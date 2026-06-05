# PRD — Find Ideal Estate

**Versão:** 2.4  
**Fonte canônica anterior:** `PRD v2.3 — Find Ideal Estate`  
**Última atualização:** 2026-04-26  
**Status:** Ativo

> **Mudanças v2.3 (2026-04-26):** monetização migrada de "créditos avulsos" para **freemium + assinatura mensal por plano** (Anônimo, Free, Básico, Pro, Pro Max). Custo padronizado em 5 etapas monetizáveis × 20 créditos = 100 créditos por jornada completa. Stripe Billing (Subscriptions) substitui Payment Intent. Plano Pro inclui endereços de imóveis salvos na fila do prewarm noturno (mesmo run da atualização da base). Plano Pro Max ganha fila dedicada de refresh com cadência e franquia próprias. Adicionadas tabelas `plans`, `plan_entitlements`, `subscriptions`, `subscription_events`, `pro_max_refresh_targets`. Fase 8 reescopada e Fase 9 (Pro Max) adicionada ao roadmap.

> **Mudanças v2.4 (2026-04-26):** mantém o modelo de monetização por **freemium + planos mensais + créditos por ciclo + entitlements**, mas altera a prioridade de implementação de cobrança. A ativação inicial dos planos pagos passa a ser feita por **Pix com QR Code / Pix Copia e Cola**. **Stripe não foi removido**: Stripe Billing permanece no roadmap como evolução futura para automação de assinatura, portal do cliente, retries, proration e cobrança recorrente. A Fase 8 foi reescopada para **Auth + planos + ativação por Pix**. Fase 10 adicionada para **Stripe Billing e automação de recorrência**. Tabelas `subscriptions` e `subscription_events` substituídas por `plan_activations`. Adicionadas `payments` e `pix_payment_data`. Preço do Pro Max corrigido para R$ 312,99.

---

## Índice

