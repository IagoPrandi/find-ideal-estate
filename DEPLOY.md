# Guia de Deploy — Frontend (Vercel) + Backend (EC2 na AWS)

> Stack: Vite + React (frontend) · FastAPI + PostgreSQL/PostGIS + Redis + Workers Dramatiq (backend)

---

## Índice

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [Frontend no Vercel](#2-frontend-no-vercel)
3. [Backend na AWS — EC2 + Docker Compose](#3-backend-na-aws--ec2--docker-compose)
4. [Nginx + SSL no EC2](#4-nginx--ssl-no-ec2)
5. [Variáveis de ambiente (resumo)](#5-variáveis-de-ambiente-resumo)
6. [CI/CD com GitHub Actions](#6-cicd-com-github-actions)
7. [Checklist de primeira subida](#7-checklist-de-primeira-subida)

---

## 1. Visão geral da arquitetura

```
Usuário
  │
  ▼
Vercel CDN ──► apps/web  (Vite SPA, edge global)
  │
  │  VITE_API_BASE = https://api.seudominio.com.br
  ▼
EC2  (Elastic IP → api.seudominio.com.br)
├── Nginx  (porta 443, SSL via Let's Encrypt)
│     └── proxy_pass → http://localhost:8000
└── Docker Compose
      ├── api              (uvicorn, porta 8000 interna)
      ├── worker           (filas: transport, zones, enrichment…)
      ├── worker-scrape-browser  (Playwright + Xvfb)
      ├── worker-prewarm
      ├── postgres         (PostGIS, porta interna)
      └── redis            (porta interna)
```

Tudo roda num único EC2. Nginx faz a terminação TLS e encaminha para a API. Banco e Redis ficam acessíveis apenas internamente via rede Docker.

---

## 2. Frontend no Vercel

### 2.1 Pré-requisitos

- Conta no [vercel.com](https://vercel.com) conectada ao GitHub.

### 2.2 Arquivo `apps/web/vercel.json`

Crie o arquivo em `apps/web/vercel.json`:

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

Garante que o React Router funcione ao acessar URLs diretas ou recarregar a página.

### 2.3 Configuração do projeto no Vercel

No painel, clique em **Add New → Project** e importe o repositório:

| Campo | Valor |
|-------|-------|
| **Framework Preset** | Vite |
| **Root Directory** | `apps/web` |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |
| **Install Command** | `npm ci` |
| **Node.js Version** | 20.x |

### 2.4 Variáveis de ambiente no Vercel

**Settings → Environment Variables:**

| Variável | Valor |
|----------|-------|
| `VITE_API_BASE` | `https://api.seudominio.com.br` |
| `VITE_MAPTILER_API_KEY` | chave do MapTiler |
| `VITE_GOOGLE_CLIENT_ID` | client_id do Google OAuth |

### 2.5 Domínio personalizado

1. **Settings → Domains** → adicione `seudominio.com.br`.
2. No DNS, crie um `CNAME` apontando para `cname.vercel-dns.com`.
3. O Vercel provisiona o certificado TLS automaticamente.

---

## 3. Backend na AWS — EC2 + Docker Compose

### 3.1 Criar a instância EC2

No console AWS (ou via CLI):

- **AMI:** Ubuntu 24.04 LTS
- **Tipo:** `t3.large` (2 vCPU, 8 GB RAM) — necessário para Playwright + PostGIS
- **Storage:** 40 GB gp3 (SSD)
- **Security Group:**

| Porta | Protocolo | Origem |
|-------|-----------|--------|
| 22 | TCP | seu IP (para SSH) |
| 80 | TCP | `0.0.0.0/0` |
| 443 | TCP | `0.0.0.0/0` |

### 3.2 Elastic IP

```bash
# Alocar e associar à instância
aws ec2 allocate-address --domain vpc
aws ec2 associate-address --instance-id i-XXXXXXXX --allocation-id eipalloc-XXXXXXXX
```

Anote o IP público estático e crie um registro `A` em `api.seudominio.com.br` apontando para ele.

### 3.3 Preparar o servidor

```bash
ssh ubuntu@<ELASTIC_IP>

# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
newgrp docker

# Docker Compose plugin
sudo apt-get install -y docker-compose-plugin

# Nginx e Certbot
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

### 3.4 Clonar o repositório e configurar o `.env`

```bash
git clone https://github.com/SEU_ORG/SEU_REPO.git /opt/app
cd /opt/app

# Criar o .env de produção a partir do exemplo
cp .env.example .env
nano .env  # preencher os valores reais (veja seção 5)
```

### 3.5 `docker-compose.prod.yml`

Este arquivo sobrescreve o compose de desenvolvimento: remove hot-reload, volumes de código e expõe apenas o necessário.

```yaml
# Usar com: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

services:
  api:
    restart: unless-stopped
    command: ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
    volumes: []

  worker:
    profiles: []          # remove o profile "manual" para subir por padrão
    restart: unless-stopped
    volumes: []

  worker-scrape-browser:
    restart: unless-stopped
    volumes: []

  worker-prewarm:
    restart: unless-stopped
    volumes: []

  postgres:
    restart: unless-stopped
    ports: []             # remove exposição externa do banco

  redis:
    restart: unless-stopped
    ports: []             # remove exposição externa do Redis
```

> O arquivo `docker-compose.prod.yml` já está no repositório em [`docker-compose.prod.yml`](docker-compose.prod.yml).

### 3.6 Primeira subida

```bash
cd /opt/app

# Migrations (roda uma vez; o entrypoint.sh executa alembic upgrade head antes de subir o uvicorn)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api

# Aguardar API ficar healthy, depois subir tudo
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Verificar status
docker compose ps
docker compose logs api --tail 50
```

---

## 4. Nginx + SSL no EC2

### 4.1 Configuração do Nginx

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

### 4.2 Certificado SSL (Let's Encrypt)

```bash
sudo certbot --nginx -d api.seudominio.com.br --non-interactive --agree-tos -m seu@email.com
```

O Certbot edita o arquivo do Nginx automaticamente para adicionar HTTPS e redirecionar HTTP → HTTPS. A renovação é automática via systemd timer.

---

## 5. Variáveis de ambiente (resumo)

### Frontend — Vercel

| Variável | Exemplo |
|----------|---------|
| `VITE_API_BASE` | `https://api.seudominio.com.br` |
| `VITE_MAPTILER_API_KEY` | chave MapTiler |
| `VITE_GOOGLE_CLIENT_ID` | `123456.apps.googleusercontent.com` |

### Backend — arquivo `.env` no EC2

| Variável | Observação |
|----------|------------|
| `DATABASE_URL` | `postgresql://postgres:SENHA@postgres:5432/find_ideal_estate` (serviço Docker interno) |
| `REDIS_URL` | `redis://redis:6379/0` (serviço Docker interno) |
| `GOOGLE_CLIENT_ID` | mesmo valor do frontend |
| `RESEND_API_KEY` | chave do serviço de e-mail |
| `MAPTILER_API_KEY` | chave do MapTiler (usada no backend para geocoding) |
| `MERCADO_PAGO_ENVIRONMENT` | `production` |
| `MERCADO_PAGO_ACCESS_TOKEN_LIVE` | token live |
| `MERCADO_PAGO_PUBLIC_KEY_LIVE` | chave pública live |
| `MERCADO_PAGO_WEBHOOK_SECRET` | segredo de validação |
| `MERCADO_PAGO_WEBHOOK_URL` | `https://api.seudominio.com.br/billing/webhook/mercado-pago` |
| `INTERNAL_API_TOKEN` | token forte (uuid4) para chamadas internas |

---

## 6. CI/CD com GitHub Actions

Adicione os secrets no repositório (`Settings → Secrets → Actions`):

```
EC2_HOST        → IP elástico do servidor
EC2_USER        → ubuntu
EC2_SSH_KEY     → chave privada SSH (conteúdo do arquivo .pem)
VERCEL_TOKEN    → token da conta Vercel
VERCEL_ORG_ID   → org ID do projeto Vercel
VERCEL_PROJECT_ID → project ID do projeto Vercel
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
            docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache api
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps api
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps \
              worker worker-scrape-browser worker-prewarm
            docker image prune -f
```

> O `entrypoint.sh` já roda `alembic upgrade head` antes do uvicorn em cada subida da API, então as migrations são aplicadas automaticamente no deploy.

---

## 7. Checklist de primeira subida

### EC2 / Backend
- [ ] Instância EC2 `t3.large` criada (Ubuntu 24.04)
- [ ] Elastic IP alocado e associado
- [ ] Security Group liberando 22, 80, 443
- [ ] `A record` de `api.seudominio.com.br` apontando para o Elastic IP (aguardar propagação)
- [ ] Docker e Docker Compose instalados
- [ ] Repositório clonado em `/opt/app`
- [ ] `.env` preenchido com todos os valores reais
- [ ] `docker compose ... up -d` executado com sucesso
- [ ] `docker compose ps` mostra todos os serviços `healthy` / `running`
- [ ] `curl http://localhost:8000/health` retorna `200` no servidor
- [ ] Nginx configurado e testado (`nginx -t`)
- [ ] Certificado SSL emitido pelo Certbot
- [ ] `curl https://api.seudominio.com.br/health` retorna `200`

### Vercel / Frontend
- [ ] `apps/web/vercel.json` com rewrite SPA criado e commitado
- [ ] Projeto criado com Root Directory `apps/web`
- [ ] Variáveis de ambiente configuradas (`VITE_API_BASE` aponta para `https://api.seudominio.com.br`)
- [ ] Build bem-sucedido
- [ ] DNS de `seudominio.com.br` apontando para o Vercel
- [ ] Certificado TLS provisionado

### Teste de integração
- [ ] `https://seudominio.com.br` carrega o frontend sem erros no console
- [ ] Login com Google funciona
- [ ] Mapa carrega (MapTiler)
- [ ] Chamadas à API retornam dados (Network tab → `api.seudominio.com.br`)
- [ ] Fluxo de pagamento Pix funciona (webhook Mercado Pago recebido e processado)
