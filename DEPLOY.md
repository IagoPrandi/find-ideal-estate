# Guia de Deploy — Frontend (Vercel) + Backend (AWS EC2 + RDS + ElastiCache)

> Stack: Vite + React (frontend) · FastAPI + PostgreSQL/PostGIS em RDS · Redis em ElastiCache · Workers Dramatiq em EC2.

---

## Índice

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [Rede AWS e segurança](#2-rede-aws-e-segurança)
3. [Banco e cache gerenciados](#3-banco-e-cache-gerenciados)
4. [Backend na AWS — EC2 + Docker Compose](#4-backend-na-aws--ec2--docker-compose)
5. [Nginx + SSL no EC2](#5-nginx--ssl-no-ec2)
6. [Variáveis de ambiente](#6-variáveis-de-ambiente)
7. [Frontend no Vercel](#7-frontend-no-vercel)
8. [CI/CD com GitHub Actions](#8-cicd-com-github-actions)
9. [Checklist de primeira subida](#9-checklist-de-primeira-subida)

---

## 1. Visão geral da arquitetura

```text
Usuário
  │
  ▼
Vercel CDN ──► apps/web (Vite SPA)
  │
  │  VITE_API_BASE = https://api.seudominio.com.br
  ▼
EC2 pública (Elastic IP → api.seudominio.com.br)
├── Nginx (porta 443, SSL via Let's Encrypt)
│     └── proxy_pass → http://localhost:8000
└── Docker Compose
      ├── api                     (uvicorn, porta 8000 local)
      ├── worker                  (filas: transport, zones, enrichment...)
      ├── worker-scrape-browser   (Playwright + Xvfb)
      ├── worker-prewarm
      ├── Valhalla / OTP          (self-hosted, quando aplicável)
      └── sem Postgres/Redis locais em produção

Subnets privadas da mesma VPC
├── RDS PostgreSQL 16 + PostGIS
└── ElastiCache Redis/Valkey
```

O MVP já inicia com **PostgreSQL/PostGIS no RDS** e **Redis no ElastiCache**, ambos em subnets privadas. O EC2 continua hospedando API, workers e serviços pesados de mobilidade/scraping. Banco e cache não devem ter IP público nem portas abertas para a internet.

> O Postgres e o Redis definidos no `docker-compose.yml` são para desenvolvimento local. Em produção, `docker-compose.prod.yml` força `DATABASE_URL` e `REDIS_URL` vindos do `.env` e coloca os serviços locais em profile inativo.

---

## 2. Rede AWS e segurança

### 2.1 Topologia mínima

- 1 VPC dedicada ao projeto.
- 2 subnets públicas, em AZs diferentes.
- 2 subnets privadas, em AZs diferentes, para RDS e ElastiCache.
- EC2 inicialmente em subnet pública com Elastic IP.
- RDS e ElastiCache em subnets privadas.
- NAT Gateway é opcional nesta fase se apenas a EC2 pública precisa sair para internet. Se futuramente mover API/workers para subnets privadas, use NAT Gateway ou outro caminho controlado de egress.

### 2.2 Security Groups

Crie três Security Groups:

| Security Group | Regras de entrada |
|---|---|
| `sg-onde-morar-ec2` | `22/tcp` somente do seu IP; `80/tcp` e `443/tcp` de `0.0.0.0/0` |
| `sg-onde-morar-rds` | `5432/tcp` somente de `sg-onde-morar-ec2` |
| `sg-onde-morar-redis` | `6379/tcp` somente de `sg-onde-morar-ec2` |

Regras obrigatórias:

- Não liberar `5432` ou `6379` para internet.
- Não usar `0.0.0.0/0` no RDS ou ElastiCache.
- Não colocar credenciais reais em documentação, GitHub Actions logs ou arquivos commitados.
- Usar credenciais diferentes por ambiente: local, staging e produção.

---

## 3. Banco e cache gerenciados

### 3.1 RDS PostgreSQL + PostGIS

Configuração inicial recomendada:

| Campo | Valor inicial |
|---|---|
| Engine | PostgreSQL 16 |
| Extensão | PostGIS habilitada no banco da aplicação |
| Classe | `db.t4g.medium` para produção inicial; `db.t4g.micro` apenas staging/teste |
| Storage | gp3, mínimo 40 GB, autoscaling habilitado |
| Public access | `No` |
| Multi-AZ | recomendado para produção; opcional para reduzir custo no MVP inicial |
| Backups | retenção mínima de 7 dias |
| Encryption | habilitado com KMS |
| Security Group | `sg-onde-morar-rds` |

Após criar o banco, conecte a partir do EC2 e habilite as extensões necessárias:

```bash
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

Se as migrations já criam essas extensões, os comandos acima devem continuar idempotentes.

### 3.2 ElastiCache Redis/Valkey

Configuração inicial recomendada:

| Campo | Valor inicial |
|---|---|
| Engine | Redis OSS 7.x ou Valkey compatível |
| Tipo | Node-based cache |
| Classe | `cache.t4g.small` para produção inicial |
| Subnet group | subnets privadas |
| Public access | inexistente |
| Security Group | `sg-onde-morar-redis` |
| Backups | habilitar se o cache passar a armazenar estado não recriável |

Se habilitar TLS/auth token, valide que a aplicação aceita `rediss://`:

```env
REDIS_URL=rediss://:SENHA_DO_REDIS@cache.xxxxxx.use1.cache.amazonaws.com:6379/0
```

Se usar Redis privado sem TLS no primeiro MVP, documente a decisão como temporária. A porta continua inacessível fora da VPC.

### 3.3 Teste de conectividade a partir do EC2

```bash
# DNS e porta do RDS
nc -vz meu-rds.xxxxxx.us-east-1.rds.amazonaws.com 5432

# DNS e porta do ElastiCache
nc -vz meu-cache.xxxxxx.use1.cache.amazonaws.com 6379

# Extensões do Postgres
psql "$DATABASE_URL" -c "SELECT extname FROM pg_extension WHERE extname IN ('postgis', 'pgcrypto');"
```

---

## 4. Backend na AWS — EC2 + Docker Compose

### 4.1 Criar a instância EC2

No console AWS ou via CLI:

- **AMI:** Ubuntu 24.04 LTS.
- **Tipo:** `t3.large` (2 vCPU, 8 GB RAM) como mínimo para Playwright + workers + serviços de mobilidade. Se Valhalla/OTP e scraping concorrerem muito, prefira `t3.xlarge`.
- **Storage:** 40 GB gp3 ou mais.
- **Security Group:** `sg-onde-morar-ec2`.

### 4.2 Elastic IP

```bash
aws ec2 allocate-address --domain vpc
aws ec2 associate-address --instance-id i-XXXXXXXX --allocation-id eipalloc-XXXXXXXX
```

Crie um registro `A` em `api.seudominio.com.br` apontando para o Elastic IP.

### 4.3 Preparar o servidor

```bash
ssh ubuntu@<ELASTIC_IP>

# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
newgrp docker

# Docker Compose plugin
sudo apt-get update
sudo apt-get install -y docker-compose-plugin

# Nginx, Certbot e clientes de diagnóstico
sudo apt-get install -y nginx certbot python3-certbot-nginx postgresql-client netcat-openbsd
```

### 4.4 Clonar o repositório e configurar o `.env`

```bash
git clone https://github.com/SEU_ORG/SEU_REPO.git /opt/app
cd /opt/app

cp .env.example .env
nano .env
```

Preencha `DATABASE_URL` com o endpoint do RDS e `REDIS_URL` com o endpoint do ElastiCache. Não use `postgres:5432` nem `redis:6379` em produção.

### 4.5 `docker-compose.prod.yml`

Use o override de produção:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --services
```

Confirme no output de `config --services`:

- sobem por padrão: `api`, `worker`, `worker-scrape-browser`, `worker-prewarm`;
- não sobem por padrão: `postgres`, `redis`, `ui`.

Evite imprimir ou salvar o output completo de `docker compose config` em CI/logs, porque ele expande valores do `.env` e pode expor segredos.

### 4.6 Primeira subida

```bash
cd /opt/app

# Sobe API primeiro para aplicar migrations via entrypoint.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api

# Verificar API.
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs api --tail 80
curl http://localhost:8000/health

# Subir workers.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d \
  worker worker-scrape-browser worker-prewarm

# Verificar status.
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

---

## 5. Nginx + SSL no EC2

### 5.1 Configuração do Nginx

Crie `/etc/nginx/sites-available/api`:

```nginx
server {
    listen 80;
    server_name api.seudominio.com.br;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        client_max_body_size 20M;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/api /etc/nginx/sites-enabled/api
sudo nginx -t
sudo systemctl reload nginx
```

### 5.2 Certificado SSL

```bash
sudo certbot --nginx -d api.seudominio.com.br --non-interactive --agree-tos -m seu@email.com
```

O Certbot adiciona HTTPS e redirecionamento HTTP → HTTPS. A renovação automática roda via systemd timer.

---

## 6. Variáveis de ambiente

### 6.1 Backend — `.env` no EC2

| Variável | Observação |
|---|---|
| `DATABASE_URL` | `postgresql://APP_USER:SENHA@meu-rds.xxxxxx.us-east-1.rds.amazonaws.com:5432/find_ideal_estate` |
| `REDIS_URL` | `redis://meu-cache.xxxxxx.use1.cache.amazonaws.com:6379/0` ou `rediss://:SENHA@...:6379/0` |
| `DB_POOL_SIZE` | `5` como ponto inicial |
| `DB_MAX_OVERFLOW` | `5` como ponto inicial |
| `DB_POOL_TIMEOUT_SECONDS` | `30` |
| `GOOGLE_CLIENT_ID` | mesmo valor do frontend |
| `RESEND_API_KEY` | chave do serviço de e-mail |
| `MAPTILER_API_KEY` | chave do MapTiler usada pelo backend |
| `MERCADO_PAGO_ENVIRONMENT` | `production` |
| `MERCADO_PAGO_ACCESS_TOKEN_LIVE` | token live |
| `MERCADO_PAGO_PUBLIC_KEY_LIVE` | chave pública live |
| `MERCADO_PAGO_WEBHOOK_SECRET` | segredo de validação |
| `MERCADO_PAGO_WEBHOOK_URL` | `https://api.seudominio.com.br/billing/webhook/mercado-pago` |
| `INTERNAL_API_TOKEN` | token forte, por exemplo UUID v4 ou valor aleatório de 32+ bytes |

Regras:

- Nunca commitar `.env`.
- Não imprimir o `.env` inteiro em logs de CI/CD.
- Ajustar pool do banco de acordo com o tamanho do RDS. API e cada worker podem abrir pools próprios.

### 6.2 Frontend — Vercel

| Variável | Exemplo |
|---|---|
| `VITE_API_BASE` | `https://api.seudominio.com.br` |
| `VITE_MAPTILER_API_KEY` | chave MapTiler |
| `VITE_GOOGLE_CLIENT_ID` | `123456.apps.googleusercontent.com` |

---

## 7. Frontend no Vercel

### 7.1 Pré-requisitos

- Conta no [vercel.com](https://vercel.com) conectada ao GitHub.

### 7.2 Arquivo `apps/web/vercel.json`

Crie o arquivo em `apps/web/vercel.json`:

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

Isso garante que o React Router funcione ao acessar URLs diretas ou recarregar a página.

### 7.3 Configuração do projeto no Vercel

No painel, clique em **Add New → Project** e importe o repositório:

| Campo | Valor |
|---|---|
| **Framework Preset** | Vite |
| **Root Directory** | `apps/web` |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |
| **Install Command** | `npm ci` |
| **Node.js Version** | 20.x |

### 7.4 Variáveis de ambiente no Vercel

**Settings → Environment Variables:**

| Variável | Valor |
|---|---|
| `VITE_API_BASE` | `https://api.seudominio.com.br` |
| `VITE_MAPTILER_API_KEY` | chave do MapTiler |
| `VITE_GOOGLE_CLIENT_ID` | client_id do Google OAuth |

### 7.5 Domínio personalizado

1. **Settings → Domains** → adicione `seudominio.com.br`.
2. No DNS, crie um `CNAME` apontando para `cname.vercel-dns.com`.
3. O Vercel provisiona o certificado TLS automaticamente.

---

## 8. CI/CD com GitHub Actions

Adicione os secrets no repositório (`Settings → Secrets → Actions`):

```text
EC2_HOST
EC2_USER
EC2_SSH_KEY
VERCEL_TOKEN
VERCEL_ORG_ID
VERCEL_PROJECT_ID
```

Crie `.github/workflows/deploy.yml`:

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
          working-directory: apps/web
          vercel-args: --prod

  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ${{ secrets.EC2_USER }}
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /opt/app
            git pull origin main
            docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
            docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache api worker worker-scrape-browser worker-prewarm
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps api
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps \
              worker worker-scrape-browser worker-prewarm
            docker image prune -f
```

> O `entrypoint.sh` aplica `alembic upgrade head` antes do uvicorn. A primeira subida deve ser acompanhada pelos logs da API para validar conexão com RDS e migrations.

---

## 9. Checklist de primeira subida

### AWS / Rede

- [ ] VPC criada ou selecionada.
- [ ] Subnets públicas e privadas criadas em pelo menos 2 AZs.
- [ ] `sg-onde-morar-ec2` permite SSH somente do seu IP e HTTP/HTTPS público.
- [ ] `sg-onde-morar-rds` permite `5432` somente de `sg-onde-morar-ec2`.
- [ ] `sg-onde-morar-redis` permite `6379` somente de `sg-onde-morar-ec2`.

### RDS / ElastiCache

- [ ] RDS PostgreSQL 16 criado sem acesso público.
- [ ] Banco `find_ideal_estate` criado.
- [ ] Extensões `postgis` e `pgcrypto` habilitadas.
- [ ] Backups automáticos habilitados.
- [ ] ElastiCache criado em subnets privadas.
- [ ] EC2 consegue conectar no RDS (`nc -vz ... 5432`).
- [ ] EC2 consegue conectar no ElastiCache (`nc -vz ... 6379`).

### EC2 / Backend

- [ ] Instância EC2 `t3.large` ou superior criada.
- [ ] Elastic IP alocado e associado.
- [ ] `A record` de `api.seudominio.com.br` apontando para o Elastic IP.
- [ ] Docker e Docker Compose instalados.
- [ ] Repositório clonado em `/opt/app`.
- [ ] `.env` preenchido com endpoints reais de RDS e ElastiCache.
- [ ] `.env` revisado sem imprimir segredos em logs; `docker compose ... config --services` não lista `postgres`, `redis` ou `ui`.
- [ ] `docker compose ... up -d api` executado com sucesso.
- [ ] Logs da API mostram migrations aplicadas sem erro.
- [ ] Workers sobem sem tentar conectar em `postgres` ou `redis` locais.
- [ ] `curl http://localhost:8000/health` retorna `200`.
- [ ] Nginx configurado e testado (`nginx -t`).
- [ ] Certificado SSL emitido pelo Certbot.
- [ ] `curl https://api.seudominio.com.br/health` retorna `200`.

### Vercel / Frontend

- [ ] `apps/web/vercel.json` com rewrite SPA criado e commitado.
- [ ] Projeto criado com Root Directory `apps/web`.
- [ ] Variáveis de ambiente configuradas.
- [ ] Build bem-sucedido.
- [ ] DNS de `seudominio.com.br` apontando para o Vercel.
- [ ] Certificado TLS provisionado.

### Teste de integração

- [ ] `https://seudominio.com.br` carrega o frontend sem erros no console.
- [ ] Login com Google funciona.
- [ ] Mapa carrega com MapTiler.
- [ ] Chamadas à API retornam dados.
- [ ] Fluxo de pagamento Pix funciona.
- [ ] Uma jornada completa executa sem backlog crescente nas filas.