1. [Visão do Produto](#1-visão-do-produto)
2. [Progress Tracker](#2-progress-tracker)
3. [Arquitetura do Sistema](#3-arquitetura-do-sistema)
4. [Infraestrutura e Deploy](#4-infraestrutura-e-deploy)
5. [Modelo de Dados](#5-modelo-de-dados)
6. [Fontes de Dados Geoespaciais](#6-fontes-de-dados-geoespaciais)
7. [Pipeline ETL](#7-pipeline-etl)
8. [Especificação do Backend](#8-especificação-do-backend)
9. [Especificação do Frontend](#9-especificação-do-frontend)
10. [Autenticação e Modelo de Acesso](#10-autenticação-e-modelo-de-acesso)
11. [Monetização](#11-monetização)
12. [Roadmap por Fase (0–10)](#12-roadmap-por-fase-010)
13. [Segurança](#13-segurança)
14. [Observabilidade](#14-observabilidade)
15. [Estratégia de Testes](#15-estratégia-de-testes)
16. [Registro de Riscos](#16-registro-de-riscos)
17. [Decisões Técnicas Fechadas](#17-decisões-técnicas-fechadas)

---

## 1. Visão do Produto

### Problema

Encontrar imóvel para alugar ou comprar em São Paulo é um processo fragmentado: o usuário compara plataformas separadas, faz cálculos de deslocamento mentalmente e não tem visão integrada de qualidade urbana — transporte, segurança, área verde, risco de alagamento, preço e disponibilidade — para os bairros candidatos.

### Solução

**Find Ideal Estate** é um ambiente de decisão imobiliária guiado por mapa. O usuário parte de um endereço de referência, como trabalho ou escola, configura seu perfil de deslocamento e o produto:

1. Descobre pontos de transporte elegíveis dentro do raio configurado;
2. Gera zonas geoespaciais de isócrona para cada ponto selecionado;
3. Enriquece cada zona com dados urbanos analíticos;
4. Busca, normaliza e deduplica imóveis dentro da zona;
5. Permite salvar imóveis e zonas;
6. Apresenta dashboards e comparações explicáveis;
7. Permite comparar zonas e imóveis salvos;
8. Futuramente, permite interação por agente de IA com ferramentas analíticas.

### Princípios

1. **Mapa como plano principal.** A interface nunca esconde o mapa; o painel é auxiliar ao espaço.
2. **Progresso real, nunca spinner vazio.** Cada etapa de processamento emite eventos SSE granulares.
3. **Dados explicáveis.** Nenhum indicador composto com pesos opacos. O produto apresenta métricas objetivas e comparativas.
4. **Monetização proporcional ao valor e ao custo.** Créditos representam consumo de capacidade analítica; planos definem limites de acesso, persistência e atualização.
5. **Cobrança simples no lançamento.** A primeira versão de cobrança usa Pix com QR Code. Automação de assinatura via Stripe fica para fase posterior.

### Personas

| Persona | Situação | Necessidade principal |
|---|---|---|
| Relocador urbano | Mudar de bairro, manter emprego atual | Quais regiões permitem chegar ao trabalho em até X minutos? |
| Comprador de primeiro imóvel | Busca ativa com prazo definido | Comparar regiões por preço, segurança, transporte e qualidade urbana |
| Locatário em decisão rápida | Precisa escolher entre poucas opções | Comparar imóveis salvos e entender trade-offs |
| Investidor pequeno | Avalia recorrência e oportunidade | Entender preço relativo ao mercado e liquidez da região |
| Corretor/consultor | Apoia cliente na decisão | Gerar comparativos e explicações confiáveis |

---

## 2. Progress Tracker

### Fases de backend / infraestrutura

| Fase | Título | Status | Observações |
|---|---|---|---|
| 0 | Fundação: monorepo, DB, CI | ✅ Concluída | Base técnica criada |
| 1 | Core domain: journey, job, SSE | ✅ Concluída | Jornada, jobs e progresso real-time |
| 2 | Dramatiq + worker infra | ✅ Concluída | Filas, retry, watchdog, cancelamento |
| 3 | Transporte: GTFS + Valhalla + OTP | 🔄 Em progresso | Núcleo de mobilidade |
| 4 | Zonas: isócronas + enriquecimento | ✅ Concluída | Zonas, badges e enriquecimento |
| 5 | Imóveis: scrapers + dedup + cache | ✅ Concluída | Scraping, cache e deduplicação |
| 6 | Dashboard + favoritos | 🔄 Em progresso | Dashboard, favoritos de imóveis e zonas; compartilhamento de jornadas por link público |
| 7 | Scheduler noturno / prewarm | ⬜ Não iniciada | Prewarm por demanda real e salvos Pro Max |
| 8 | Auth + planos + ativação por Pix | 🔄 Em progresso | M8.1–M8.8 implementados; M8.9 (E2E) pendente |
| 9 | Plano Pro Max: refresh dedicado | ⬜ Não iniciada | Fila e cadência próprias |
| 10 | Stripe Billing e automação de recorrência | ⬜ Backlog | Automação futura; não bloqueia lançamento Pix |

### Fases de frontend

| Fase | Título | Status | Observações |
|---|---|---|---|
| FE0 | Setup Vite/React inicial | ✅ Concluída | Base web |
| FE1 | MapLibre + MapTiler | ✅ Concluída | Mapa e camadas |
| FE2 | Etapa 1: formulário de config | ✅ Concluída | Criação de jornada |
| FE3 | Migração para Next.js App Router | ⬜ Não iniciada | Não bloqueia MVP |
| FE4 | Seleção de transporte | ✅ Concluída | Pontos e linhas |
| FE5 | Progressão SSE + zonas | ✅ Concluída | Zonas progressivas |
| FE6 | Comparação de zonas | ✅ Concluída | Lista, badges e filtros; visualização somente leitura de jornada compartilhada |
| FE7 | Imóveis + dashboard | ✅ Concluída | Cards e dashboard |
| FE8 | Auth + planos + Pix | 🔄 Em progresso | PlanosPage, ContaPage, PixModal, header badges implementados |
| FE9 | UI Pro Max | ⬜ Não iniciada | Refresh, prioridade e badges |
| FE10 | Stripe customer portal | ⬜ Backlog | Portal, checkout recorrente e proration |

> **Regra de milestone:** uma fase só é marcada como concluída após confirmação explícita do responsável.

> **Observação de progresso (2026-05-25):** implementação em andamento para busca inicial por endereço geocodificado, zonas desenhadas manualmente, comparação expandida com transporte/imóveis por tipo, cor persistente de zonas salvas, snapshots de imóveis/POIs com ícones consistentes e compartilhamento público de zona salva individual. Documentos obrigatórios abertos nesta execução: `PRD.md`, `SKILLS_README.md`, `skills/best-practices/SKILL.md` e `skills/best-practices/references/agent-principles.md`. Skill usada: `best-practices`. Nenhuma fase foi marcada como concluída sem confirmação do responsável.

> **Observação de progresso (2026-05-26, revisão):** refinado o fluxo para escolha explícita entre selecionar ponto e desenhar área, com zona desenhada indo direto para comparação sem job/tela de enriquecimento. Também foram planejados/aplicados detalhes expandíveis de transporte em zonas salvas e mapa na página pública de zona compartilhada. Documentos obrigatórios reabertos nesta execução: `PRD.md`, `SKILLS_README.md`, `skills/best-practices/SKILL.md` e `skills/best-practices/references/agent-principles.md`. Skill usada: `best-practices`. Nenhuma fase foi marcada como concluída sem confirmação do responsável.

> **Observação de progresso (2026-06-05, experimento Firecrawl):** adicionado scraper experimental Firecrawl para VivaReal e ZapImóveis, selecionável por `SCRAPER_PROVIDER=firecrawl`, com extração via `rawHtml` dos chunks Next.js (`content.listings`) para preservar `latitude`/`longitude`; a verificação live em `scripts/verify_m5_3_scrapers_live.py --provider firecrawl` agora exige imóveis com coordenadas. Documentos obrigatórios abertos nesta execução: `PRD.md`, `SKILLS_README.md` e `skills/firecrawl/SKILL.md`. Skill usada: `firecrawl`. Nenhuma fase foi marcada como concluída sem confirmação do responsável.

> **Observação de progresso (2026-06-05, Firecrawl como padrão):** Firecrawl passou a ser o provider padrão para ZapImóveis e VivaReal no `PlatformRegistry`; Playwright permanece disponível por override explícito com `SCRAPER_PROVIDER=playwright`. Documentos obrigatórios abertos nesta execução: `PRD.md`, `SKILLS_README.md` e `skills/firecrawl/SKILL.md`. Skill usada: `firecrawl`. Nenhuma fase foi marcada como concluída sem confirmação do responsável.

---

## 3. Arquitetura do Sistema

### Diagrama de alto nível

```text
┌───────────────────────────────────────────────────────────────┐
│ Frontend — Vercel / CDN                                       │
│ Vite/React ou Next.js App Router                              │
│ MapLibre + MapTiler                                           │
│ TanStack Query + Zustand                                      │
│ SSE client / REST commands                                    │
└───────────────────────┬───────────────────────────────────────┘
                        │ HTTPS
┌───────────────────────▼───────────────────────────────────────┐
│ Backend — Hostinger VPS KVM 4                                 │
│ FastAPI + Uvicorn                                             │
│ Dramatiq workers                                              │
│ PostgreSQL 16 + PostGIS                                       │
│ Redis                                                         │
│ Valhalla                                                      │
│ OTP 2                                                         │
│ Playwright worker                                             │
│ Billing atual: Pix                                            │
│ Billing futuro: Stripe                                        │
└───────────────────────┬───────────────────────────────────────┘
                        │
              ┌─────────▼─────────┐
              │ R2 / S3           │
              │ relatórios        │
              │ artefatos         │
              └───────────────────┘
```

### Estrutura do monorepo

```text
find-ideal-estate/
  apps/
    web/
    api/
  packages/
    contracts/
    design-system/
  infra/
    docker/
    migrations/
    seeds/
  docs/
```

### Módulos principais do backend

```text
apps/api/src/
  modules/
    auth/
    billing/              ← Pix agora; Stripe depois
    plans/
    usage_limits/
    journeys/
    jobs/
    transport/
    zones/
    urban_analysis/
    pois/
    listings/
    favorites/
    reports/
    datasets/
```

### Regra arquitetural de billing

A lógica de plano não deve depender de Stripe ou Pix diretamente.

Separação obrigatória:

```text
plans/entitlements  → define o que o usuário pode fazer
billing/            → recebe pagamento e ativa plano
credits/            → concede e consome créditos
subscriptions/      → representa ciclo ativo do plano
providers/pix       → implementação Pix
providers/stripe    → implementação futura
```

### Regras de dependência entre módulos

```
Permitido:  api/routes  → módulos de domínio → módulos de infra
Proibido:   módulos de domínio importando de api/routes
Proibido:   módulos de infra importando de domínio

api/routes/*          → qualquer módulo de domínio
modules/journeys      → transport, zones, listings
modules/listings      → deduplication, usage_limits
modules/zones         → urban_analysis, pois, transport
modules/transport     → NÃO importa de zones, listings, journeys
modules/deduplication → NÃO importa de listings
```

**Regra de DTO:** módulos nunca importam modelos internos de outros módulos.
Toda comunicação entre módulos usa DTOs de `packages/contracts/`.

### Injeção de dependência

- **Fases 0–3:** composição manual no `lifespan` do FastAPI (até ~5 módulos ativos).
- **Fase 4+:** `dependency-injector` — Container/Provider explícito e auditável.
  Migração incremental por módulo, iniciando com o domínio de transporte e zonas.

---

## 4. Infraestrutura e Deploy

### Topologia inicial

| Serviço | Plataforma | Observação |
|---|---|---|
| Frontend | Vercel | CDN, preview e deploy simples |
| API + workers + DB + Redis | Hostinger VPS KVM 4 | Topologia inicial |
| Valhalla / OTP | Hostinger VPS | Self-hosted |
| Object Storage | R2 / S3 | Relatórios e artefatos |
| Billing atual | Pix | QR Code / copia e cola |
| Billing futuro | Stripe | Automação de recorrência |

### Variáveis de ambiente obrigatórias — fase Pix

```env
DATABASE_URL=
REDIS_URL=
MAPBOX_ACCESS_TOKEN=
MAPTILER_API_KEY=
VALHALLA_URL=
OTP_URL=
R2_BUCKET=
S3_BUCKET=

PIX_PROVIDER=manual
PIX_KEY=
PIX_MERCHANT_NAME=
PIX_MERCHANT_CITY=
PIX_PAYMENT_EXPIRATION_MINUTES=60
PIX_STATIC_QR_CODE_URL=
PIX_COPY_PASTE_PAYLOAD=
PIX_CALLBACK_SECRET=
```

### Variáveis de ambiente futuras — Stripe

```env
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_BASICO=
STRIPE_PRICE_PRO=
STRIPE_PRICE_PRO_MAX=
```

> As variáveis Stripe permanecem documentadas, mas não são requisito da primeira versão de cobrança.

### Bright Data

Escape hatch manual, nunca base da arquitetura.

- **Habilitar** para uma plataforma quando, na janela de 24h: `success_rate < 85%`
  OU `empty_result_rate > 20%` em zonas com histórico não vazio.
- **Desabilitar** após 72h consecutivas com `success_rate >= 95%`
  e `empty_result_rate <= 10%`.

---

## 5. Modelo de Dados

### Diagrama de relações

```text
users
  ├─ user_sessions
  ├─ journeys
  ├─ user_listing_favorites
  ├─ user_zone_favorites
  ├─ user_credits
  ├─ plan_activations
  └─ payments

plans
  └─ plan_entitlements

payments
  ├─ pix_payment_data
  └─ (future stripe references)

plan_activations
  └─ credit_ledger

pro_max_refresh_targets
  └─ user favorites

journeys
  └─ jobs ── job_events

transport_points ── zones
zones
  ├─ zone_listing_caches ── properties ── listing_ads
  │                              └─ listing_snapshots
  └─ listing_search_requests

dataset_versions
external_usage_ledger
scraping_degradation_events
webhook_events
pro_max_refresh_runs
```

### Diretriz de dados

O modelo de dados deve suportar Pix agora e Stripe depois. Portanto, pagamentos devem ser modelados de forma genérica, e o plano ativo do usuário não deve depender do método de pagamento.

### `users`

```sql
users (
  id                   UUID PRIMARY KEY,
  email                TEXT UNIQUE NOT NULL,        -- normalizado em lowercase
  display_name         TEXT,
  password_hash        TEXT,                        -- PBKDF2-HMAC-SHA256, 600 000 iter
  password_updated_at  TIMESTAMPTZ,
  google_subject       TEXT UNIQUE,                 -- sub do ID token Google (migration 0033)
  email_verified_at    TIMESTAMPTZ,                 -- preenchido no login Google (migration 0033)
  role                 TEXT NOT NULL DEFAULT 'user', -- 'user' | 'proprietario' (migration 0028)
  is_active            BOOLEAN DEFAULT true,
  is_superuser         BOOLEAN DEFAULT false,
  created_at           TIMESTAMPTZ DEFAULT NOW(),
  updated_at           TIMESTAMPTZ DEFAULT NOW()
)
-- UNIQUE INDEX em lower(email)
-- UNIQUE INDEX em google_subject
```

### `user_sessions`

```sql
user_sessions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  token_hash   TEXT UNIQUE NOT NULL,    -- SHA-256 do token opaco
  expires_at   TIMESTAMPTZ NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
-- INDEX em user_id, INDEX em expires_at
```

TTL padrão: 30 dias. Cookie HTTP-only `auth_session` com `samesite=lax`.

### `journeys`

```sql
journeys (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                     UUID REFERENCES users(id),       -- NULL se anônimo
  anonymous_session_id        TEXT,                            -- NULL se autenticado
  state                       TEXT NOT NULL DEFAULT 'draft',   -- JourneyState
  input_snapshot              JSONB,
  selected_transport_point_id UUID,
  selected_zone_id            UUID,
  selected_property_id        UUID,
  last_completed_step         INT,
  secondary_reference_point   GEOMETRY(Point, 4326),           -- trabalho, escola
  secondary_reference_label   TEXT,
  created_at                  TIMESTAMPTZ DEFAULT NOW(),
  updated_at                  TIMESTAMPTZ DEFAULT NOW(),
  expires_at                  TIMESTAMPTZ                      -- TTL anônimo: 7 dias
)
```

**`JourneyState`:** `draft → active ↔ processing → cancelled → active → completed | expired`

### `jobs`

```sql
jobs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  journey_id          UUID REFERENCES journeys(id),
  job_type            TEXT NOT NULL,    -- JobType enum
  state               TEXT NOT NULL DEFAULT 'pending',  -- JobState enum
  progress_percent    INT DEFAULT 0,
  current_stage       TEXT,
  cancel_requested_at TIMESTAMPTZ,
  started_at          TIMESTAMPTZ,
  finished_at         TIMESTAMPTZ,
  worker_id           TEXT,
  result_ref          JSONB,
  error_code          TEXT,
  error_message       TEXT,
  created_at          TIMESTAMPTZ DEFAULT NOW()
)
```

**`JobType`:**
`transport_search · zone_generation · zone_enrichment · listings_scrape ·`
`listings_dedup · listings_prewarm · report_generate`

**`JobState`:**
`pending → running → completed | failed | retrying → pending | cancelled`

### `job_events`

```sql
job_events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id       UUID REFERENCES jobs(id),
  event_type   TEXT NOT NULL,
  stage        TEXT,
  message      TEXT,
  payload_json JSONB,
  created_at   TIMESTAMPTZ DEFAULT NOW()
)
```

Retenção: 30–90 dias. Fonte de verdade para reconexão SSE via `Last-Event-ID`.

### `transport_points`

```sql
transport_points (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  journey_id      UUID REFERENCES journeys(id),
  source          TEXT NOT NULL,  -- 'gtfs_stop' | 'metro_station' | 'train_station'
  external_id     TEXT,
  name            TEXT,
  location        GEOMETRY(Point, 4326),
  walk_time_sec   INT,
  walk_distance_m INT,
  route_ids       TEXT[],
  modal_types     TEXT[],
  created_at      TIMESTAMPTZ DEFAULT NOW()
)
-- INDEX GIST em location
```

### `zones`

```sql
zones (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  journey_id           UUID REFERENCES journeys(id),
  transport_point_id   UUID REFERENCES transport_points(id),
  modal                TEXT NOT NULL,        -- 'walking' | 'transit' | 'car'
  max_time_minutes     INT NOT NULL,
  radius_meters        INT NOT NULL,
  fingerprint          TEXT NOT NULL UNIQUE, -- SHA-256 canônico
  isochrone_geom       GEOMETRY(POLYGON, 4326),
  dataset_version_id   UUID REFERENCES dataset_versions(id),
  state                TEXT NOT NULL DEFAULT 'pending',
  -- campos de enriquecimento
  green_area_m2        FLOAT,
  flood_area_m2        FLOAT,
  safety_incidents_count INT,
  poi_counts           JSONB,   -- {"restaurants": 12, "schools": 3, ...}
  badges               JSONB,   -- ZoneBadgeValue por critério
  badges_provisional   BOOLEAN DEFAULT true,
  created_at           TIMESTAMPTZ DEFAULT NOW(),
  updated_at           TIMESTAMPTZ DEFAULT NOW()
)
-- INDEX GIST em isochrone_geom
```

**Fingerprint:** SHA-256 do JSON canônico `{lat, lon, modal, max_time, radius, dataset_v}`,
lat/lon arredondados para 5 casas decimais (~1m precisão).
Zonas são reutilizadas entre jornadas de usuários diferentes quando o fingerprint coincidir.

### `properties`

```sql
properties (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  address_normalized   TEXT,
  location             GEOMETRY(Point, 4326),
  area_m2              FLOAT,
  bedrooms             INT,
  bathrooms            INT,
  parking              INT,
  usage_type           TEXT,          -- 'residential' | 'commercial' | 'mixed' | 'unknown'
  usage_type_inferred  BOOLEAN DEFAULT false,
  geo_hash             TEXT,
  fingerprint          TEXT NOT NULL UNIQUE,
  created_at           TIMESTAMPTZ DEFAULT NOW()
)
-- INDEX GIST em location
```

### `listing_ads`

```sql
listing_ads (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id           UUID REFERENCES properties(id),
  platform              TEXT NOT NULL,  -- 'quintoandar' | 'zapimoveis' | 'vivareal'
  platform_listing_id   TEXT NOT NULL,
  url                   TEXT,
  advertised_usage_type TEXT,
  first_seen_at         TIMESTAMPTZ DEFAULT NOW(),
  last_seen_at          TIMESTAMPTZ DEFAULT NOW(),
  is_active             BOOLEAN DEFAULT true,
  UNIQUE (platform, platform_listing_id)
)
```

### `listing_snapshots`

```sql
listing_snapshots (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_ad_id     UUID REFERENCES listing_ads(id),
  observed_at       TIMESTAMPTZ DEFAULT NOW(),
  price             NUMERIC(12,2),
  condo_fee         NUMERIC(10,2),
  iptu              NUMERIC(10,2),
  availability_state TEXT,
  raw_payload       JSONB
)
```

Retenção: brutos 30 dias; normalizados de preço retenção longa.

### `zone_listing_caches`

```sql
zone_listing_caches (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zone_fingerprint     TEXT NOT NULL,
  config_hash          TEXT NOT NULL,
  status               TEXT NOT NULL DEFAULT 'pending',  -- ZoneCacheStatus
  platforms_completed  TEXT[],
  platforms_failed     TEXT[],
  coverage_ratio       FLOAT,
  preliminary_count    INT,
  scraped_at           TIMESTAMPTZ,
  expires_at           TIMESTAMPTZ,   -- aluguel: +12h, compra: +24h
  created_at           TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (zone_fingerprint, config_hash)
)
```

**`ZoneCacheStatus`:**
`pending → scraping → partial → complete | failed | cancelled_partial`

### `user_credits`

```sql
user_credits (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                UUID REFERENCES users(id) UNIQUE NOT NULL,
  plan_id                UUID REFERENCES plans(id),

  -- Buckets independentes (consumo FIFO: cycle → rollover → legacy)
  cycle_credits          INT NOT NULL DEFAULT 0,    -- cota mensal do plano (expira no fim do ciclo)
  rollover_balance       INT NOT NULL DEFAULT 0,    -- até 25% da cota anterior, expira no fim do ciclo seguinte
  legacy_balance         INT NOT NULL DEFAULT 0,    -- top-ups avulsos / migração de créditos pré-2.3 (não expira)

  cycle_started_at       TIMESTAMPTZ,
  cycle_ends_at          TIMESTAMPTZ,
  monthly_quota          INT,                       -- cache da cota do plano vigente
  updated_at             TIMESTAMPTZ DEFAULT NOW()
)
-- INDEX em cycle_ends_at para o job noturno de expiração/concessão
```

Saldo total = `cycle_credits + rollover_balance + legacy_balance`. Toda alteração passa por `credit_ledger` em transação atômica.

### `credit_ledger`

```sql
credit_ledger (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID REFERENCES users(id) NOT NULL,
  bucket        TEXT NOT NULL,          -- 'cycle' | 'rollover' | 'legacy'
  delta         INT NOT NULL,           -- positivo = crédito; negativo = débito
  reason        TEXT NOT NULL,
  -- Razões válidas:
  --   'signup_grant_free' | 'anonymous_balance_discarded'
  --   'pix_plan_activation' | 'pix_plan_renewal' | 'manual_plan_adjustment'
  --   'monthly_grant' | 'monthly_expire' | 'rollover_grant' | 'rollover_expire'
  --   'topup_purchase' | 'legacy_migration'
  --   'step_zone_generation' | 'step_zone_enrichment' | 'step_listings_cache'
  --   'step_listings_scrape' | 'step_report'
  --   'pro_max_refresh'
  reference_id  UUID,                   -- job_id, journey_id, payment_id, activation_id
  balance_after INT NOT NULL,           -- saldo total após a operação
  created_at    TIMESTAMPTZ DEFAULT NOW()
)
-- INDEX em (user_id, created_at DESC)
```

> **Nota:** operações de refresh (`pro_max_refresh`) são registradas como entradas com `delta = 0` para manter histórico auditável sem afetar saldo.

### `payments`

Tabela genérica para Pix agora e Stripe depois.

```sql
payments (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID REFERENCES users(id) NOT NULL,
  plan_id               UUID REFERENCES plans(id),
  payment_provider      TEXT NOT NULL, -- pix | stripe
  payment_method        TEXT NOT NULL, -- pix_qr_code | stripe_checkout
  payment_type          TEXT NOT NULL, -- plan_activation | plan_renewal | topup
  amount_brl            NUMERIC(8,2) NOT NULL,
  status                TEXT NOT NULL DEFAULT 'pending',
  -- pending | paid | failed | expired | cancelled | refunded

  external_reference    TEXT,
  external_payment_id   TEXT,

  created_at            TIMESTAMPTZ DEFAULT NOW(),
  expires_at            TIMESTAMPTZ,
  paid_at               TIMESTAMPTZ,
  cancelled_at          TIMESTAMPTZ,
  refunded_at           TIMESTAMPTZ
)
```

### `pix_payment_data`

```sql
pix_payment_data (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_id          UUID REFERENCES payments(id) ON DELETE CASCADE NOT NULL,
  pix_key             TEXT,
  merchant_name       TEXT,
  merchant_city       TEXT,
  qr_code_payload     TEXT,
  pix_copy_paste      TEXT,
  qr_code_image_url   TEXT,
  provider_payload    JSONB,
  created_at          TIMESTAMPTZ DEFAULT NOW()
)
```

### `plan_activations`

Representa o ciclo ativo de plano, independentemente do método de pagamento.

```sql
plan_activations (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID REFERENCES users(id) NOT NULL,
  plan_id            UUID REFERENCES plans(id) NOT NULL,
  source_payment_id  UUID REFERENCES payments(id),
  status             TEXT NOT NULL DEFAULT 'active',
  -- active | expired | cancelled | replaced | manual
  started_at         TIMESTAMPTZ NOT NULL,
  ends_at            TIMESTAMPTZ NOT NULL,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
)
```

### `external_usage_ledger`

```sql
external_usage_ledger (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider       TEXT NOT NULL,
  operation_type TEXT NOT NULL,
  user_id        UUID,
  session_id     TEXT,
  journey_id     UUID,
  units          INT DEFAULT 1,
  estimated_cost NUMERIC(8,4),
  cache_hit      BOOLEAN DEFAULT false,
  status         TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
)
```

### `dataset_versions`

```sql
dataset_versions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_type TEXT NOT NULL,   -- 'gtfs_sptrans' | 'osm_sp' | 'geosampa_flood' | ...
  version_hash TEXT NOT NULL,   -- SHA-256 do arquivo fonte
  source_url   TEXT,
  imported_at  TIMESTAMPTZ DEFAULT NOW(),
  is_current   BOOLEAN DEFAULT false,
  metadata     JSONB
)
```

### `listing_search_requests`

```sql
listing_search_requests (
  id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  journey_id                 UUID,
  user_id                    UUID,
  session_id                 TEXT,
  zone_fingerprint           TEXT NOT NULL,
  search_location_normalized TEXT NOT NULL,
  search_location_label      TEXT NOT NULL,
  search_location_type       TEXT NOT NULL,   -- 'street' | 'neighborhood' | 'address' | 'landmark'
  search_type                TEXT NOT NULL,   -- 'rental' | 'sale'
  usage_type                 TEXT NOT NULL,   -- 'residential' | 'commercial' | 'all'
  platforms_hash             TEXT NOT NULL,
  result_source              TEXT NOT NULL,   -- 'cache_hit' | 'cache_partial' | 'cache_miss' | 'fresh_scrape'
  requested_at               TIMESTAMPTZ DEFAULT NOW()
)
```

**Regra fechada:** esta tabela registra toda tentativa de busca de imóveis **confirmada pelo clique em "Buscar imóveis" na Etapa 5**. O prewarm noturno considera **apenas** os endereços/search locations pesquisados nas últimas 24 horas. Não existe fallback por zona popular, geohash, região ou cold start artificial.

### `scraping_degradation_events`

```sql
scraping_degradation_events (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  platform            TEXT NOT NULL,
  event_type          TEXT NOT NULL,  -- 'degraded' | 'recovered'
  trigger_metric      TEXT,
  metric_value        FLOAT,
  bright_data_enabled BOOLEAN DEFAULT false,
  created_at          TIMESTAMPTZ DEFAULT NOW()
)
```

### `webhook_events`

```sql
webhook_events (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider       TEXT NOT NULL, -- pix | stripe | mobility_db
  event_id       TEXT,
  event_type     TEXT NOT NULL,
  payload        JSONB,
  processed      BOOLEAN DEFAULT false,
  processed_at   TIMESTAMPTZ,
  error          TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (provider, event_id)
)
```

### `user_listing_favorites`

```sql
user_listing_favorites (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  listing_key         TEXT NOT NULL,               -- chave opaca do imóvel favorito
  journey_id          UUID NOT NULL,
  zone_fingerprint    TEXT NOT NULL,
  search_type         TEXT NOT NULL,               -- 'rental' | 'sale'
  usage_type          TEXT NOT NULL,               -- 'residential' | 'commercial' | 'all'
  listing_payload     JSONB NOT NULL,              -- snapshot do card (preço, endereço, plataforma…)

  -- Endereço normalizado (usado pelo prewarm Pro e pelo refresh Pro Max)
  address_normalized  TEXT,
  property_id         UUID REFERENCES properties(id),

  -- Versionamento de snapshot
  snapshot_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_refreshed_at   TIMESTAMPTZ,                 -- atualizado pela run noturna (Pro) ou refresh dedicado (Pro Max)
  last_viewed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  priority_flag       BOOLEAN NOT NULL DEFAULT false,

  -- Retenção por plano (Free=7 dias, Básico/Pro/Pro Max=30 dias)
  view_window_ends_at TIMESTAMPTZ,                 -- saved_at + retention_days do plano vigente no save
  view_state          TEXT NOT NULL DEFAULT 'visible', -- 'visible' | 'expired_for_view' | 'over_limit_grace' | 'archived'

  saved_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_user_listing_favorites_user_key UNIQUE (user_id, listing_key)
)
-- INDEX em (user_id, saved_at DESC)
-- INDEX em (user_id, view_window_ends_at) WHERE view_state = 'visible'
-- INDEX em (address_normalized) WHERE address_normalized IS NOT NULL
```

### `user_zone_favorites`

```sql
user_zone_favorites (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  zone_key            TEXT NOT NULL,               -- chave opaca da zona favorita
  journey_id          UUID NOT NULL,
  zone_fingerprint    TEXT NOT NULL,
  search_type         TEXT NOT NULL,
  usage_type          TEXT NOT NULL,
  zone_payload        JSONB NOT NULL,              -- snapshot da zona (badges, métricas…)

  snapshot_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_refreshed_at   TIMESTAMPTZ,
  last_viewed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  priority_flag       BOOLEAN NOT NULL DEFAULT false,

  view_window_ends_at TIMESTAMPTZ,
  view_state          TEXT NOT NULL DEFAULT 'visible',

  saved_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_user_zone_favorites_user_key UNIQUE (user_id, zone_key)
)
-- INDEX em (user_id, saved_at DESC)
-- INDEX em (user_id, view_window_ends_at) WHERE view_state = 'visible'
```

### `plans`

```sql
plans (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug              TEXT UNIQUE NOT NULL, -- anonymous | free | basico | pro | pro_max
  name              TEXT NOT NULL,
  price_brl         NUMERIC(8,2),
  monthly_credits   INT NOT NULL DEFAULT 0,
  is_paid           BOOLEAN NOT NULL DEFAULT false,
  stripe_price_id   TEXT, -- futuro, opcional
  display_order     INT NOT NULL DEFAULT 0,
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ DEFAULT NOW()
)
```

### Seed inicial de planos

| slug | name | price_brl | monthly_credits | is_paid |
|---|---|---:|---:|---|
| anonymous | Anônimo | NULL | 300 | false |
| free | Free cadastrado | 0 | 350 | false |
| basico | Básico | 21.99 | 800 | true |
| pro | Pro | 90.99 | 4000 | true |
| pro_max | Pro Max | 312.99 | 20000 | true |

### `plan_entitlements`

```sql
plan_entitlements (
  plan_id                         UUID PRIMARY KEY REFERENCES plans(id) ON DELETE CASCADE,

  max_listing_favorites           INT,
  max_zone_favorites              INT,
  retention_days                  INT NOT NULL,

  can_customize_radius            BOOLEAN NOT NULL DEFAULT false,
  can_customize_max_time          BOOLEAN NOT NULL DEFAULT false,
  can_customize_distance          BOOLEAN NOT NULL DEFAULT false,

  max_active_metrics              INT,
  zone_selection_policy           TEXT NOT NULL, -- restricted | any

  auto_refresh_policy             TEXT NOT NULL, -- none | managed_queue
  pro_max_refresh_max_zones       INT,
  pro_max_refresh_max_listings    INT,
  pro_max_refresh_cadence_days    INT,
  pro_max_refresh_eligibility_days INT,

  rollover_percent                INT NOT NULL DEFAULT 0,
  rollover_cycles                 INT NOT NULL DEFAULT 0,
  cycle_length_days               INT NOT NULL DEFAULT 30
)
```

### Entitlements por plano

| Plano | Imóveis | Zonas | Retenção | Parametrização | Métricas | Zonas | Refresh |
|---|---:|---:|---:|---|---|---|---|
| Anônimo | 0 | 0 | 7 dias sessão | travada | default | restrito | none |
| Free | 5 | 2 | 7 dias | travada | default | 2 linhas | none |
| Básico | 20 | 4 | 30 dias | liberada com limite | 4 | qualquer zona | none |
| Pro | 100 | 20 | 30 dias | liberada | ilimitadas | qualquer zona | none |
| Pro Max | 100 | 20 | 30 dias | liberada | ilimitadas | qualquer zona | none |

### `plan_activations` (v2.4 — substitui `subscriptions`)

> **v2.4:** as tabelas `subscriptions` e `subscription_events` foram substituídas por `plan_activations`. A lógica de ciclo ativo de plano não depende mais de Stripe; pagamentos são modelados em `payments` + `pix_payment_data`.

```sql
plan_activations (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID REFERENCES users(id) NOT NULL,
  plan_id            UUID REFERENCES plans(id) NOT NULL,
  source_payment_id  UUID REFERENCES payments(id),
  status             TEXT NOT NULL DEFAULT 'active',
  -- active | expired | cancelled | replaced | manual
  started_at         TIMESTAMPTZ NOT NULL,
  ends_at            TIMESTAMPTZ NOT NULL,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
)
```

> **Nota de compatibilidade:** referências a `subscriptions` no código legado devem ser migradas para `plan_activations`. Referências a `subscription_events` devem ser migradas para `credit_ledger` + `webhook_events`.

### `subscription_events` (legado — removido em v2.4)

> Mantido apenas para referência de migração. A tabela foi substituída pelo fluxo `payments → plan_activations → credit_ledger`. O campo `stripe_event_id` foi absorvido por `webhook_events (provider, event_id)`.

```sql
-- LEGADO: não criar em novos ambientes
subscription_events (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subscription_id     UUID,  -- era REFERENCES subscriptions(id)
  event_type          TEXT NOT NULL,
  from_plan_id        UUID REFERENCES plans(id),
  to_plan_id          UUID REFERENCES plans(id),
  stripe_event_id     TEXT,
  payload             JSONB,
  created_at          TIMESTAMPTZ DEFAULT NOW()
)
```

### `pro_max_refresh_targets`

Itens elegíveis ao refresh automático do plano Pro Max. Atualizado via triggers de favorito (insert/update/delete) e por job de revisão de elegibilidade.

```sql
pro_max_refresh_targets (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  target_kind              TEXT NOT NULL,   -- 'listing' | 'zone'
  listing_favorite_id      UUID REFERENCES user_listing_favorites(id) ON DELETE CASCADE,
  zone_favorite_id         UUID REFERENCES user_zone_favorites(id) ON DELETE CASCADE,
  is_active                BOOLEAN NOT NULL DEFAULT true,
  is_priority              BOOLEAN NOT NULL DEFAULT false,
  last_refreshed_at        TIMESTAMPTZ,
  next_refresh_due_at      TIMESTAMPTZ NOT NULL,
  last_attempt_status      TEXT,            -- 'success' | 'partial' | 'failed' | 'skipped_quota'
  failure_count            INT NOT NULL DEFAULT 0,
  created_at               TIMESTAMPTZ DEFAULT NOW(),
  updated_at               TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT chk_target_xor CHECK (
    (target_kind = 'listing' AND listing_favorite_id IS NOT NULL AND zone_favorite_id IS NULL)
    OR (target_kind = 'zone' AND zone_favorite_id IS NOT NULL AND listing_favorite_id IS NULL)
  )
)
-- INDEX em (user_id, is_active, next_refresh_due_at)
-- INDEX em (next_refresh_due_at) WHERE is_active = true
```

### `pro_max_refresh_runs`

Log de execuções do scheduler dedicado do Pro Max — telemetria e auditoria.

```sql
pro_max_refresh_runs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  status              TEXT NOT NULL DEFAULT 'running',
  -- 'running' | 'success' | 'success_empty' | 'partial' | 'failed'
  targets_total       INT NOT NULL DEFAULT 0,
  targets_succeeded   INT NOT NULL DEFAULT 0,
  targets_failed      INT NOT NULL DEFAULT 0,
  targets_skipped     INT NOT NULL DEFAULT 0,
  notes               TEXT
)
```

---

## 6. Fontes de Dados Geoespaciais

### GeoSampa (`.gpkg` locais em `data_cache/geosampa/`)

| Arquivo | Conteúdo | Uso no produto |
|---|---|---|
| `geoportal_corredor_onibus_v2.gpkg` | Corredores de ônibus | Layer de transporte no mapa |
| `geoportal_estacao_metro_v2.gpkg` | Estações de metrô | Pontos de transporte elegíveis |
| `geoportal_estacao_trem_v2.gpkg` | Estações de trem | Pontos de transporte elegíveis |
| `geoportal_linha_metro_v4.gpkg` | Linhas de metrô | Layer de rede no mapa |
| `geoportal_linha_trem_v2.gpkg` | Linhas de trem | Layer de rede no mapa |
| `geoportal_mancha_inundacao_25.gpkg` | Áreas de risco de alagamento (polígonos) | Enriquecimento: `flood_area_m2` |
| `geoportal_ponto_onibus.gpkg` | Paradas de ônibus individuais | Pontos elegíveis (modal ônibus) |
| `geoportal_terminal_onibus_v2.gpkg` | Terminais de ônibus | Pontos elegíveis (prioridade alta) |
| `SIRGAS_GPKG_linhaonibus.gpkg` | Geometrias de linhas de ônibus | Layer de rede no mapa |
| `SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg` | Vegetação significativa (polígonos) | Enriquecimento: `green_area_m2` |

**Ingestão:** `ogr2ogr` → PostGIS, versionado em `dataset_versions`.
**Frequência:** conforme atualização GeoSampa (tipicamente semestral).

### GTFS SPTrans (feed local em `data_cache/gtfs/`)

| Arquivo | Conteúdo |
|---|---|
| `stops.txt` | 22.094 paradas — `stop_id, stop_name, stop_desc, stop_lat, stop_lon` |
| `routes.txt` | 1.345 linhas — `route_id, agency_id, route_short_name, route_long_name, route_type, route_color, route_text_color` |
| `stop_times.txt` | Horários de passagem |
| `trips.txt` | Viagens por linha |
| `shapes.txt` | Geometrias de percurso |
| `agency.txt` | Operadoras |
| `calendar.txt` | Calendário de operação |
| `fare_attributes.txt` / `fare_rules.txt` | Tarifas |
| `frequencies.txt` | Frequência por período |

**Fontes via Mobility Database:**
`mdb-559` (SPTrans), `mdb-560` (Metrô SP). Webhook dispara ingestão automática.

### ObservaSampa

`data_cache/observasampa/ObservaSampaDadosAbertosIndicadoresCSV.csv`
— Indicadores urbanos abertos de São Paulo.
Uso: dashboard de zona, indicadores socioeconômicos complementares.
Frequência: semestral/anual.

### OSM (OpenStreetMap)

- Base viária e geometrias necessárias para construir o grafo local do Valhalla.
- Não é fonte primária de POIs no produto.
- Uso principal: rotas, isócronas e apoio geoespacial ao motor local.
- Frequência: mensal (snapshot Geofabrik BR), apenas para rebuild do grafo e suporte cartográfico/local.

### Mapbox Search Box API — POIs por categoria

- Fonte operacional dos POIs exibidos e analisados pelo produto.
- Endpoint principal: **Category Search** (`/searchbox/v1/category/{canonical_category_id}`), com resolução prévia de categorias via `list/category`.
- Busca orientada por **ponto + raio/bbox**, como já ocorre no legado (`pois_categoria_raio.py`).
- Categorias iniciais: supermercados, academias, parques, farmácias, mercados e restaurantes.
- Persistência: **somente cache/resultado derivado por zona/jornada**, nunca dataset-base da cidade.
- Política de retenção: TTL curto e reaproveitamento apenas para reduzir custo/latência da experiência.

---

## 7. Pipeline ETL

### Fluxo por fonte

```
Mobility Database webhook
  → download GTFS zip
  → hash check → [iguais: encerra sem reprocessar]
  → staging tables PostGIS
  → validação consistência (shapes, stop_times, trips)
  → transação de substituição atômica
  → dataset_versions registro
  → Redis cache invalidation (transport points por área)
  → OTP reload no Hostinger VPS

GeoSampa (manual / semestral)
  → ogr2ogr → PostGIS staging
  → ST_IsValid em todas as geometrias
  → transação de substituição atômica
  → dataset_versions registro

OSM (mensal via Geofabrik)
  → import dos dados viários necessários ao ambiente geoespacial local
  → Valhalla graph rebuild (offline, < 30 min)
  → dataset_versions registro
  → zonas existentes: mantêm versão anterior registrada na zona

Mapbox Search Box API (sob demanda, sem ingestão massiva)
  → resolve categorias via `list/category` quando necessário
  → consulta POIs por categoria com `category/{canonical_category_id}`
  → normaliza resposta por zona/jornada
  → persiste apenas cache efêmero / resultado derivado
  → agrega `poi_counts` e detalhes exibíveis na UI

ObservaSampa (manual)
  → CSV import → tabela analytics
  → dataset_versions registro
```

### Tabelas PostGIS para GTFS

```sql
gtfs_stops      (stop_id, stop_name, stop_lat, stop_lon, location GEOMETRY(Point,4326))
gtfs_routes     (route_id, route_short_name, route_long_name, route_type)
gtfs_trips      (trip_id, route_id, shape_id)
gtfs_stop_times (trip_id, stop_id, arrival_time, departure_time, stop_sequence)
gtfs_shapes     (shape_id, shape_pt_sequence, location GEOMETRY(Point,4326))
```

**Índice GIST obrigatório em `gtfs_stops.location`** — `ST_DWithin` por raio é a consulta
mais frequente do produto; sem índice vira full scan de 22k linhas.

---

## 8. Especificação do Backend

### Filas Dramatiq

| Fila | Concorrência | Worker | Justificativa |
|---|---|---|---|
| `transport` | 4 | worker-general (Hostinger) | Leve, PostGIS local |
| `zones` | 2 | worker-general (Hostinger) | Valhalla CPU-bound; isócrona de carro ~1GB RAM temporária |
| `enrichment` | 4 | worker-general (Hostinger) | PostGIS paralelizável por zona |
| `scrape_browser` | 1 | worker-scrape-browser (Hostinger) | Playwright: ~300MB RAM, 1 browser |
| `scrape_http` | 4 | worker-scrape-browser (Hostinger) | httpx sem browser (quando implementado) |
| `deduplication` | 2 | worker-general (Hostinger) | CPU + DB |
| `reports` | 1 | worker-general (Hostinger) | WeasyPrint: 400–600MB RAM |
| `prewarm` | — | worker-general (Hostinger) | Prioridade LOW, cede para USER_REQUEST |
| `pro_max_refresh` | 1 | worker-general (Hostinger) | Prioridade entre PREWARM e USER_REQUEST; cadência semanal por item |
| `billing` | 2 | worker-general (Hostinger) | Pix agora; Stripe depois — ativação/expiração de ciclo |

**Prioridades:** `USER_REQUEST = 0` (mais alto) · `PRO_MAX_REFRESH = 3` · `PREWARM = 5` (mais baixo). `BILLING = 0` (mesma prioridade que USER_REQUEST). Pro Max precisa terminar dentro da janela noturna (03:00–05:30) sem competir com requisições de usuário; o prewarm geral cede para ambos.

**JobType estendido (v2.4):** `pro_max_refresh_listing`, `pro_max_refresh_zone`, `monthly_grant`, `monthly_expire`, `pix_payment_confirm`, `plan_activation`.

### Política de retry

```python
class JobRetryPolicy:
    TRANSPORT_SEARCH = dict(max_retries=2, backoff_seconds=[5, 30])
    ZONE_GENERATION  = dict(max_retries=1, backoff_seconds=[10])
    ENRICHMENT       = dict(max_retries=2, backoff_seconds=[5, 15])
    SCRAPING         = dict(max_retries=3, backoff_seconds=[10, 30, 60])
    DEDUPLICATION    = dict(max_retries=2, backoff_seconds=[5, 10])
    REPORT           = dict(max_retries=1, backoff_seconds=[15])
```

### Eventos SSE

| Evento | Quando emitido |
|---|---|
| `job.started` | Worker inicia o job |
| `job.stage.started` | Início de cada sub-etapa |
| `job.stage.progress` | Progresso percentual dentro da etapa |
| `job.partial_result.ready` | Resultado parcial disponível (ex: primeira zona) |
| `zone.badges.updated` | Badge provisório após enriquecimento individual de zona |
| `zones.badges.finalized` | Recálculo final com mediana real de todas as zonas |
| `listings.preliminary.ready` | Resultado preliminar de cache disponível |
| `listings.diff.applied` | Diff de revalidação aplicado |
| `job.stage.completed` | Sub-etapa concluída |
| `job.cancelled` | Cancelamento confirmado |
| `job.failed` | Erro não recuperável após retries |
| `job.completed` | Job concluído com sucesso |
| `report.ready` | PDF pronto, signed URL disponível |

### Fan-out SSE (múltiplos processos na Hostinger)

```python
# Worker (qualquer processo)
async def publish_event(job_id: UUID, event: JobEvent):
    await redis.publish(f"job:{job_id}", event.model_dump_json())
    await db.insert_job_event(event)        # persiste para reconexão

# API — endpoint SSE (qualquer instância)
async def job_events_stream(job_id: UUID, request: Request):
    async with redis.subscribe(f"job:{job_id}") as channel:
        async for message in channel:
            if await request.is_disconnected():
                break
            yield f"data: {message}\n\n"
```

Reconexão via `Last-Event-ID`: API reenvia eventos perdidos de `job_events` antes de
assinar o canal Redis. Sem sticky sessions necessárias.

### Cancelamento cooperativo

```
t=0      Usuário pressiona cancelar
t=0      API: grava cancel_requested_at, responde 202 imediatamente
t=0–2s   Worker: verifica flag no início de cada sub-etapa
t=2s     Worker: encerra sub-etapa de forma limpa ao detectar flag
t=2–5s   Worker: persiste resultado parcial, status → cancelled_partial
t=5s     Worker: libera lock de scraping
t=30s    Watchdog: força cancelled_partial se worker não confirmou
```

Watchdog: scheduler a cada 60s, detecta jobs `running` sem heartbeat > 2min
(`job_heartbeat:{job_id}` no Redis, TTL 120s; worker publica a cada 30s).

### Controle de créditos por etapa monetizável

A v2.3 substitui custos finos por modal por **5 etapas monetizáveis × 20 créditos** (decisão de produto — ver Seção 11).

```python
class JourneyStep(str, Enum):
    ZONE_GENERATION   = "step_zone_generation"
    ZONE_ENRICHMENT   = "step_zone_enrichment"
    LISTINGS_CACHE    = "step_listings_cache"
    LISTINGS_SCRAPE   = "step_listings_scrape"
    REPORT            = "step_report"

STEP_COST = 20  # créditos por etapa monetizável (uniforme, independente de modal)

# Helpers de classificação
NON_MONETIZED_OPS = {"journey_config", "transport_search", "dashboard_view"}
```

**Consumo FIFO entre buckets** (`cycle_credits` → `rollover_balance` → `legacy_balance`).

```python
async def check_and_consume_credits(
    user_id: UUID | None,
    session_id: str | None,
    step: JourneyStep,
    reference_id: UUID | None = None,
) -> CreditResult:
    cost = STEP_COST

    if user_id is None:
        # Sessão anônima: 1 bucket único em Redis
        balance = int(await redis.get(f"credit:session:{session_id}") or 0)
        if balance < cost:
            raise InsufficientCreditsError(required=cost, balance=balance)
        new_balance = balance - cost
        await redis.set(f"credit:session:{session_id}", new_balance, ex=7 * 86400)
        return CreditResult(consumed=cost, balance=new_balance, plan="anonymous")

    # Usuário autenticado: lock de linha + débito FIFO
    async with db.transaction():
        row = await db.fetchrow(
            """SELECT cycle_credits, rollover_balance, legacy_balance, plan_id
                 FROM user_credits WHERE user_id=$1 FOR UPDATE""",
            user_id,
        )
        total = (row["cycle_credits"] or 0) + (row["rollover_balance"] or 0) + (row["legacy_balance"] or 0)
        if total < cost:
            raise InsufficientCreditsError(required=cost, balance=total)

        # FIFO: consome cycle, depois rollover, depois legacy
        remaining = cost
        debits: list[tuple[str, int]] = []
        for bucket in ("cycle_credits", "rollover_balance", "legacy_balance"):
            available = row[bucket] or 0
            if available <= 0:
                continue
            take = min(available, remaining)
            debits.append((bucket, take))
            remaining -= take
            if remaining == 0:
                break
        assert remaining == 0

        new_cycle    = row["cycle_credits"]    - sum(t for b, t in debits if b == "cycle_credits")
        new_rollover = row["rollover_balance"] - sum(t for b, t in debits if b == "rollover_balance")
        new_legacy   = row["legacy_balance"]   - sum(t for b, t in debits if b == "legacy_balance")
        new_total    = new_cycle + new_rollover + new_legacy

        await db.execute(
            """UPDATE user_credits
                  SET cycle_credits=$2, rollover_balance=$3, legacy_balance=$4, updated_at=NOW()
                WHERE user_id=$1""",
            user_id, new_cycle, new_rollover, new_legacy,
        )
        for bucket, take in debits:
            ledger_bucket = bucket.replace("_credits", "").replace("_balance", "")
            await db.execute(
                """INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                user_id, ledger_bucket, -take, step.value, reference_id, new_total,
            )

    return CreditResult(consumed=cost, balance=new_total, debits=debits)
```

### Enforcement de entitlements antes de operações de plano

Capabilities resolvidas no início de cada request por `PlanEntitlementService.resolve(user_id) → ResolvedEntitlements`. Cache em Redis (TTL 60s, invalidado em `subscription_events`).

```python
@dataclass(frozen=True)
class ResolvedEntitlements:
    plan_slug: str
    max_listing_favorites: int | None
    max_zone_favorites: int | None
    retention_days: int
    can_customize_radius: bool
    can_customize_max_time: bool
    can_customize_distance: bool
    max_active_metrics: int | None
    zone_selection_policy: str          # 'restricted' | 'any'
    auto_refresh_policy: str            # 'none' | 'nightly_inclusion' | 'managed_queue'
    pro_max_refresh_max_zones: int | None
    pro_max_refresh_max_listings: int | None
    pro_max_refresh_cadence_days: int | None
    pro_max_refresh_eligibility_days: int | None
    rollover_percent: int
    rollover_cycles: int
    cycle_length_days: int

class PlanEntitlementService:
    async def assert_can_save_listing(self, user_id: UUID) -> None:
        ent = await self.resolve(user_id)
        if ent.max_listing_favorites is None:
            return
        count = await self._listing_count(user_id)
        if count >= ent.max_listing_favorites:
            raise EntitlementExceeded(
                kind="max_listing_favorites",
                plan=ent.plan_slug,
                current=count,
                limit=ent.max_listing_favorites,
            )

    async def assert_can_customize(self, user_id: UUID, field: str) -> None:
        ent = await self.resolve(user_id)
        flag = {
            "radius": ent.can_customize_radius,
            "max_time": ent.can_customize_max_time,
            "distance": ent.can_customize_distance,
        }[field]
        if not flag:
            raise EntitlementExceeded(kind=f"customize_{field}", plan=ent.plan_slug)

    async def assert_view_window_valid(self, favorite) -> None:
        if favorite.view_state == "expired_for_view":
            raise ViewWindowExpired(plan=favorite.plan_at_save)
```

**Roteiro de aplicação:**
- `POST /favorites/listings` → `assert_can_save_listing` antes do insert.
- `PATCH /journeys/{id}` (campos de raio/tempo/distância) → `assert_can_customize`.
- `GET /favorites/listings/{key}` → `assert_view_window_valid` (retorna 410 Gone com CTA de upgrade).
- Métricas habilitadas (`POST /journeys/{id}/metrics`) → checa `max_active_metrics`.

### Integração de listings com etapas monetizáveis

```python
async def request_listings(journey_id, zone_id, user_id, session_id, config):
    cache = await zone_listing_caches.get(zone_id, config)
    cache_usable = cache is not None and cache.is_usable()

    await listing_search_requests.record(
        journey_id=journey_id,
        user_id=user_id,
        session_id=session_id,
        zone_fingerprint=config.zone_fingerprint,
        search_location_normalized=config.search_location_normalized,
        search_location_label=config.search_location_label,
        search_location_type=config.search_location_type,
        search_type=config.search_type,
        usage_type=config.usage_type,
        platforms_hash=config.platforms_hash,
        result_source="cache_hit" if cache_usable else "cache_miss",
    )

    if cache_usable:
        # Etapa monetizável #3: acesso a imóveis em cache (20 créditos)
        await check_and_consume_credits(
            user_id=user_id, session_id=session_id,
            step=JourneyStep.LISTINGS_CACHE, reference_id=journey_id,
        )
        return ListingsRequestResult(source="cache", ...)

    if config.allow_fresh_scrape:
        # Etapa monetizável #4: scraping fresco (20 créditos) — somente se o usuário confirmou na UI
        await check_and_consume_credits(
            user_id=user_id, session_id=session_id,
            step=JourneyStep.LISTINGS_SCRAPE, reference_id=journey_id,
        )
        await scrape_lock_and_enqueue(zone_id, config)
        return ListingsRequestResult(source="fresh_scrape", freshness_status="scraping_now")

    # Sem cache e sem opt-in para scraping fresco: cai no prewarm da próxima janela
    return ListingsRequestResult(
        source="none",
        freshness_status="queued_for_next_prewarm",
        next_refresh_window="03:00–05:30",
    )
```

### Prewarm noturno (com inclusão Pro Max)

```python
# APScheduler — único cron noturno
scheduler.add_job(
    prewarm_run_nightly,
    trigger="cron", hour=3,
    kwargs={"lookback_hours": 24, "limit_demand": 100, "limit_pro_max": 500},
)

async def prewarm_run_nightly(lookback_hours: int, limit_demand: int, limit_pro_max: int):
    # 1) Demanda das últimas 24 horas (regra v2.2 mantida)
    demand = await listing_search_requests.aggregate_last_24h(limit=limit_demand)

    # 2) NOVO v2.3: endereços de imóveis salvos por usuários do plano Pro Max
    #    (a base inteira é atualizada nesta mesma run; os endereços Pro Max entram junto)
    #    Pro (sem Pro Max) é EXCLUÍDO daqui.
    pro_addresses = await db.fetch(
        """
        SELECT DISTINCT f.address_normalized AS address,
               MAX(f.last_viewed_at) AS last_viewed_at
          FROM user_listing_favorites f
          JOIN subscriptions s ON s.user_id = f.user_id
          JOIN plans p ON p.id = s.plan_id
         WHERE s.status IN ('active', 'past_due')
           AND p.slug = 'pro_max'              -- exclui pro
           AND f.address_normalized IS NOT NULL
           AND f.view_state = 'visible'
         GROUP BY f.address_normalized
         ORDER BY last_viewed_at DESC
         LIMIT $1
        """,
        limit_pro_max,
    )

    # 3) Conjunto-alvo final = união (deduplicada por endereço)
    target_set = build_target_set(demand_rows=demand, pro_rows=pro_addresses)

    # 4) Enfileirar com PREWARM priority (LOW)
    for item in target_set:
        await dramatiq.send(
            "listings_prewarm",
            queue="prewarm",
            priority=Priority.PREWARM,
            kwargs={
                "address_normalized": item.address,
                "search_type": item.search_type,
                "usage_type": item.usage_type,
                "trigger_source": item.source,  # 'demand_24h' | 'pro_max_saved'
            },
        )
```

- O conjunto-alvo do prewarm é a **união** de:
  - **Demanda real**: endereços/search locations pesquisados na Etapa 5 nas últimas 24 h (regra original).
  - **Plano Pro Max (novo em v2.3)**: endereços (`address_normalized`) dos imóveis salvos por usuários com assinatura Pro Max ativa (status `active` ou `past_due` dentro do grace), independente de pesquisa recente.
- **Pro (sem Pro Max) é excluído** desta união.
- Ordenação por origem: demanda 24h primeiro (`COUNT(*) DESC`, `MAX(requested_at) DESC`); depois saved_pro_max (`MAX(last_viewed_at) DESC`); empate por cache mais antigo.
- Não existe fallback por zona popular, geohash, região ou cold start artificial.
- **Limites operacionais:** `limit_demand=100` + `limit_pro_max=500` por run inicial (ajustável). Excedente fica para a próxima janela.
- **Alerta crítico:** prewarm não iniciou em 30 min do horário, ou `prewarm_coverage_rate < 60%` dos endereços-alvo processados com sucesso.

### Refresh dedicado do Pro Max

```python
# APScheduler — fila dedicada, run noturna após o prewarm geral
scheduler.add_job(
    pro_max_refresh_run,
    trigger="cron", hour=4, minute=30,
    kwargs={"max_per_run": 200},
)

async def pro_max_refresh_run(max_per_run: int):
    run_id = await db.fetchval(
        "INSERT INTO pro_max_refresh_runs (status) VALUES ('running') RETURNING id"
    )

    # 1) Seleção: alvos Pro Max devidos hoje, dentro de quota e elegíveis
    targets = await db.fetch(
        """
        SELECT t.id, t.user_id, t.target_kind, t.listing_favorite_id, t.zone_favorite_id,
               t.is_priority, t.next_refresh_due_at
          FROM pro_max_refresh_targets t
          JOIN subscriptions s ON s.user_id = t.user_id
          JOIN plans p ON p.id = s.plan_id
         WHERE p.slug = 'pro_max'
           AND s.status IN ('active', 'past_due')
           AND t.is_active = true
           AND t.next_refresh_due_at <= NOW()
         ORDER BY t.is_priority DESC, t.next_refresh_due_at ASC
         LIMIT $1
        """,
        max_per_run,
    )

    for t in targets:
        await dramatiq.send(
            f"pro_max_refresh_{t['target_kind']}",
            queue="pro_max_refresh",
            priority=Priority.PRO_MAX_REFRESH,
            kwargs={"target_id": str(t["id"]), "run_id": str(run_id)},
        )
```

**Política de elegibilidade e franquia (mantida em sincronia com `plan_entitlements`):**

```python
async def reconcile_pro_max_targets(user_id: UUID) -> None:
    """Idempotente. Roda em on_favorite_change, on_subscription_change e no início do refresh run."""
    ent = await entitlements.resolve(user_id)
    if ent.auto_refresh_policy != "managed_queue":
        await db.execute(
            "UPDATE pro_max_refresh_targets SET is_active=false WHERE user_id=$1",
            user_id,
        )
        return

    eligibility_cutoff = now() - timedelta(days=ent.pro_max_refresh_eligibility_days)

    # Listings: ativo se visualizado nos últimos N dias OU priority_flag = true
    candidates_listing = await db.fetch(
        """SELECT id, last_viewed_at, priority_flag
             FROM user_listing_favorites
            WHERE user_id=$1 AND view_state='visible'
              AND (last_viewed_at >= $2 OR priority_flag = true)
            ORDER BY priority_flag DESC, last_viewed_at DESC
            LIMIT $3""",
        user_id, eligibility_cutoff, ent.pro_max_refresh_max_listings,
    )
    candidates_zone = await db.fetch(
        """SELECT id, last_viewed_at, priority_flag
             FROM user_zone_favorites
            WHERE user_id=$1 AND view_state='visible'
              AND (last_viewed_at >= $2 OR priority_flag = true)
            ORDER BY priority_flag DESC, last_viewed_at DESC
            LIMIT $3""",
        user_id, eligibility_cutoff, ent.pro_max_refresh_max_zones,
    )
    await upsert_targets(user_id, candidates_listing, candidates_zone, ent)
```

**Cadência:** ao concluir um refresh com sucesso, o handler atualiza
`last_refreshed_at = NOW()` e `next_refresh_due_at = NOW() + cadence_days * INTERVAL '1 day'`. Falhas: backoff `[1d, 2d, 4d]` em `failure_count`; 3 falhas → `is_active = false`, badge "Refresh manual" exibido na UI.

**Idempotência:** o handler reaproveita o cache do scraping geral quando aplicável (deduplicação por `address_normalized + search_type + usage_type`).

### Billing atual — Pix

Fluxo de ativação por Pix:

```text
Usuário escolhe plano
  → POST /billing/pix/checkout
  → backend cria payment pending
  → backend gera QR Code / copia e cola
  → frontend exibe pagamento
  → confirmação manual ou callback
  → backend marca payment paid
  → ativa plan_activation por 30 dias
  → concede créditos do ciclo
  → registra credit_ledger
```

### Endpoints Pix

```http
POST /billing/pix/checkout
GET  /billing/payments/{payment_id}
POST /billing/pix/confirm
POST /billing/pix/callback
POST /billing/payments/{payment_id}/cancel
```

#### `POST /billing/pix/checkout`

Entrada:

```json
{
  "plan_slug": "basico",
  "payment_type": "plan_activation"
}
```

Saída:

```json
{
  "payment_id": "uuid",
  "plan_slug": "basico",
  "amount_brl": 21.99,
  "status": "pending",
  "expires_at": "2026-04-26T23:59:00-03:00",
  "qr_code_payload": "...",
  "pix_copy_paste": "...",
  "qr_code_image_url": "..."
}
```

#### Confirmação Pix

Na primeira versão, pode ser manual/admin:

```http
POST /admin/billing/pix/{payment_id}/confirm
```

Regras:
- só admins podem confirmar manualmente;
- confirmação é idempotente;
- um pagamento confirmado não pode ser confirmado de novo;
- um pagamento expirado não pode ativar plano sem recriação.

#### Ativação do plano por Pix

```python
async def activate_plan_from_pix(payment_id: UUID):
    async with db.transaction():
        payment = await lock_payment(payment_id)

        if payment.status == "paid":
            return AlreadyProcessed()

        if payment.status != "pending":
            raise InvalidPaymentState()

        if payment.expires_at < now():
            raise PaymentExpired()

        await mark_payment_paid(payment_id)

        activation = await create_plan_activation(
            user_id=payment.user_id,
            plan_id=payment.plan_id,
            source_payment_id=payment.id,
            started_at=now(),
            ends_at=now() + timedelta(days=30),
        )

        plan = await get_plan(payment.plan_id)

        await grant_cycle_credits(
            user_id=payment.user_id,
            plan_id=plan.id,
            amount=plan.monthly_credits,
            reason="pix_plan_activation",
            reference_id=activation.id,
        )

        await emit_event("billing.plan_activated", user_id=payment.user_id)
```

### Billing futuro — Stripe (Fase 10)

Stripe fica em Fase 10. Escopo futuro:
- Stripe Billing;
- assinatura recorrente;
- portal do cliente;
- upgrades/downgrades com proration;
- dunning e retries;
- Payment Intent para top-up avulso;
- webhooks `customer.subscription.*` e `invoice.*`.

### Geração de relatório PDF

```
Frontend: map.getCanvas().toDataURL('image/png')
  → POST /reports {journey_id, zone_id, map_image_base64}
API: valida quota → persiste imagem R2 → cria job REPORT_GENERATE → {job_id}
Worker: busca dados → Jinja2 HTML → WeasyPrint PDF → upload R2 → signed URL (7 dias)
SSE: report.ready {url}
Frontend: exibe botão Download
```

`preserveDrawingBuffer: true` obrigatório na inicialização do MapShell.
Duração esperada: 5–20s.
`GET /reports/{report_id}/url` regenera signed URL após expiração.

### Limiares de resultado preliminar

```python
class PreliminaryResultThresholds:
    MIN_GEOMETRIC_COVERAGE = 0.30  # 30% da área da zona deve estar coberta
    MIN_PROPERTIES_RENTAL  = 5
    MIN_PROPERTIES_SALE    = 3
    MAX_CACHE_AGE_RENTAL   = 12   # horas
    MAX_CACHE_AGE_SALE     = 24   # horas
```

### Badges de zona

```python
class ZoneBadgeRule:
    SAFETY: relative_threshold = -0.20  # 20% menos ocorrências que a mediana
    GREEN:  relative_threshold = +0.20  # 20% mais área verde
    FLOOD:  relative_threshold = -0.20  # 20% menos área alagável
    POIS:   relative_threshold = +0.30  # 30% mais POIs

class ZoneBadgeValue(str, Enum):
    BEST    = "best"
    ABOVE   = "above"
    NEUTRAL = "neutral"
    BELOW   = "below"
```

Badges calculados incrementalmente (provisório com mediana parcial) e finalizados
após todas as zonas concluírem enriquecimento (`zones.badges.finalized`).

---

## 9. Especificação do Frontend

### Stack

| Biblioteca | Versão alvo | Função |
|---|---|---|
| Next.js App Router | 14+ | Framework, SSR, routing |
| MapLibre GL JS | 4+ | Renderização de mapa |
| MapTiler | — (free tier) | Tiles base (provedor único, forever) |
| TanStack Query | 5+ | Server state / cache HTTP |
| Zustand | 4+ | UI state + journey state + map state |
| shadcn/ui + Tailwind | — | Design system (componentes copiados no repo) |
| Recharts | 2+ | Gráficos (histórico, histogramas) |

### Layout

```
┌────────────────────────────────────────────────────────────┐
│  [AddressSearchBox]           [PanelToggleButton]          │
│                                                            │
│     MAPA (100% da tela)           PAINEL (420px padrão)    │
│                                   560–640px na Etapa 6     │
│                                                            │
│  [LegendCard]          [LayerControlFab]                   │
│                        [controles de zoom/bússola]         │
└────────────────────────────────────────────────────────────┘
```

Mobile: painel vira bottom sheet arrastável; mapa continua principal.

### Etapas da jornada

#### Etapa 1 — Configuração inicial

**Painel:**
- Ponto de referência principal (clique no mapa ou busca textual)
- Ponto secundário opcional (trabalho, escola — não afeta isócronas)
- Aluguel / Compra
- Raio da zona (metros) — **lock visual** com tooltip "Disponível a partir do plano Básico" para Anônimo/Free
- Modal: Transporte público | A pé | Carro
- Tempo máximo (minutos) — mesma regra de lock por plano
- Distância máxima até seed de transporte — mesma regra de lock
- Checkboxes de análise: verde, alagamento, segurança, POIs — limitados a `max_active_metrics` do plano (Básico=4; Pro/Pro Max sem limite). Tentar ativar a 5ª métrica no Básico abre modal "Atualize para Pro".
- Botão "Achar pontos de transporte"

**Mapa:** cursor vira pin somente sobre o mapa ao entrar em modo de seleção.

**Bloqueio por entitlement:** campos travados exibem ícone 🔒 com tooltip do plano necessário. O lock é visual + servidor (`assert_can_customize`); cliente não envia o campo se não tiver permissão.

#### Etapa 2 — Seleção do ponto de transporte

**Painel:** lista ordenada por menor tempo a pé / maior conectividade.
Cada item: distância a pé, tipo, qtd de linhas, linhas disponíveis, botão "Gerar zonas".

**Mapa:** círculo de alcance, pontos elegíveis destacados, trajetos a pé,
hover da lista acende ponto correspondente no mapa.

#### Etapa 3 — Geração de zonas (processamento)

**Painel:** barra de progresso real, etapa corrente, eventos recentes,
subtarefas concluídas, botão cancelar.

**Mapa:** continua navegável; zonas aparecem progressivamente via SSE.

**Regra UX:** o usuário nunca deve sentir que a tela parou.

#### Etapa 4 — Comparação de zonas

**Painel:** lista por `travel_time_minutes` asc (empates por `walk_distance_meters` asc),
badges incrementais, filtros, detalhes da zona selecionada, grupos de POIs, CTA "buscar imóveis".


**Mapa:** rótulos numéricos nos polígonos, ponto de transporte persistente,
rotas visíveis, POIs sob demanda.

**Badges:** provisórios durante enriquecimento parcial (`baseado em X de Y zonas`),
finalizados quando todas concluem.
Transição de badge para baixo = animação neutra. Para cima = animação leve positiva.

#### Etapa 5 — Busca de imóveis (seleção de endereço)

**Painel:** combobox autocomplete filtrado para dentro do polígono da zona (`ST_Contains`).
logradouro+Bairro+Cidade+UF. Botão "Buscar imóveis" habilitado só após seleção.

**Contexto:** o endereço selecionado é o parâmetro enviado ao scraper.
`ST_Within` remove falsos positivos na Etapa 6.

#### Etapa 6 — Imóveis + dashboard

**Painel expandido (560–640px), 2 abas:**

**Aba Imóveis:**
Cards: foto, preço, metragem, endereço resumido, plataforma, link externo,
badge de duplicidade, botão "ver acessibilidade".
Filtros: faixa de preço, faixa de metragem, tipo de uso, plataforma, ordenação.
Todas as plataformas disponíveis (QuintoAndar, Zap, VivaReal) são acessíveis por créditos — a distinção não é por plano, mas por saldo.
Resultado preliminar com badge de frescor; diff incremental ao revalidar.

**Aba Dashboard da zona:**
Preço médio atual e histórico (Recharts LineChart, max 365 pontos, `dot={false}` acima de 90).
Distribuição por faixa (Recharts BarChart).
Segurança, área verde, área alagável, contagem de POIs, resumo transporte.

**Mapa (ao clicar "ver acessibilidade"):** melhor rota a pé até cada categoria de POI
e até o transporte. Alternância entre categorias sem recarregar.

### UI/UX de planos, salvos e billing (v2.4 — Pix)

#### Telas principais

| Tela | Objetivo |
|---|---|
| Mapa / jornada | Execução da análise |
| Favoritos | Imóveis e zonas salvas |
| Comparação | Comparar salvos dentro da janela do plano |
| `/planos` | Escolha do plano e Pix |
| `/conta` | Plano atual, créditos e histórico |
| Modal Pix | QR Code, copia e cola, status |

#### Header e estado global de plano

- **Badge de plano** no header: chip colorido por tier (`Free` neutro, `Básico` azul, `Pro` roxo, `Pro Max` dourado).
- **Saldo dual**: pílula `cycle_credits` (com ícone de relógio para indicar expiração) + `legacy_balance` (com ícone de pacote). Hover abre tooltip com `rollover_balance` separado e dias restantes do ciclo.
- `useEntitlements()` hook centraliza acesso aos limites resolvidos no servidor. SSE event `entitlements.changed` (emitido em `plan_activations`) força refetch e invalida caches dependentes.

#### Página `/planos`

Cada plano exibe: preço, créditos, número de jornadas equivalentes, limite de imóveis salvos, limite de zonas salvas, retenção, métricas, parâmetros e refresh.

- 4 cards lado a lado: Free, Básico, Pro, Pro Max. Plano atual destaca-se com borda + chip "Seu plano".
- CTA primária por card varia: `Plano atual` (Free), `Pagar via Pix` (Básico/Pro/Pro Max).
- Linha por linha de comparação alinhada à tabela da Seção 11.

#### Modal Pix

Estados:

| Estado | UI |
|---|---|
| pending | QR Code + copia e cola + timer |
| paid | "Pagamento confirmado. Plano ativado." |
| expired | "QR Code expirado. Gerar novo Pix." |
| cancelled | "Pagamento cancelado." |

#### Painel de favoritos

`FavoritesPanel` com 3 estados por item:

| Estado | Indicador visual | Texto |
|---|---|---|
| `visible` + recente | borda neutra | `Snapshot há 3h` |
| `visible` + Pro Max | badge azul "Atualizado" | `Refresh em 3 dias` |
| `expired_for_view` | overlay 30% opaco + lock | `Janela de visualização expirou. Atualize seu plano.` |
| `over_limit_grace` | banner amarelo | `Excedeu o limite do plano. Será arquivado em 5 dias.` |

- **Star de prioridade (Pro Max)**: ícone toggle no canto do card. Click → `PATCH /favorites/listings/{key} {priority_flag: true}` → reconcilia `pro_max_refresh_targets`.
- **Aba "Sob refresh automático"** (somente Pro Max): lista os itens dentro da franquia com `next_refresh_due_at`.

#### Página `/conta`

Deve exibir:
- plano atual;
- data de início e fim do ciclo;
- créditos restantes e buckets de crédito;
- histórico de pagamentos Pix;
- histórico de créditos (`credit_ledger` paginado);
- botão "Renovar via Pix" quando próximo do fim do ciclo.

#### Modais críticos

- **Limite de salvos atingido**: título "Você atingiu seu limite", lista os limites do próximo tier, CTA "Ativar via Pix". Inclui opção secundária "Remover um existente".
- **Saldo insuficiente**: mostra etapa pretendida, custo (20), saldo atual, próximo refresh do ciclo, CTA "Ativar plano via Pix".
- **Janela de retenção expirada**: título "Visualização expirada", explica a regra do plano atual, CTA "Ativar Pro via Pix".

#### UX de Stripe futuro

Não exibir portal Stripe nem proration nesta fase. Os textos devem falar em:
- "ativar via Pix";
- "renovar via Pix";
- "pagamento aguardando confirmação";
- "Stripe será usado futuramente para automação de cobrança".

#### Acessibilidade e i18n

- Todos os textos em pt-BR. Variáveis monetárias em `Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })`.
- Estados de lock têm `aria-disabled="true"` + descrição via `aria-describedby` apontando para o tooltip.
- Cores de plano respeitam contraste WCAG AA mesmo no badge dourado (Pro Max).

### Gerenciamento de estado

| Store | Biblioteca | Conteúdo |
|---|---|---|
| `ui-store` | Zustand | painel, aba ativa, layer menu, popups, hover |
| `journey-store` | Zustand | ponto principal, seleções, parâmetros, etapas stale |
| `map-store` | Zustand | layers visíveis, viewport, instância mapa |
| `plan-store` | Zustand | entitlements resolvidos, plano vigente, saldos por bucket, status da assinatura |
| Server state | TanStack Query | zonas, imóveis, métricas, progresso de jobs, salvos com `last_refreshed_at` |
| SSE bridge | custom hook | invalida queries TanStack ao receber `entitlements.changed`, `favorites.refreshed`, `subscription.changed` |

### Regras de performance do mapa

- Mapa vive em componente próprio com refs estáveis — mudanças no painel não recriam instância.
- GeoJSON apenas para seleção ativa e subconjuntos < 500 features.
- POIs carregados sob demanda via Mapbox Search Box API por bounding box + categoria; nunca tudo de uma vez.
- Vector tiles / PMTiles para camadas base pesadas.
- Overlays analíticos server-driven.

---

## 10. Autenticação e Modelo de Acesso

### Implementação atual (Fase 8 em progresso)

Auth customizado em `apps/api/src/modules/auth/service.py`:

- **Registro e login por e-mail + senha** (implementado em 2026-04-12).
- Hashing: PBKDF2-HMAC-SHA256, 600.000 iterações, salt aleatório por usuário.
- Sessões armazenadas em `user_sessions`; token opaco de 32 bytes, hash SHA-256 no banco.
- Cookie HTTP-only `auth_session`, `samesite=lax`, TTL 30 dias.
- E-mail normalizado em lowercase; validação por regex.
- `GET /auth/me` inspeciona sessão; `POST /auth/register`; `POST /auth/login`; `POST /auth/logout`.

> **Nota de desvio do plano original:** a implementação substituiu fastapi-users + magic link por auth customizado e-mail/senha. OAuth Google foi implementado em 2026-05-05 via Google Identity Services (GIS) — `POST /auth/google`, validação server-side do ID token com `google-auth`, campos `google_subject`/`email_verified_at` em `users`. Magic link continua no backlog.

### Provedor de email (backlog)

**Resend** (`resend.com`) — planejado para magic link (backlog).

```python
RESEND_API_KEY: str
EMAIL_FROM: str = "noreply@find-ideal-estate.com.br"
```

### Fluxo anônimo → autenticado

O usuário acessa sem cadastro. Jornada associa-se a `anonymous_session_id` (cookie).
Autenticação exigida apenas em momentos de alto valor:
- Download do relatório PDF.
- Salvar jornada / favoritos persistentes.
- Acessar histórico.
- Assinar plano pago / comprar pacote avulso.

**Regra de migração (decisão fechada):** o saldo anônimo remanescente **NÃO é somado** ao saldo do plano Free. O usuário recém-cadastrado recebe **saldo fixo de 350 créditos** no bucket `cycle_credits` do plano Free; o saldo anônimo é descartado (com auditoria). Apenas jornadas e contexto da sessão anônima são preservados.

```sql
BEGIN;

UPDATE journeys
   SET user_id = :new_user_id, anonymous_session_id = NULL
 WHERE anonymous_session_id = :session_id AND user_id IS NULL;

INSERT INTO plan_activations (user_id, plan_id, status, started_at, ends_at)
SELECT :new_user_id, p.id, 'active', NOW(), NOW() + INTERVAL '30 days'
  FROM plans p
 WHERE p.slug = 'free';

INSERT INTO user_credits (
  user_id, plan_id, cycle_credits, monthly_quota, cycle_started_at, cycle_ends_at
)
SELECT :new_user_id, p.id, 350, 350, NOW(), NOW() + INTERVAL '30 days'
  FROM plans p
 WHERE p.slug = 'free'
ON CONFLICT (user_id) DO UPDATE
  SET cycle_credits = 350,
      monthly_quota = 350,
      cycle_started_at = NOW(),
      cycle_ends_at = NOW() + INTERVAL '30 days';

INSERT INTO credit_ledger (user_id, bucket, delta, reason, balance_after)
VALUES (:new_user_id, 'cycle', 350, 'signup_grant_free', 350);

INSERT INTO credit_ledger (user_id, bucket, delta, reason, balance_after)
VALUES (:new_user_id, 'cycle', 0, 'anonymous_balance_discarded', 350);

COMMIT;
```

**Migração de usuários pré-2.4:** usuários com assinatura Stripe migram para `plan_activations` com `status = 'active'` e `source_payment_id = NULL`. O saldo legado é preservado em `legacy_balance`.

**TTL de sessão anônima:** 7 dias de inatividade.
Jornadas com relatório gerado: 30 dias.

### Resolução de plano por usuário

Toda request autenticada passa por middleware que injeta `request.state.entitlements`:

```python
async def entitlements_middleware(request, call_next):
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        request.state.entitlements = await entitlements.resolve(user_id)
    else:
        request.state.entitlements = ANONYMOUS_DEFAULT_ENTITLEMENTS
    return await call_next(request)
```

`ANONYMOUS_DEFAULT_ENTITLEMENTS` é um singleton imutável que reflete a linha do plano `anonymous` em `plan_entitlements`.

### Mapa de dependência de auth por fase (v2.3)

| Feature | Fase | Depende de auth? | Plano mínimo |
|---|---|---|---|
| Análise de transporte e zonas | 4 | Não (créditos de sessão) | anônimo |
| Cache de imóveis | 6 | Não (créditos de sessão) | anônimo |
| Badge de frescor | 6 | Não | anônimo |
| Scraping fresco sob demanda | 6 | Não | nenhum plano |
| Download do relatório PDF | 7 | Sim (CTA de cadastro) | free |
| Histórico de análises | 7 | Sim | free |
| Salvar imóvel/zona | 6 | Sim | free (5/2) |
| Customizar raio/tempo/distância | 4 | Sim | basico |
| Selecionar qualquer zona | 4 | Sim | basico |
| > 4 métricas simultâneas | 4 | Sim | pro |
| Inclusão noturna no prewarm | 7 | Sim | pro |
| Refresh automático semanal de salvos | 9 | Não | nenhum plano |
| Assinatura recorrente / billing | 8 | Sim | qualquer pago |

**Fases 6–7 sem auth completa:** créditos de sessão trackeados por Redis `credit:session:{session_id}` com TTL 7 dias. A assinatura real é criada na Fase 8.

---

## 11. Monetização

### Modelo comercial

O produto opera em modelo:

```text
freemium + planos mensais + créditos por ciclo + entitlements por plano
```

A cobrança prioritária da primeira versão é:

```text
Pix com QR Code / Pix Copia e Cola
```

Stripe permanece no roadmap, mas não bloqueia o lançamento da monetização.

### Unidade de consumo

| Etapa | Créditos |
|---|---:|
| Geração de zona | 20 |
| Enriquecimento de zona | 20 |
| Acesso a imóveis em cache | 20 |
| Scraping fresco sob demanda | indisponível |
| Relatório/export analítico | 20 |

Total:

```text
1 jornada completa sem scraping sob demanda = 80 créditos
```

### Planos

| Plano | Preço | Créditos | Imóveis salvos | Zonas salvas | Retenção | Parametrização | Métricas | Atualização |
|---|---:|---:|---:|---:|---:|---|---|---|
| Anônimo | — | 300 sessão | 0 | 0 | 7 dias sessão | travada | default | não |
| Free | R$ 0 | 350 | 5 | 2 | 7 dias | travada | default | não |
| Básico | R$ 21,99 | 800 | 20 | 4 | 30 dias | limitada | 4 | não |
| Pro | R$ 90,99 | 4000 | 100 | 20 | 30 dias | liberada | sem limite | não |
| Pro Max | R$ 312,99 | 20000 | 100 | 20 | 30 dias | liberada | sem limite | não |

### Plano Anônimo

- 300 créditos de sessão;
- até 3 jornadas completas;
- parâmetros travados;
- sem favoritos persistentes;
- sem atualização automática.

### Plano Free

- 350 créditos por ciclo;
- não soma com saldo anônimo;
- 5 imóveis salvos;
- 2 zonas salvas;
- retenção de 7 dias;
- acesso à comparação por 7 dias;
- parâmetros travados.

### Plano Básico

- R$ 21,99/mês;
- 800 créditos;
- 20 imóveis salvos;
- 4 zonas salvas;
- retenção e comparação por 30 dias;
- customização de raio, tempo e distância dentro do limite do plano;
- qualquer zona;
- até 4 métricas.

### Plano Pro

- R$ 90,99/mês;
- 4000 créditos;
- 100 imóveis salvos;
- 20 zonas salvas;
- retenção e comparação por 30 dias;
- qualquer zona;
- métricas ilimitadas;
- sem atualização automática.

### Plano Pro Max

- R$ 312,99/mês;
- 20000 créditos;
- herda Pro;
- sem atualização automática.

### Política de créditos

- créditos do ciclo expiram no fim do ciclo;
- rollover de até 25% por 1 ciclo;
- créditos avulsos/top-up futuros entram em `legacy_balance`;
- consumo FIFO:
  - `cycle_credits`;
  - `rollover_balance`;
  - `legacy_balance`.

### Pagamento via Pix

#### Ativação

1. Usuário escolhe plano.
2. Sistema gera cobrança Pix.
3. Usuário paga.
4. Sistema confirma pagamento.
5. Plano é ativado por 30 dias.
6. Créditos são concedidos.

#### Renovação

Na primeira versão, a renovação é manual:
- antes do vencimento, o usuário recebe CTA de renovação;
- gera novo Pix;
- ao pagar, novo ciclo é iniciado.

#### Confirmação

A confirmação pode ser:
- manual por admin na primeira versão;
- automática via callback de provedor Pix em versão seguinte.

### Stripe futuro

Stripe entra depois para:
- assinatura recorrente;
- portal do cliente;
- upgrades e downgrades automáticos;
- proration;
- retries;
- dunning;
- webhooks de assinatura;
- top-up automatizado.

---

## 12. Roadmap por Fase (0–10)

> **Convenção de milestones:**
> Cada fase é dividida em marcos internos (M*fase*.*n*) que podem ser verificados
> de forma independente. Um marco é concluído quando todos os seus critérios de
> verificação passam no ambiente de staging.
> Estimativas de esforço em dias de trabalho focado (single developer).

---

### Fase 0 — Fundação

**Objetivo:** repositório e infraestrutura base prontos para desenvolvimento.
**Esforço estimado:** 3–4 dias · **Status:** ✅ Concluída
**Dependências bloqueantes:** nenhuma.

#### M0.1 — Monorepo e estrutura de diretórios
- [x] Criar estrutura `apps/web`, `apps/api`, `packages/contracts`, `infra/`
- [x] `pyproject.toml` com Poetry/uv; workspace configurado
- [x] `packages/contracts/` vazio mas importável (sem DTOs ainda)
- [x] `.gitignore` e `.editorconfig` completos

**Verificação:** `cd apps/api && python -c "from contracts import __version__"` sem erro.

#### M0.2 — Docker e banco de dados
- [x] `docker-compose.yml`: serviços `api`, `postgres` (PostGIS), `redis`
- [x] `docker/api.Dockerfile` e `docker/ui.Dockerfile`
- [x] PostGIS extensão habilitada na migration inicial
- [x] Alembic configurado; `alembic upgrade head` aplica sem erro
- [x] Tabelas `users`, `journeys`, `jobs`, `job_events` criadas (schema mínimo)

**Verificação:** `docker compose up -d` → `docker compose ps` mostra todos `healthy`.

#### M0.3 — API base e configuração
- [x] `core/config.py`: Pydantic Settings com todas as vars obrigatórias
- [x] Startup falha com mensagem clara se var obrigatória ausente
- [x] `GET /health` retorna `{"status": "ok", "db": "ok", "redis": "ok"}`
- [x] Logging estruturado JSON com campos `request_id`, `correlation_id`, `level`, `timestamp`
- [x] Middleware injeta `request_id` em todas as respostas

**Verificação:** remover `DATABASE_URL` → startup imprime `ConfigurationError: DATABASE_URL is required`.

#### M0.4 — CI básico
- [x] GitHub Actions: `ruff check`, `mypy` (strict em `core/`), `pytest` unitário
- [x] Pipeline verde em branch limpa
- [x] Badge de status no README

**Verificação:** PR com erro de tipo falha o CI antes de merge.

---

### Fase 1 — Core domain: journey, job, SSE

**Objetivo:** modelo de jornada e job funcionando end-to-end com SSE real.
**Esforço estimado:** 4–5 dias · **Status:** ✅ Concluída
**Dependências bloqueantes:** M0.2, M0.3.

#### M1.1 — Schema completo de domínio
- [x] Migrations para `journeys`, `jobs`, `job_events`, `transport_points`, `zones` (colunas base)
- [x] Enums `JourneyState`, `JobType`, `JobState` definidos em `packages/contracts/`
- [x] Relacionamentos FK corretos; `CASCADE` em job_events → jobs

**Verificação:** `alembic upgrade head` sem erro; todas as tabelas existem com colunas esperadas.

#### M1.2 — Endpoints de jornada
- [x] `POST /journeys` cria jornada + sessão anônima (cookie `anonymous_session_id`, HttpOnly)
- [x] `GET /journeys/{id}` retorna estado + `last_completed_step`
- [x] `PATCH /journeys/{id}` atualiza `input_snapshot`, `selected_transport_point_id`, etc.
- [x] `DELETE /journeys/{id}` marca como `expired`
- [x] DTOs `JourneyCreate`, `JourneyRead` em `packages/contracts/`

**Verificação:** `POST /journeys` → body com `id`; cookie `anonymous_session_id` presente na resposta.

#### M1.3 — Endpoints de job
- [x] `POST /jobs` cria job associado a uma jornada
- [x] `GET /jobs/{id}` retorna estado + `progress_percent` + `current_stage`
- [x] `POST /jobs/{id}/cancel` grava `cancel_requested_at`, responde 202

**Verificação:** job criado e listado com estado `pending`.

#### M1.4 — SSE via Redis pub/sub
- [x] `GET /jobs/{id}/events` abre stream SSE
- [x] Worker stub publica em `job:{id}` no Redis; cliente recebe no stream
- [x] Reconexão com `Last-Event-ID`: API reenvia eventos de `job_events` desde o ID
- [x] Cleanup de assinatura Redis ao desconectar (sem leak)

**Verificação:** abrir stream → publicar manualmente no Redis → evento chega ao cliente em < 500ms.
Desconectar e reconectar com `Last-Event-ID=X` → recebe eventos posteriores a X.

---

### Fase 2 — Dramatiq + worker infrastructure ✅

**Objetivo:** sistema de filas real com retry, heartbeat e cancelamento cooperativo.
**Esforço estimado:** 5–6 dias · **Status:** ✅ Concluída (2026-03-17)
**Dependências bloqueantes:** M1.3, M1.4.

#### M2.1 — Broker e filas ✅
- [x] `StubBroker` ativo em contexto de testes (`DRAMATIQ_BROKER=stub`)
- [x] `RedisBroker` ativo em contexto de produção
- [x] Definição de filas em `workers/queue.py`:
  `transport`, `zones`, `enrichment`, `scrape_browser`, `scrape_http`, `deduplication`, `reports`, `prewarm`
- [x] Concorrências corretas conforme tabela da seção 8
- [x] `Priority.USER_REQUEST = 0`, `Priority.PREWARM = 5`

**Verificação:** testes unitários passam com `StubBroker`; zero imports de Redis em módulos de domínio.

#### M2.2 — JobRetryPolicy e middleware ✅
- [x] `JobRetryPolicy` com backoffs distintos por tipo de job
- [x] Middleware `JobStateMiddleware`: atualiza `jobs.state` + emite SSE em cada transição
- [x] Middleware de heartbeat: publica `job_heartbeat:{job_id}` a cada 30s, TTL 120s
- [x] Transições cobertas por testes unitários: `pending→running→completed`, `failed→retrying→pending`

**Verificação:** job que lança exceção na primeira tentativa → estado `retrying` → re-executa com backoff correto.

#### M2.3 — Cancelamento cooperativo ✅
- [x] `JobCancelledException` importável em qualquer handler
- [x] Helper `check_cancellation(job_id)` verifica `cancel_requested_at` antes de cada sub-etapa
- [x] Handler de exemplo usa `check_cancellation` entre etapas
- [x] Estado final: `cancelled_partial` (resultado parcial persiste em `result_ref`)
- [x] `POST /jobs/{id}/cancel` testado end-to-end com handler de exemplo

**Verificação:** `POST /cancel` → handler detecta flag em < 2s → SSE emite `job.cancelled`.

#### M2.4 — Watchdog ✅
- [x] APScheduler (ou `asyncio` periódico) a cada 60s
- [x] Detecta jobs `running` com `job_heartbeat:{id}` expirado (> 2 min)
- [x] Força estado `cancelled_partial` e emite `job.failed` via SSE
- [x] Teste: matar worker manualmente → watchdog corrige estado em < 90s

**Verificação:** job sem heartbeat → watchdog o cancela; `GET /jobs/{id}` mostra `cancelled_partial`.

#### M2.5 — Worker de exemplo e testes ✅
- [x] `TRANSPORT_SEARCH` stub que dorme 3s emitindo progresso via SSE a cada 500ms
- [x] Testes unitários com `StubBroker` para cada tipo de job definido
- [x] Cobertura de retry: `max_retries` e `backoff_seconds` testados diretamente
- [x] Smoke test local: enfileirar job → aguardar SSE `job.completed`

**Verificação:** todos os testes unitários passam; smoke test completo em < 10s com `StubBroker`.

---

### Fase 3 — Transporte: GTFS + Valhalla + OTP 🔄

**Objetivo:** descoberta de pontos de transporte elegíveis e rotas a pé funcionando.
**Esforço estimado:** 8–10 dias · **Status:** 🔄 Em progresso
**Dependências bloqueantes:** M2.1–M2.5. Hostinger VPS com Valhalla + OTP rodando.

#### M3.1 — Baseline frontend em Vite + React ✅
- [x] `apps/web/` consolidado com Vite + React 18
- [x] MapLibre GL JS integrado; `MapShell` com `preserveDrawingBuffer: true`
- [x] MapTiler como único provedor de tiles (chave via `NEXT_PUBLIC_MAPTILER_API_KEY`)
- [x] Etapa 1 portada: formulário de configuração funcionando
- [x] `npm run build` (Vite) sem erros; `npm run preview` responsivo

**Verificação:** `npm run build` verde em `apps/web`; formulário de Etapa 1 salva jornada via `POST /journeys`.

#### M3.2 — Ingestão GTFS para PostGIS ✅
- [x] Script de ingestão: download zip → hash check → staging → substituição atômica
- [x] Tabelas: `gtfs_stops`, `gtfs_routes`, `gtfs_trips`, `gtfs_stop_times`, `gtfs_shapes`
- [x] Índice GIST em `gtfs_stops.location`
- [x] Registro em `dataset_versions` (`is_current = true` somente para o mais recente)
- [x] Hash check: executar ingestão duas vezes → segunda encerra sem reprocessar

**Verificação:** `SELECT count(*) FROM gtfs_stops` → ~22.094; re-ingestão do mesmo arquivo encerra em < 2s.

#### M3.3 — Ingestão GeoSampa ✅
- [x] `ogr2ogr` para: estações metro/trem, paradas de ônibus, terminais, corredores
- [x] `ST_IsValid` em todas as geometrias antes de commit
- [x] Registro em `dataset_versions`

**Verificação:** `SELECT count(*) FROM geosampa_metro_stations` → dado real SP.

#### M3.4 — Adaptador Valhalla ✅
- [x] `ValhallaAdapter.route(origin, dest, costing)` → `RouteResult`
- [x] `ValhallaAdapter.isochrone(origin, costing, contours_minutes)` → `GeoJSON`
- [x] Cache Redis: chave `valhalla:{costing}:{lat1}:{lon1}:{lat2}:{lon2}`, TTL 24h
- [x] Timeout de 5s com `httpx.TimeoutException` → `ValhallaCommunicationError`

**Verificação:** rota a pé entre dois pontos SP < 300ms; 2ª chamada (cache) < 50ms.

#### M3.5 — Adaptador OTP 2 ✅
- [x] `OTPAdapter.plan(origin, dest, datetime)` → `TransitItinerary`
- [x] Mapeia `leg.mode` para `modal_types` em `transport_points`
- [x] Retorna múltiplos itinerários ordenados por duração

**Verificação:** consulta de transporte público entre dois pontos SP retorna itinerário com linhas identificadas.

#### M3.6 — Job `TRANSPORT_SEARCH` real ✅
- [x] `ST_DWithin` sobre `gtfs_stops` + `geosampa_metro_stations` + `geosampa_trem_stations`
- [x] Filtro por `modal` selecionado na jornada
- [x] Ranking: distância a pé asc; desempate por qtd de rotas desc
- [x] Persiste lista em `transport_points`; emite `job.completed` via SSE
- [x] `GET /journeys/{id}/transport-points` retorna lista enriquecida

**Verificação:** ponto em SP (lat -23.55, lon -46.63), raio 300m → lista de paradas/estações com `walk_distance_m` ± 10% do real.

#### M3.7 — Proxy de geocoding ✅
- [x] `POST /api/geocode` → chama Mapbox Search Box API
- [x] Cache Redis 24h por string normalizada
- [x] Rate limit: 30 req/min por sessão via `external_usage_ledger`
- [x] Debounce da request quando chamada em < 300ms da anterior (retorna cached)
- [x] Não expõe token Mapbox ao frontend

**Verificação:** `POST /api/geocode {"q": "Av Paulista"}` retorna list de sugestões;
segunda chamada idêntica tem `cache_hit=true` em `external_usage_ledger`.

#### M3.8 — Frontend Etapa 2: seleção de transporte ✅
- [x] Lista de pontos de transporte com distância a pé, tipo, qtd de linhas
- [x] Hover na lista acende ponto correspondente no mapa
- [x] Círculo de alcance desenhado ao abrir a etapa
- [x] Botão "Gerar zonas" enfileira job e avança para Etapa 3

**Verificação:** hover em item da lista → marcador no mapa pisca; clique "Gerar zonas" → `POST /jobs` com tipo `ZONE_GENERATION`.

---

### Fase 4 — Zonas: isócronas + enriquecimento + DI 🔄

**Objetivo:** geração e enriquecimento de zonas com badges incrementais, incluindo POIs obtidos sob demanda via Mapbox.
**Esforço estimado:** 8–10 dias · **Status:** ⬜ Não iniciada
**Dependências bloqueantes:** M3.4, M3.6. Dados GeoSampa importados e ambiente geoespacial local (Valhalla/OTP) operacional.

#### M4.1 — dependency-injector ✅
- [x] Container principal em `apps/api/src/core/container.py`
- [x] Providers: `ValhallAdapter`, `OTPAdapter`, `TransportService`, `ZoneService`
- [x] Integrado ao FastAPI `lifespan` (não via decoradores globais)
- [x] Módulos de Fase 0–3 migrados ao container sem alterar comportamento

**Verificação:** `GET /health` com DI ativo → mesmos resultados; testes unitários passam com providers mockados.

#### M4.2 — Fingerprint e reaproveitamento de zona ✅
- [x] `compute_zone_fingerprint(lat, lon, modal, max_time, radius, dataset_version)` → SHA-256
- [x] lat/lon arredondados a 5 casas decimais antes do hash
- [x] `zones.fingerprint` com constraint UNIQUE
- [x] Antes de chamar Valhalla: checagem por fingerprint existente no banco
- [x] Zona reutilizada emite `zone.reused` em vez de `zone.generated`

**Verificação:** duas jornadas com mesmos parâmetros → `SELECT count(*) FROM zones WHERE fingerprint = :fp` = 1. ✅

#### M4.3 — Job `ZONE_GENERATION` ✅
- [x] Chamada Valhalla `/isochrone` para cada ponto de transporte selecionado
- [x] Persiste polígono em `zones.isochrone_geom` (PostGIS POLYGON 4326)
- [x] Emite `job.partial_result.ready` ao concluir cada zona (não aguarda todas)
- [x] Estado de zona: `pending → generating → enriching → complete | failed`
- [x] Zonas aparecem progressivamente no mapa via SSE

**Verificação:** selecionando 3 pontos de transporte → 3 polígonos chegam via SSE em sequência, não todos de uma vez. ✅

#### M4.4 — 4 subjobs de enriquecimento paralelos ✅
- [x] `ZONE_ENRICHMENT` dispara 4 subjobs por zona (fila `enrichment`, conc. 4):
  - `EnrichGreen`: `ST_Area(ST_Intersection(zone, vegetacao))` → `green_area_m2`
  - `EnrichFlood`: `ST_Area(ST_Intersection(zone, mancha_inundacao))` → `flood_area_m2`
  - `EnrichSafety`: `COUNT(incidents WHERE ST_Within(incident, zone))` → `safety_incidents_count`
  - `EnrichPOIs`: consulta Mapbox Search Box API por categoria usando o centroid/bbox da zona; normaliza o retorno e agrega `poi_counts` por categoria
- [x] `EnrichPOIs` usa cache efêmero por `zone_fingerprint + category_set + radius/bbox` antes de chamar a Mapbox
- [x] Todos os 4 subjobs iniciam simultaneamente por zona

**Verificação:** `EXPLAIN ANALYZE` dos 4 queries + parallel wall time vs sequential: parallelismo demonstrado com 1.21x speedup. ✅

#### M4.5 — Badges incrementais ✅
- [x] `compute_badge(value, peer_median, threshold)` → `ZoneBadgeValue`
- [x] Badge calculado com mediana parcial após cada zona concluir enriquecimento
- [x] SSE `zone.badges.updated` com `{"provisional": true, "based_on": "X/Y zonas"}`
- [x] Quando todas as zonas concluem: recalcula com mediana real → SSE `zones.badges.finalized`
- [x] `zones.badges_provisional = false` após finalização

**Verificação:** com 3 zonas enriquecendo: 1ª a concluir emite badge provisional;
após 3ª: `zones.badges.finalized` emitido exatamente uma vez. ✅

#### M4.6 — Frontend Etapas 3 e 4 ✅
- [x] **Etapa 3:** barra de progresso real (% do SSE), etapa corrente, botão cancelar ativo
- [x] Zonas aparecem no mapa progressivamente ao receber `job.partial_result.ready`
- [x] Rótulos numéricos nos polígonos (order por `travel_time_minutes`)
- [x] **Etapa 4:** lista ordenada por `travel_time_minutes` asc
- [x] Badges exibidos com indicador provisional/finalizado
- [x] Filtros: modal, tempo máximo, badge mínimo
- [x] CTA "Buscar imóveis" visível na zona selecionada

**Verificação:** cancelar durante Etapa 3 → spinner para; dados parciais persistem na lista. ✅

---

### Fase 5 — Imóveis: scrapers + deduplicação + cache 🔄

**Objetivo:** scrapers Playwright integrados ao sistema de filas com cache geoespacial.
**Esforço estimado:** 10–12 dias · **Status:** 🔄 Em progresso
**Dependências bloqueantes:** M4.3. `worker-scrape-browser` rodando em Hostinger VPS.

#### M5.1 — Tabelas e máquina de estados ✅
- [x] Migrations: `properties`, `listing_ads`, `listing_snapshots`, `zone_listing_caches`
- [x] `ZoneCacheStatus` implementado como máquina de estados explícita:
  `pending → scraping → partial → complete | failed | cancelled_partial`
- [x] Toda transição de estado passa por método único `transition_to(new_state)` com validação

**Verificação:** tentar `transition_to(complete)` a partir de `pending` → `InvalidStateTransition`. ✅

#### M5.2 — Lock de scraping ✅
- [x] Lock Redis: `SET scraping_lock:{fingerprint}:{config_hash} 1 EX 300 NX`
- [x] Worker tenta adquirir lock antes de iniciar scraping; se falhar → aguarda + reabre cache
- [x] Lock liberado explicitamente em `finally` (evita esperar TTL em sucesso)
- [x] Teste: duas goroutines tentam lock para mesma zona → somente uma scrape

**Verificação:** teste de lock concorrente passa sem escrita duplicada no banco.

#### M5.3 — Adaptadores Playwright ✅
- [x] `QuintoAndarScraper` migrado do script legado para handler Dramatiq
- [x] `ZapImoveisScraper` migrado
- [x] `VivaRealScraper` migrado
- [x] Cada scraper: user-agent realista, delays entre ações, `robots.txt` verificado
- [x] `scraping_degradation_events` criado quando `success_rate < 85%` em 24h

**Verificação:** scraper de QA, ZP e VP retornam ≥ 5 imóveis para zona de teste em SP sem erro 4xx/5xx.

#### M5.4 — Stale-while-revalidate e hit parcial ✅
- [x] Hit total: cache `complete` + dentro do TTL → retorna imediatamente
- [x] Hit parcial: cache por interseção de polígonos (`ST_Within`) com outra zona de geometria similar
- [x] Miss total: registra demanda e retorna fila para prewarm; não enfileira scraping sob demanda
- [x] `PreliminaryResultThresholds` aplicados antes de sinalizar `listings.preliminary.ready`

**Verificação:** buscar imóveis em zona A → criar zona B que cobre 70% de A → resultado parcial de A serve para B.

#### M5.5 — Deduplicação ✅
- [x] `compute_property_fingerprint(address_normalized, lat, lon, area_m2, bedrooms)` → SHA-256
- [x] Mesmo imóvel em 2 plataformas → 1 `property`, 2 `listing_ads`
- [x] `current_best_price` calculado como `MIN(price)` entre listing_ads ativos
- [x] `second_best_price` = segundo menor preço ativo (mostra economia multi-plataforma)
- [x] Badge de duplicidade: `"Disponível em 2 plataformas · menor: R$ X"`

**Verificação:** inserir mesmo imóvel via 2 plataformas → `SELECT count(*) FROM properties WHERE fingerprint = :fp` = 1. ✅ (2026-03-22: `property_count=1`, `listing_ads_count=2`, `current_best_price=2800.00`, `second_best_price=3100.00`)

#### M5.6 — `listing_search_requests` ✅
- [x] Registrar somente buscas confirmadas pelo clique em "Buscar imóveis" na Etapa 5, inclusive cache hit e cache miss
- [x] Persistir `zone_fingerprint`, `search_location_normalized`, `search_type`, `usage_type`, `platforms_hash` e `requested_at`
- [x] Busca de usuário FREE sem cache também entra na fila lógica de demanda para o prewarm seguinte
- [x] Query base da Fase 7: agregação das buscas das últimas 24h por endereço/search location

**Verificação:** 3 buscas para o mesmo endereço em 24h → agregação retorna `demand_count = 3`. ✅ (2026-03-22: demand_count=3, address isolation ✓, 8 unit tests passing)

#### M5.7 — Frontend Etapas 5 e início de 6 ✅
- [x] **Etapa 5:** combobox autocomplete filtrado por `ST_Contains(zone, address_point)`
- [x] Bairros > logradouros > referências na ordenação do autocomplete
- [x] "Buscar imóveis" habilitado somente após endereço selecionado
- [x] **Etapa 6 inicial:** listagem de imóveis com cache (badge de frescor: `"Dados de Xh atrás"`)
- [x] Diff incremental: novos/removidos ao revalidar sem recarregar lista inteira
- [x] Cards: foto, preço, metragem, plataforma, badge de duplicidade, link externo

**Verificação:** imóvel aparece em < 500ms (cache hit); diff ao revalidar não pisca a lista. ✅ (2026-03-22: `ui/src/App.test.tsx` valida `firstClickElapsed < 500ms`, mensagem de diff `+1/-1`, e preservação do mesmo nó DOM para card estável)

---

### Fase 6 — Dashboard + relatório PDF 🔄

**Objetivo:** análise urbana completa, favoritos de imóveis e zonas, geração de PDF para compartilhamento.
**Esforço estimado:** 7–8 dias · **Status:** 🔄 Em progresso
**Dependências bloqueantes:** M4.5, M5.5.

#### M6.1 — Rollups de preço ✅
- [x] `property_price_rollups` calculados periodicamente (diário ou por trigger de ingestão)
- [x] Campos: `date`, `zone_fingerprint`, `search_type`, `median_price`, `p25_price`, `p75_price`, `sample_count`
- [x] Retenção: 365 dias de histórico

**Verificação:** após ingestão de 20 imóveis → rollup calculado; mediana dentro do IQR esperado. ✅ (2026-03-22: `apps/api/tests/test_phase6_price_rollups.py` — 15 passed; cenário de 20 preços sintéticos valida `is_median_within_iqr`; trigger por ingestão em `workers/handlers/listings.py`; retenção `RETENTION_DAYS=365`)

#### M6.2 — Dashboard da zona ✅
- [x] **Aba Dashboard** no frontend (Etapa 6, segunda aba):
  - Preço mediano atual + variação (↑↓) vs. mês anterior
  - LineChart: histórico de 30 dias (FREE) / 90 dias (PRO) com `dot={false}` acima de 90 pontos
  - BarChart: distribuição por faixas de aluguel/compra (10 faixas)
  - Segurança: contagem de ocorrências + badge
  - Área verde: m² + badge
  - Risco de alagamento: % da área + badge
  - POIs: contagem por categoria (top 6 categorias)
  - Transporte: tempo médio ao ponto-semente + linhas disponíveis

**Verificação:** Dashboard carrega com dados reais para zona de teste; LineChart mostra exatamente 30 pontos para sessão FREE. ✅ (2026-03-22: `ui/src/App.test.tsx` valida aba Dashboard, `Pontos exibidos: 30`, `Tempo médio ao ponto-semente: 41 min`, `7 linhas (3 usadas)` e top 6 categorias de POI com corte da 7ª categoria; milestone fechado por confirmação explícita do responsável)

#### M6.3 — Job `REPORT_GENERATE` ⬜ -> **SUSPENSO**
- [ ] Template Jinja2 HTML com seções: cabeçalho da jornada, mapa (imagem base64), lista de zonas comparativa, detalhes dos imóveis, dashboard
- [ ] WeasyPrint: HTML → PDF
- [ ] Upload para R2/S3; signed URL com TTL de 7 dias
- [ ] `GET /reports/{id}/url` regenera signed URL sem re-gerar o PDF
- [ ] `report.ready` SSE com `{url, expires_at}`

**Verificação:** PDF gerado em < 20s para jornada com 5 zonas e 20 imóveis; tamanho < 5MB.

#### M6.4 — Captura do mapa no frontend ⬜-> **SUSPENSO**
- [ ] `MapShell` inicializado com `preserveDrawingBuffer: true`
- [ ] `map.getCanvas().toDataURL('image/png')` chamado antes de `POST /reports`
- [ ] Imagem incluída no payload (base64); endpoint valida presença da imagem
- [ ] Fallback: se canvas vazio (todo transparente) → erro descritivo para o usuário

**Verificação:** relatório gerado com imagem de mapa não-transparente.

#### M6.5 — Mapa de acessibilidade de imóvel ⬜-> **SUSPENSO**
- [ ] "Ver acessibilidade" em card de imóvel → mapa mostra rota a pé até ponto de transporte
- [ ] Rotas para categorias de POI: escola, supermercado, farmácia, parque (top 4)
- [ ] Alternância entre categorias sem recarregar (Zustand: categoria ativa → layer toggle)
- [ ] Distância e tempo estimado exibidos no painel

**Verificação:** clicar "Ver acessibilidade" → 5 rotas aparecem no mapa sem piscar.

#### M6.6 — Saldo de créditos e CTA de cadastro ⬜-> **SUSPENSO**
- [ ] Sessão anônima próxima de zerar créditos (≤ 15) → banner `"Cadastre-se e ganhe 30 créditos extras"`
- [ ] Operação com créditos insuficientes → modal com saldo atual, custo da operação e botão "Comprar créditos" (redireciona para Fase 8)
- [ ] `GET /account/credits/session` retorna `{balance}` para sessões anônimas (lê Redis)
- [ ] Créditos de sessão exibidos no header da aplicação (badge)

**Verificação:** sessão nova → consumir 25 créditos → banner de baixo saldo aparece; consumir os 5 restantes → modal de créditos insuficientes ao tentar nova operação.

#### M6.7 — Favoritos de imóveis ✅
- [x] Tabela `user_listing_favorites` (migration `20260413_0024`)
- [x] `POST /favorites/listings` salva snapshot do card (payload JSONB)
- [x] `GET /favorites/listings` lista favoritos do usuário autenticado; suporte a analytics por zona
- [x] `DELETE /favorites/listings/{listing_key}` remove favorito
- [x] Frontend: botão de favorito nos cards de imóvel; painel `FavoritesPanel` listando favoritos
- [x] Criação manual de favorito por URL (módulo `apps/api/src/modules/favorites/manual.py`): normaliza a URL, raspa metadados básicos e cria snapshot

**Verificação:** salvar imóvel como favorito → aparece em `GET /favorites/listings`; deletar → não aparece mais. ✅ (2026-04-13)

#### M6.8 — Favoritos de zonas ✅
- [x] Tabela `user_zone_favorites` (migration `20260422_0025`)
- [x] `POST /zone-favorites` salva snapshot de zona (badges, métricas, fingerprint)
- [x] `GET /zone-favorites` lista zonas favoritas com analytics enriquecidos
- [x] `DELETE /zone-favorites/{zone_key}` remove zona favorita
- [x] Service `apps/api/src/modules/zone_favorites/service.py` com analytics de dashboard para zonas salvas (`address_scope="all_addresses"`)
- [x] Frontend: `AuthContext` gerencia lista de favoritos de zona; botão de salvar zona no painel
- [x] Dashboard de preços de zonas salvas cobre todos os bairros da cidade sem restrição por busca

**Verificação:** salvar zona → aparece em `GET /zone-favorites` com métricas; analytics de preço mostra dados citywide. ✅ (2026-04-22)

---

### Fase 7 — Scheduler noturno (prewarm + inclusão Pro Max) ⬜

**Objetivo:** atualizar a base de imóveis durante a janela noturna, cobrindo (1) endereços efetivamente pesquisados nas últimas 24 h e (2) endereços de imóveis salvos por usuários do plano Pro Max.
**Esforço estimado:** 5–6 dias · **Status:** ⬜ Não iniciada
**Dependências bloqueantes:** M5.6, M6.5, M8.3 (modelo de planos).

#### M7.1 — APScheduler integrado ⬜
- [ ] APScheduler em `worker-scheduler` dedicado
- [ ] Jobs não bloqueiam API nem `worker-general`
- [ ] Um cron registrado: `03:00` → `prewarm_run_nightly(lookback_hours=24, limit_demand=100, limit_pro_max=500)`
- [ ] Logs de início/fim de cada run com `prewarm_last_run_status`

**Verificação:** scheduler inicia com o stack e o cron de 03:00 é registrado corretamente.

#### M7.2 — Conjunto-alvo (demanda 24h ∪ saved Pro Max) ⬜
- [ ] Query 1: agrega `listing_search_requests` com `requested_at >= now() - interval '24 hours'` (até `limit_demand`)
- [ ] Query 2: `user_listing_favorites JOIN subscriptions JOIN plans` filtrando `plans.slug = 'pro_max'` e `subscriptions.status IN ('active','past_due')` (até `limit_pro_max`)
- [ ] Pro (sem Pro Max) **excluído** (deduplicação por `user_id` no `WHERE`)
- [ ] União deduplicada por `(address_normalized, search_type, usage_type)` com `trigger_source` registrado por linha
- [ ] Cada item enfileira `LISTINGS_PREWARM` com `Priority.PREWARM = 5`
- [ ] `last_prewarmed_at` do cache + `last_refreshed_at` em `user_listing_favorites` atualizados ao concluir

**Verificação:** usuário Pro Max com 3 imóveis salvos sem busca recente → run noturna processa esses endereços e atualiza `last_refreshed_at`.

#### M7.3 — Sem fallback e sem cold start artificial ⬜
- [ ] Nenhuma query por zonas populares, geohash, região ou listas manuais
- [ ] Se ambos os conjuntos estão vazios, o scheduler não enfileira scraping
- [ ] FREE sem cache recebe UI de fila para o próximo prewarm; não há scraping imediato

**Verificação:** base zerada + nenhuma busca em 24h + nenhum usuário Pro Max com salvos → prewarm executa sem itens e finaliza como `success_empty`.

#### M7.4 — Métricas e alertas de prewarm ⬜
- [ ] Métrica `prewarm_coverage_rate`: `enderecos_processados / enderecos_enfileirados`
- [ ] Métrica `prewarm_target_count_24h`: agora segmentada por `trigger_source` (`demand_24h`, `pro_max_saved`)
- [ ] Métrica `prewarm_pro_max_inclusion_count`: número de endereços únicos vindos de salvos Pro Max por run
- [ ] `prewarm_last_run_status`: `success | success_empty | partial | failed`
- [ ] **Alerta crítico 1:** prewarm não inicia em 30 min → `prewarm_start_overdue`
- [ ] **Alerta crítico 2:** `prewarm_coverage_rate < 0.60` quando `prewarm_target_count_24h > 0`

**Verificação:** matar `worker-scrape-browser` durante o prewarm → alerta gerado em < 35 min.

#### M7.5 — UI para endereço sem cache ⬜
- [ ] Free/Anônimo sem cache: banner `"Este endereço entrou na fila de atualização noturna."`
- [ ] Linha secundária: `"Se houver anúncios disponíveis, eles aparecerão após a próxima atualização."`
- [ ] CTA contextual por plano:
  - Anônimo/Free: `"Cadastre-se / Atualize para Básico — scraping sob demanda"`
  - Básico: `"Atualize para Pro — seus salvos atualizados toda noite"`
- [ ] Endereço com cache fresco exibe badge: `"Dados de 10h atrás"`
- [ ] Pro: cards de imóveis salvos exibem `"Atualizado hoje · run noturna"` quando `last_refreshed_at` está dentro de 24 h

**Verificação:** endereço pesquisado hoje sem cache mostra banner correto; após o prewarm seguinte, o banner some, a lista é servida do cache, e usuário Pro vê o badge "Atualizado hoje" em seus salvos correspondentes.

---

### Fase 8 — Auth + planos + ativação por Pix 🔄

**Objetivo (v2.4 reescopo):** produto monetizável com **planos mensais ativados via Pix com QR Code / Pix Copia e Cola**, enforcement de entitlements em API+UI. Stripe Billing fica para Fase 10.
**Esforço estimado:** 12–14 dias · **Status:** 🔄 Em progresso (M8.1–M8.8 implementados; M8.9 pendente)
**Dependências bloqueantes:** M6.5, M7.4.

#### M8.1 — Auth e-mail/senha ✅
- [x] `POST /auth/register` — cria usuário com email + senha (PBKDF2-HMAC-SHA256, 600k iter)
- [x] `POST /auth/login` — valida credenciais, cria sessão em `user_sessions`, seta cookie HTTP-only `auth_session`
- [x] `POST /auth/logout` — revoga sessão no banco e limpa cookie
- [x] `GET /auth/me` — retorna status de autenticação

**Verificação:** `POST /auth/register` → usuário criado; `POST /auth/login` → cookie `auth_session`; `GET /auth/me` → `is_authenticated=true`. ✅ (2026-04-12)

#### M8.2 — Migração anônimo → Free ✅
- [x] Hook `on_after_register`: detecta `anonymous_session_id` no cookie
- [x] Transação atômica:
  - Migra jornadas para `user_id`
  - Cria `plan_activations(plan='free', status='active', 30 dias)`
  - Insere `user_credits(cycle_credits=350, monthly_quota=350)` — **saldo anônimo NÃO somado**
  - Audita ledger: `signup_grant_free` (+350)
- [x] Cookie anônimo limpo + `DEL credit:session:{session_id}` no Redis

**Verificação:** anônimo com 300/350 usados → cadastrar → `cycle_credits = 350`; ledger registra `signup_grant_free`. ✅ (2026-04-26)

#### M8.3 — Planos e entitlements ✅
- [x] Migration `20260426_0027`: `plans`, `plan_entitlements`, `user_credits`, `credit_ledger`, `payments`, `pix_payment_data`, `plan_activations`, `pro_max_refresh_targets`, `pro_max_refresh_runs`, `webhook_events`
- [x] Seed: 5 planos com `plan_entitlements` conforme Seção 5
- [x] `resolve_entitlements(user_id) → ResolvedEntitlements` com cache Redis (TTL 60s, invalidado em `plan_activations`)
- [x] `GET /account/plan` retorna `{plan, status, started_at, ends_at, entitlements}`

**Verificação:** seed aplicado com 5 planos e entitlements; `GET /account/plan` retorna plano ativo do usuário. ✅ (2026-04-26)

#### M8.4 — Créditos por ciclo ✅
- [x] `check_and_consume(user_id, step)` consome FIFO: `cycle_credits → rollover_balance → legacy_balance`
- [x] Anônimo: `credit:session:{session_id}` Redis com 350, TTL 7 dias
- [x] Saldo insuficiente → `InsufficientCreditsError` com `{required, balance}`
- [x] `GET /account/credits` retorna `{cycle, rollover, legacy, total, cycle_ends_at}`

**Verificação:** FIFO correto; `InsufficientCreditsError` lançado quando saldo < custo; ledger auditável. ✅ (2026-04-26)

#### M8.5 — Pix checkout ✅
- [x] `payments` e `pix_payment_data` criados via migration
- [x] `POST /billing/pix/checkout` — gera payload Pix Copia e Cola, retorna `payment_id`
- [x] TTL configurável via `PIX_PAYMENT_EXPIRATION_MINUTES`
- [x] `GET /billing/payments/{id}` — retorna status; auto-expira pendentes vencidos
- [x] `POST /billing/payments/{id}/cancel` — cancela pagamento pendente

**Verificação:** checkout retorna `pix_copy_paste` e `status=pending`; GET após expiração retorna `status=expired`. ✅ (2026-04-26)

#### M8.6 — Confirmação Pix e ativação de plano ✅
- [x] `POST /admin/billing/pix/{id}/confirm` — confirmação manual por admin
- [x] `POST /billing/pix/callback` — callback com validação de assinatura HMAC (`PIX_CALLBACK_SECRET`)
- [x] `activate_plan_from_pix(payment_id)` — transação atômica com idempotência (`PaymentAlreadyProcessedError`)
- [x] Criação de `plan_activation` por 30 dias; replace de ativação anterior
- [x] Upsert de `user_credits` com nova cota; ledger auditado com `reason='pix_plan_activation'`

**Verificação:** confirmar pagamento → `plan_activations.status=active`; reconfirmar → `AlreadyProcessed`. ✅ (2026-04-26)

#### M8.7 — Renovação manual por Pix ✅
- [x] CTA exibido 7 dias antes de `ends_at` na página `/conta`
- [x] Novo `payment` Pix gerado com `payment_type='plan_renewal'`
- [x] Ao confirmar: novo `plan_activation` com `replaced` no anterior; ledger com `reason='pix_plan_renewal'`

**Verificação:** CTA de renovação aparece ≤ 7 dias antes do vencimento; novo ciclo iniciado após confirmação. ✅ (2026-04-26)

#### M8.8 — UI `/planos` e `/conta` ✅
- [x] `PlanosPage`: modal com cards dos 4 planos pagáveis, CTA "Assinar via Pix" ou "Plano atual"
- [x] `PixModal`: Pix Copia e Cola, timer com countdown, polling 5s, estados pending/paid/expired/cancelled
- [x] `ContaPage`: plano ativo, saldo de créditos (cycle/rollover/legacy), barra de uso, CTA "Renovar via Pix"
- [x] Header: botões Planos (sempre visível) e Conta (logado) no `AuthAccessCard`

**Verificação:** fluxo Free → Básico via PixModal; plano ativo e créditos exibidos em ContaPage. ✅ (2026-04-26)

#### M8.9 — Testes E2E Pix
- [ ] anônimo → Free (350 créditos);
- [ ] Free → Básico por Pix;
- [ ] confirmação do pagamento;
- [ ] ativação do plano;
- [ ] consumo de créditos;
- [ ] expiração de Pix pendente.

**Verificação:** todos os testes E2E passam em staging sem intervenção manual.

---

### Fase 9 — Plano Pro Max (refresh dedicado) ⬜

**Objetivo:** entregar a atualização automática controlada dos favoritos do plano Pro Max via fila e scheduler dedicados, com franquia, cadência e elegibilidade explicitamente limitadas.
**Esforço estimado:** 6–8 dias · **Status:** ⬜ Não iniciada
**Dependências bloqueantes:** M7.2, M8.3, M8.5.

#### M9.1 — Fila + scheduler dedicados ⬜
- [ ] Fila Dramatiq `pro_max_refresh` (concorrência 1, prioridade `Priority.PRO_MAX_REFRESH = 3`)
- [ ] APScheduler: cron `04:30` → `pro_max_refresh_run(max_per_run=200)` (após o prewarm geral)
- [ ] Handlers `pro_max_refresh_listing` e `pro_max_refresh_zone` reaproveitam scrapers e queries de zona existentes (idempotente; cache hit não dispara scrape novo)

**Verificação:** scheduler dispara às 04:30; cada item alvo emite `last_refreshed_at` atualizado.

#### M9.2 — Reconciliação de targets ⬜
- [ ] Função `reconcile_pro_max_targets(user_id)` chamada em:
  - `on_favorite_change` (insert/update/delete em `user_listing_favorites`/`user_zone_favorites`)
  - `on_subscription_change` (mudança de plano que afeta `auto_refresh_policy`)
  - Início de cada `pro_max_refresh_run` (revalidação preventiva)
- [ ] Política: ativos = `view_state='visible'` E (`last_viewed_at >= now() - eligibility_days` OU `priority_flag=true`); ordenados por `priority_flag DESC, last_viewed_at DESC`; cap em `max_zones`/`max_listings`
- [ ] Excedente fica `is_active=false` mas mantém histórico para promoção manual

**Verificação:** usuário Pro Max com 35 imóveis salvos: 30 em `pro_max_refresh_targets.is_active=true`; 5 mais antigos `is_active=false`. Marcar 1 deles como `priority_flag=true` → reconciliação promove + rebaixa o último não-priority.

#### M9.3 — Cadência e backoff ⬜
- [ ] Sucesso: `last_refreshed_at = NOW()`, `next_refresh_due_at = NOW() + 7d`, `failure_count = 0`
- [ ] Falha: `failure_count++`, backoff `[1d, 2d, 4d]`; ao chegar a 3 falhas → `is_active=false`, badge UI "Refresh manual"
- [ ] Run regista resumo em `pro_max_refresh_runs` (started_at, finished_at, totals, status)

**Verificação:** simular falha 3x num target → após 3ª, item desativado e badge "Refresh manual" exibido.

#### M9.4 — UI Pro Max ⬜
- [ ] Aba "Sob refresh automático" no `FavoritesPanel` listando `pro_max_refresh_targets.is_active=true` com `next_refresh_due_at`
- [ ] Toggle de `priority_flag` em cada card
- [ ] Badge "Refresh em N dias" / "Atualizado há Xh" baseado em `last_refreshed_at`
- [ ] Modal de promoção: "Você está usando 30/30. Promover este item rebaixará o item X (último visto há Y dias). Continuar?"
- [ ] Página `/planos`: Pro Max mostra benefícios reais ("Atualização automática semanal · até 10 zonas + 30 imóveis · prioridade configurável")

**Verificação:** usuário Pro upgrade → Pro Max → aba aparece com seus salvos elegíveis populados em < 5s; toggle de priority preserva estado entre reloads.

#### M9.5 — Métricas e alertas ⬜
- [ ] `pro_max_refresh_run_duration_seconds` (alvo: < 30 min)
- [ ] `pro_max_refresh_success_rate` (alvo: > 90%)
- [ ] `pro_max_refresh_skipped_quota` (gauge — itens ignorados por quota)
- [ ] Alerta: `success_rate < 80%` em 2 runs consecutivas → investigar scrapers
- [ ] Alerta: run não inicia em 30 min do horário programado

**Verificação:** matar `worker-general` durante run → alerta gerado em < 35 min.

#### M9.6 — Testes E2E Pro Max ⬜
- [ ] Playwright: usuário Pro Max com 5 imóveis salvos → run noturna manual → `last_refreshed_at` atualizado em todos
- [ ] Cenário de exceder franquia: salvar 35 → 30 ativos visíveis na aba; promover 1 do excedente
- [ ] Cenário de downgrade Pro Max → Pro: targets desativados; aba some

**Verificação:** testes E2E passam em staging sem intervenção manual.

---

### Fase 10 — Stripe Billing e automação de recorrência ⬜

**Objetivo:** substituir a operação Pix manual por cobrança recorrente automatizada.
**Esforço estimado:** 10–12 dias · **Status:** ⬜ Backlog
**Dependências bloqueantes:** M8 concluída e validada comercialmente.

#### M10.1 — Stripe Billing
- [ ] criar produtos e prices no Stripe;
- [ ] `POST /billing/stripe/subscribe`;
- [ ] checkout de assinatura via Stripe Checkout Session.

#### M10.2 — Customer Portal
- [ ] `POST /billing/portal` → Stripe Customer Portal session;
- [ ] cancelamento de assinatura;
- [ ] troca de cartão.

#### M10.3 — Webhooks Stripe
- [ ] `customer.subscription.created`;
- [ ] `customer.subscription.updated`;
- [ ] `invoice.payment_succeeded` → renovar `plan_activation` + `monthly_grant`;
- [ ] `invoice.payment_failed` → grace period 7 dias.

#### M10.4 — Proration e mudança de plano
- [ ] upgrade imediato com proration;
- [ ] downgrade no fim do ciclo;
- [ ] grace period past_due;
- [ ] rebaixamento automático para Free após grace.

#### M10.5 — Migração Pix → Stripe
- [ ] usuários Pix podem migrar para recorrência Stripe;
- [ ] preservar `plan_activation` atual;
- [ ] preservar saldo e entitlements.

---

## 13. Segurança

### Token Mapbox

- `MAPBOX_ACCESS_TOKEN` exclusivamente no backend, nunca exposto ao cliente.
- Geocoding via `POST /api/geocode` (proxy server-side).
- POIs via módulo backend dedicado (`pois`) chamando Search Box Category Search.
- Rate limit e orçamento por operação registrados em `external_usage_ledger`.

### Rate limiting (Redis-based)

| Camada | Limite autenticado | Limite anônimo |
|---|---|---|
| Geocoding | 150 req/hora | 50 req/hora |
| POIs (Search Box Category Search) | 90 req/hora | 30 req/hora |
| Criação de jornada | 20/dia | 5/dia |
| Geração de relatório | sem limite fixo (controlado por créditos) | sem limite fixo (controlado por créditos) |

Soft limit → avisa UI, ativa fallback.
Hard limit → bloqueia a operação, mantém fluxo via cache/seleção manual.

**Três fallbacks em cascata para geocoding:**
1. Cache Redis (string normalizada) → ~70% das buscas repetidas
2. Banco (histórico persistido) → ~20% dos casos de rate limit
3. Seleção manual no mapa → sempre disponível

### Scraping

- Playwright isolado em `worker-scrape-browser` (Hostinger VPS), sem proxy por padrão.
- `user-agent` realista, delays humanos entre ações.
- `robots.txt` verificado durante desenvolvimento de cada adapter.
- Bright Data somente como escape hatch por plataforma, por configuração.

### Pix

Regras obrigatórias:
- toda confirmação de pagamento deve ser idempotente;
- pagamento expirado não ativa plano;
- confirmação manual exige perfil admin;
- callback Pix deve validar assinatura/secret (`PIX_CALLBACK_SECRET`);
- `payment_id` não pode ser reutilizado;
- um pagamento pago não pode ativar plano duas vezes;
- Pix Copia e Cola não deve conter dados sensíveis além do necessário.

### Webhooks Stripe (futuro — Fase 10)

- `stripe.Webhook.construct_event()` obrigatório em todos os eventos.
- Idempotência por `webhook_events (provider='stripe', event_id)` UNIQUE.
- Validar `customer_id ↔ user_id` antes de mutar `plan_activations`/`user_credits`.
- Nenhum crédito concedido sem evento validado.

### Enforcement de entitlements

- Toda capability de plano (limites de save, customização de parâmetros, métricas, refresh) é validada **no servidor**, nunca apenas no cliente.
- Cache de entitlements (Redis, TTL 60s) é invalidado por `plan_activations` ao ativar/expirar ciclo.
- Endpoints de billing (`/billing/pix/checkout`, `/billing/pix/confirm`) exigem autenticação.
- `priority_flag` e reconciliação `pro_max_refresh_targets` rejeitam requests de planos sem `auto_refresh_policy='managed_queue'` com `403`.

### Cookies

- `anonymous_session_id`: `HttpOnly`, `SameSite=Lax`, `Secure` em produção.
- `fastapi-users` cookies: rotação automática de sessão a cada login.

### Magic link

- Token: 32 bytes via `secrets.token_urlsafe()`.
- Expiração: 15 minutos. Single-use.
- Comparação timing-safe via `hmac.compare_digest()`.

---

## 14. Observabilidade

### Logging

JSON estruturado em todos os processos.
Campos obrigatórios: `request_id · journey_id · job_id · user_id|session_id · level · message · timestamp`

### Métricas operacionais

| Métrica | Alerta |
|---|---|
| `valhalla_isochrone_p95_ms` | > 500ms → avaliar escalar VPS |
| `scraping_success_rate_{platform}` | < 85% (24h) → habilitar Bright Data |
| `scraping_empty_result_rate_{platform}` | > 20% (24h) → habilitar Bright Data |
| `prewarm_coverage_rate` | < 60% dos endereços-alvo → alerta crítico |
| `prewarm_last_run_status` | `failed` → alerta crítico |
| `prewarm_pro_max_inclusion_count` | gauge — endereços únicos vindos de salvos Pro Max por run |
| `pro_max_refresh_run_duration_seconds` | > 30 min → investigar |
| `pro_max_refresh_success_rate` | < 80% em 2 runs consecutivas → investigar |
| `pro_max_refresh_skipped_quota` | gauge — itens ignorados por franquia |
| `pix_payment_created_count` | cobranças Pix criadas |
| `pix_payment_paid_count` | pagamentos Pix confirmados |
| `pix_payment_expired_count` | Pix expirados sem confirmação |
| `pix_payment_conversion_rate` | taxa de conversão Pix |
| `pix_activation_lag_seconds` | tempo entre pagamento Pix e ativação de plano; > 60s → alerta |
| `pix_pending_overdue_count` | Pix pendentes vencidos — alerta se crescente |
| `plan_activation_count{plan}` | ativações por plano |
| `plan_renewal_count{plan}` | renovações manuais por plano |
| `plan_expiration_count{plan}` | ciclos expirados por plano |
| `mapbox_poi_request_error_rate` | > 10% (24h) → investigar limites/token/categorias |
| `job_queue_depth_{queue}` | > 50 → investigar |
| `db_connection_pool_waiters` | > 5 → escalar pool |

### Métricas de produto

- Tempo para listar pontos de transporte.
- Tempo para primeira zona aparecer.
- Tempo total por job (por tipo).
- Taxa de cancelamento por etapa.
- Cache hit por provedor (geocoding, isócrona, listings).
- Custo externo estimado por jornada (`external_usage_ledger`).
- Quantidade média de imóveis por zona.
- Taxa de duplicidade de imóveis.
- Taxa de conversão Free → Básico → Pro → Pro Max (funil de planos).
- MRR (monthly recurring revenue) por plano.
- Churn mensal por plano.
- Distribuição de uso de cota mensal por plano (p50/p90 de % consumido).
- Taxa de uso de rollover (% de usuários que aproveitam o rollover_balance).
- Top-ups avulsos por plano (sinaliza se cota está mal dimensionada).

### Alertas críticos

1. Prewarm não iniciou em 30 min do horário programado.
2. < 60% dos endereços/search locations-alvo processados com sucesso no prewarm.
3. API sem resposta por > 60s (health check).
4. `worker-scrape-browser` sem heartbeat por > 5 min.
5. Postgres: `connection pool waiters > 10` por > 2 min.
6. Pro Max refresh run não iniciou em 30 min do cron 04:30, ou `pro_max_refresh_success_rate < 80%` em 2 runs consecutivas.
7. `pix_activation_lag_seconds > 60` em qualquer confirmação Pix (pagamento confirmado mas plano não ativado).
8. `pix_pending_overdue_count` crescente há > 24h (Pix manual sem confirmação).
9. Webhook com `processed=false` há > 5 min em `webhook_events` (loop quebrado).

---

## 15. Estratégia de Testes

### Pirâmide (4 camadas)

```
              ┌──────┐
              │  E2E │  5%  ── Playwright: fluxo completo em staging
             ┌┴──────┴┐
             │ Smoke  │  5%  ── Dataset A: transport → zonas → imóveis
            ┌┴────────┴┐
            │Integration│ 30% ── API + DB real, worker + StubBroker
           ┌┴──────────┴┐
           │    Unit    │ 60% ── serviços com DI (sem DB/Redis real)
           └────────────┘
```

### Regras

**Unitário:** serviços de domínio com implementações fake injetadas pelo construtor.
`StubBroker` para jobs — sem Redis. `AsyncSession` mock para DB.

**Integração:** API real com Postgres + Redis de teste (Docker).
Workers com `StubBroker` + banco real.

**Smoke (Dataset A):** `scripts/e2e_smoke_dataset_a.ps1` com coordenadas fixas,
fluxo completo em staging. Roda no CI antes de qualquer deploy em produção.

**E2E:** Playwright — configuração → transporte → zonas → imóveis → relatório.
Cenários adicionais (v2.4): jornada Free→Básico via Pix, Pro Max com salvos atualizados pela run noturna, Pro Max com 35 salvos (30 ativos + 5 fora de franquia + promoção de priority).

### Testes unitários de billing Pix

- geração de payload Pix;
- cálculo de expiração;
- ativação de plano a partir de pagamento confirmado;
- concessão de créditos via ledger;
- consumo FIFO (cycle → rollover → legacy);
- idempotência de confirmação;
- enforcement de entitlements.

### Testes de integração de billing Pix

- `POST /billing/pix/checkout`;
- `GET /billing/payments/{id}`;
- confirmação manual via admin;
- ativação de plano e concessão de créditos;
- expiração de pagamento pendente;
- transição de ciclo e rollover.

### Fixtures obrigatórias

- GTFS feed reduzido (100 paradas, 10 linhas) para integração.
- Polígonos de vegetação e alagamento para 3 zonas de teste.
- 30 imóveis sintéticos nas 3 zonas.
- 5 planos seedados (`anonymous`, `free`, `basico`, `pro`, `pro_max`) com `plan_entitlements` correspondentes.
- 4 personas pré-criadas: anônimo (sessão), Free (350 cycle), Pro (4000 cycle, 5 salvos com `address_normalized`), Pro Max (35 salvos: 30 elegíveis + 5 fora de franquia + 1 priority).

### CI checks obrigatórios

`mypy` (strict em `core/` e `modules/`) · `ruff` · testes unitários ·
testes integração · smoke Dataset A em staging

---

## 16. Registro de Riscos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Playwright bloqueado pelas plataformas | Alta | Alto | `success_rate` monitorado; Bright Data como escape hatch por plataforma |
| Valhalla OOM (isócrona carro + prewarm) | Média | Alto | Concorrência 2 na fila `zones`; prewarm restrito a endereços demandados nas últimas 24h |
| Redis pub/sub congestionado | Baixa | Médio | Canal por `job_id`; cleanup automático ao desconectar |
| Prewarm não termina antes do pico matinal | Média | Alto | Limite de 100 endereços por run; alerta em 30 min; escalar VPS se p95 prewarm > 2h |
| S3/R2 signed URL expirada antes do download | Baixa | Baixo | Endpoint de regeneração; retenção de 30 dias |
| Custo Mapbox Search > orçamento mensal | Média | Médio | Cache efêmero; rate limit por operação; debounce; orçamento diário |
| Confirmação manual de Pix atrasar ativação | Média | Médio | Alerta de pendentes e painel admin; CTA na UI |
| Pagamento Pix confirmado duas vezes | Baixa | Alto | Idempotência por `payment_id` + `status=paid` |
| Pagamento expirado ativar plano | Baixa | Alto | Validação transacional: `expires_at < now()` → erro |
| Usuário pagar valor errado no Pix manual | Média | Médio | QR Code dinâmico com valor fixo; conferência manual por admin |
| Falta de recorrência automática aumentar churn | Alta | Médio | Lembretes antes do vencimento; CTA de renovação na UI |
| Pix manual aumentar carga de suporte | Média | Médio | Painel admin simples; status de pagamento claro na UI |
| Migração anônima → autenticado perdendo jornada | Baixa | Alto | Transação atômica; saldo anônimo descartado por design (auditado em ledger) |
| GTFS desatualizado gerando rotas incorretas | Média | Médio | Webhook Mobility Database dispara ingestão automática |
| WeasyPrint consumindo > 600MB | Baixa | Médio | Concorrência 1 na fila `reports`; timeout de job em 60s |
| Pro Max subprecificado | Média | Alto | Franquia explícita (10 zn + 30 lst, 7d cadência, eleg 30d); monitoramento de custo por refresh |
| Scraping sobrecarregar VPS | Média | Alto | Filas com concorrência limitada; prewarm limitado |
| Futuro Stripe exigir retrabalho | Baixa | Médio | `payments` genérico e `plan_activations` separado do provedor |
| Salvos expirados gerarem frustração | Média | Médio | UI clara com estado de expiração e CTA de renovação |
| Cache de entitlements stale na ativação | Baixa | Baixo | TTL 60s + invalidação por `plan_activations` |

---

## 17. Decisões Técnicas Fechadas

As decisões abaixo são **finais** para todas as fases.
Não reabrir sem análise de impacto documentada.

| Decisão | Escolha | Racional |
|---|---|---|
| Provedor de tiles | **MapTiler (único, forever)** | Zero código para escalar; upgrade só no painel |
| Framework frontend | **Next.js App Router** | SSR nativo, Vercel zero config, ecossistema |
| ORM / migrations | **SQLAlchemy 2 + Alembic** | Tipagem estrita, suporte PostGIS nativo |
| Broker de jobs | **Dramatiq** | `StubBroker` para testes; retry nativo por tipo via middleware |
| Isócrona / rota | **Valhalla self-hosted** | Sem ToS de armazenamento; cache por fingerprint; latência 80–200ms |
| Transporte público | **OTP 2 + GTFS** | Sem custo por request; dados locais; sem proibição de storage |
| Progresso real-time | **SSE (não WebSocket)** | Fluxo unidirecional; mais simples, proxy-friendly |
| Geocoding | **Mapbox Search Box API (proxy)** | Já integrado; custo baixo com cache Redis 24h |
| POIs | **Mapbox Search Box API — Category Search** | Busca sob demanda por categoria/raio com cache efêmero |
| PDF generator | **WeasyPrint** | HTML/CSS, SVG, Python-native, sem Node no worker |
| DI Fases 0–3 | **Composição manual no lifespan** | Baixa complexidade, sem overhead |
| DI Fase 4+ | **dependency-injector** | Container/Provider explícito, migração incremental |
| Scraping browser | **Playwright no Hostinger VPS** | IP brasileiro; isolado do api/worker-general |
| Proxy residencial | **Bright Data somente como escape hatch** | Ativação por plataforma; nunca base da arquitetura |
| Modelo de monetização | **Freemium + planos mensais + créditos por ciclo** | Separação clara entre uso ocasional e intenso |
| Cobrança prioritária | **Pix com QR Code / Pix Copia e Cola** | Menor complexidade para lançamento |
| Stripe | **Backlog futuro (Fase 10)** | Automação de assinatura depois da validação comercial |
| Ciclo do plano | **30 dias** | Simples para Pix manual e compatível com assinatura futura |
| Créditos por jornada | **80 créditos** | Jornada sem scraping sob demanda |
| Etapas monetizáveis | **4 × 20 créditos** | Scraping sob demanda indisponível em todos os planos |
| Créditos anônimos | **300** | Menor liberdade que o Free |
| Migração anônimo → Free | **Free recebe 350; não soma saldo anônimo** | Evita arbitragem |
| Plano Básico | **R$ 21,99 / 800 créditos** | Entrada acessível |
| Plano Pro | **R$ 90,99 / 4000 créditos** | Usuário intenso |
| Plano Pro Max | **R$ 312,99 / 20000 créditos** | Franquia superior ao Pro; sem scraping sob demanda |
| Refresh do plano Pro | **Não incluso** | Evita custo oculto |
| Refresh do plano Pro Max | **Não incluso** | Nenhum plano libera scraping/refresh sob demanda |
| Modelo de pagamento | **`payments` genérico** | Suporta Pix agora e Stripe depois |
| Ativação de plano | **`plan_activations`** | Desacopla plano ativo do provedor de pagamento |
| Confirmação Pix inicial | **Manual/admin ou callback opcional** | Permite lançar sem gateway completo |
| Renovação | **Manual por Pix na primeira versão** | Simples e suficiente para validação |
| Stripe Billing | **Fase 10** | Portal, retries e recorrência depois da validação comercial |
| Scraping arbitrário | **Nenhum plano libera scraping sob demanda** | Buscas sem cache registram demanda para prewarm controlado |
| Salvos pós-downgrade | **`over_limit_grace` 7d → `archived` (nunca delete)** | Recuperação total via upgrade; UI sempre mostra arquivados |
