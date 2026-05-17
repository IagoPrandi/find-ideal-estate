# Guia de Deploy — Frontend (Vercel) + Backend (AWS EC2 + RDS + Redis local)

> Stack: Vite + React (frontend) · FastAPI + PostgreSQL/PostGIS em RDS · Redis local no EC2 · Workers Dramatiq em EC2.

---

## Índice

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [Rede AWS e segurança](#2-rede-aws-e-segurança)
3. [Banco gerenciado e cache local](#3-banco-gerenciado-e-cache-local)
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
      ├── redis                   (porta interna Docker, sem exposição pública)
      └── Valhalla / OTP          (self-hosted, quando aplicável)

Subnets privadas da mesma VPC
└── RDS PostgreSQL 16 + PostGIS
```

O MVP fica híbrido: **PostgreSQL/PostGIS no RDS** em subnets privadas e **Redis local no EC2** via Docker, sem exposição pública da porta `6379`. O EC2 continua hospedando API, workers e serviços pesados de mobilidade/scraping.

> Em produção, `docker-compose.prod.yml` força `DATABASE_URL` a apontar para o RDS e mantém `REDIS_URL=redis://redis:6379/0` dentro da rede Docker local da instância.

---

## 2. Rede AWS e segurança

### 2.1 Região, VPC e DNS

Crie uma VPC dedicada ao projeto na mesma região onde ficarão EC2 e RDS.

Configuração recomendada:

| Campo | Valor |
|---|---|
| Nome | `vpc-onde-morar-prod` |
| Região | preferencialmente `sa-east-1` se latência Brasil for prioridade; `us-east-1` se custo/serviços forem prioridade |
| IPv4 CIDR | `10.20.0.0/23` |
| IPv6 | desabilitado no MVP, salvo necessidade explícita |
| DNS resolution | habilitado |
| DNS hostnames | habilitado |
| Tenancy | default |

Use uma VPC nova para evitar conflito com redes antigas, VPNs ou ambientes de teste. Se já existir uma VPC corporativa, valide antes se o bloco `10.20.0.0/23` não conflita com outras redes privadas.

### 2.2 Plano de subnets

Use pelo menos 2 Availability Zones. O RDS exige DB subnet group com subnets em AZs diferentes para alta disponibilidade e manutenção segura.

Plano inicial:

| Nome | AZ | CIDR | Tipo | Uso |
|---|---|---:|---|---|
| `subnet-onde-morar-public-a` | `az-a` | `10.20.0.0/24` | pública | EC2, Nginx, Elastic IP |
| `subnet-onde-morar-public-b` | `az-b` | `10.20.1.0/24` | pública | reserva para ALB/futuro failover |
| `subnet-onde-morar-private-data-a` | `az-a` | `10.20.10.0/24` | privada | RDS |
| `subnet-onde-morar-private-data-b` | `az-b` | `10.20.11.0/24` | privada | RDS |
| `subnet-onde-morar-private-app-a` | `az-a` | `10.20.20.0/24` | privada | futura API/worker atrás de ALB |
| `subnet-onde-morar-private-app-b` | `az-b` | `10.20.21.0/24` | privada | futura API/worker atrás de ALB |

Para o MVP, a EC2 pode começar na subnet pública. As subnets privadas de app já ficam reservadas para uma evolução sem renumerar a rede.

### 2.3 Internet Gateway e route tables

Crie um Internet Gateway:

| Recurso | Nome |
|---|---|
| Internet Gateway | `igw-onde-morar-prod` |

Anexe o Internet Gateway à VPC.

Crie as route tables:

| Route table | Associar com | Rotas |
|---|---|---|
| `rtb-onde-morar-public` | subnets públicas | `10.20.0.0/16 -> local`; `0.0.0.0/0 -> igw-onde-morar-prod` |
| `rtb-onde-morar-private-data` | subnets privadas de dados | `10.20.0.0/16 -> local` |
| `rtb-onde-morar-private-app` | subnets privadas de app | `10.20.0.0/16 -> local`; opcionalmente `0.0.0.0/0 -> NAT Gateway` no futuro |

Regras:

- Subnets públicas devem ter rota `0.0.0.0/0` para o Internet Gateway.
- Subnets privadas de dados não devem ter rota direta para Internet Gateway.
- RDS fica somente nas subnets privadas de dados.
- NAT Gateway não é necessário para o RDS. Ele só será necessário se API/workers forem movidos para subnets privadas e precisarem baixar imagens, acessar APIs externas, Mercado Pago, MapTiler, Mapbox, GitHub ou serviços similares.

### 2.4 DB subnet group e isolamento do Redis

Crie um DB subnet group para o RDS:

| Campo | Valor |
|---|---|
| Nome | `dbsubnet-onde-morar-prod` |
| VPC | `vpc-onde-morar-prod` |
| Subnets | `subnet-onde-morar-private-data-a`, `subnet-onde-morar-private-data-b` |

Para o Redis local:

- não existe subnet group;
- não abra `6379` no Security Group da EC2;
- mantenha `ports: []` no override de produção para que o Redis exista apenas na rede Docker interna.

### 2.5 Security Groups

Crie Security Groups com referência entre grupos, não com IP privado fixo. Isso evita quebrar acesso se a EC2 for recriada.

| Security Group | Regras de entrada |
|---|---|
| `sg-onde-morar-ec2` | `22/tcp` somente do seu IP; `80/tcp` e `443/tcp` de `0.0.0.0/0` |
| `sg-onde-morar-rds` | `5432/tcp` somente de `sg-onde-morar-ec2` |

Regras obrigatórias:

- Não liberar `5432` ou `6379` para internet.
- Não usar `0.0.0.0/0` no RDS.
- Não colocar credenciais reais em documentação, GitHub Actions logs ou arquivos commitados.
- Usar credenciais diferentes por ambiente: local, staging e produção.

### 2.6 NACLs, endpoints e validação

Mantenha Network ACLs padrão no MVP, salvo exigência explícita de compliance. Security Groups são stateful e suficientes para este desenho inicial.

Opcionalmente, quando mover API/workers para subnets privadas, considere VPC endpoints para reduzir dependência de NAT:

| Endpoint | Quando usar |
|---|---|
| S3 Gateway Endpoint | acesso a buckets S3/R2 compatível via AWS S3 |
| CloudWatch Logs Interface Endpoint | logs sem saída pública |
| ECR API/DKR Interface Endpoints | pull de imagens privadas sem internet |
| Secrets Manager Interface Endpoint | leitura de segredos sem internet |

Validação mínima após criar a rede:

```bash
# A partir da EC2, DNS interno do RDS deve resolver e porta deve responder.
nc -vz meu-rds.xxxxxx.us-east-1.rds.amazonaws.com 5432

# A partir da EC2, o Redis local deve responder apenas via Docker/network interna.
docker exec -it $(docker ps -qf name=redis) redis-cli ping

# RDS não deve responder a partir da sua máquina local pela internet.
nc -vz meu-rds.xxxxxx.us-east-1.rds.amazonaws.com 5432
```

O último comando deve falhar fora da VPC. Se responder pela internet, a rede está insegura e deve ser corrigida antes do deploy.

---

## 3. Banco gerenciado e cache local

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

### 3.2 Redis local no EC2

Configuração inicial recomendada:

| Campo | Valor inicial |
|---|---|
| Imagem | `redis:7-alpine` |
| Execução | container Docker na mesma instância da API |
| Exposição externa | nenhuma |
| Porta | `6379` somente dentro da rede Docker |
| Persistência | opcional no MVP; manter sem exposição pública |
| Restart policy | `unless-stopped` |

Use `REDIS_URL` interno:

```env
REDIS_URL=redis://redis:6379/0
```

Regras:

- não mapear `6379` para o host;
- não abrir `6379` no Security Group da EC2;
- usar rotação de logs e monitorar memória do Redis;
- se o Redis passar a armazenar estado não recriável, adicionar volume persistente e política de backup.

### 3.3 Teste de conectividade a partir do EC2

```bash
# DNS e porta do RDS
nc -vz meu-rds.xxxxxx.us-east-1.rds.amazonaws.com 5432

# Redis local dentro do Docker
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec redis redis-cli ping

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

Preencha `DATABASE_URL` com o endpoint do RDS. Em produção, o `REDIS_URL` deve ficar interno no Docker, apontando para `redis://redis:6379/0`.

### 4.5 `docker-compose.prod.yml`

Use o override de produção:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --services
```

Confirme no output de `config --services`:

- sobem por padrão: `api`, `worker`, `worker-scrape-browser`, `worker-prewarm`, `redis`;
- não sobem por padrão: `postgres`, `ui`.

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
  worker worker-scrape-browser worker-prewarm redis

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
| `REDIS_URL` | `redis://redis:6379/0` |
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

- [ ] VPC `vpc-onde-morar-prod` criada com CIDR `10.20.0.0/16`.
- [ ] DNS resolution e DNS hostnames habilitados na VPC.
- [ ] Subnets públicas criadas: `10.20.0.0/24` e `10.20.1.0/24`.
- [ ] Subnets privadas de dados criadas: `10.20.10.0/24` e `10.20.11.0/24`.
- [ ] Subnets privadas de app reservadas: `10.20.20.0/24` e `10.20.21.0/24`.
- [ ] Internet Gateway criado e anexado à VPC.
- [ ] Route table pública criada com `0.0.0.0/0 -> Internet Gateway`.
- [ ] Route table privada de dados sem rota para Internet Gateway.
- [ ] DB subnet group `dbsubnet-onde-morar-prod` criado somente com subnets privadas de dados.
- [ ] `sg-onde-morar-ec2` permite SSH somente do seu IP e HTTP/HTTPS público.
- [ ] `sg-onde-morar-rds` permite `5432` somente de `sg-onde-morar-ec2`.
- [ ] Porta `6379` não está aberta no Security Group da EC2.
- [ ] RDS não responde a partir da internet pública.

### RDS / Redis

- [ ] RDS PostgreSQL 16 criado sem acesso público.
- [ ] Banco `find_ideal_estate` criado.
- [ ] Extensões `postgis` e `pgcrypto` habilitadas.
- [ ] Backups automáticos habilitados.
- [ ] EC2 consegue conectar no RDS (`nc -vz ... 5432`).
- [ ] Redis local sobe com `docker compose ... up -d redis`.
- [ ] `docker compose ... exec redis redis-cli ping` retorna `PONG`.

### EC2 / Backend

- [ ] Instância EC2 `t3.large` ou superior criada.
- [ ] Elastic IP alocado e associado.
- [ ] `A record` de `api.seudominio.com.br` apontando para o Elastic IP.
- [ ] Docker e Docker Compose instalados.
- [ ] Repositório clonado em `/opt/app`.
- [ ] `.env` preenchido com endpoint real do RDS e `REDIS_URL=redis://redis:6379/0`.
- [ ] `.env` revisado sem imprimir segredos em logs; `docker compose ... config --services` não lista `postgres` nem `ui`.
- [ ] `docker compose ... up -d api` executado com sucesso.
- [ ] `docker compose ... up -d redis` executado com sucesso.
- [ ] Logs da API mostram migrations aplicadas sem erro.
- [ ] API e workers conseguem conectar no Redis local sem exposição da porta `6379`.
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
