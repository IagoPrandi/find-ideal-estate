# PRD — Find Ideal Estate

**Versão:** 2.0  
**Fonte canônica:** `analise_reformulacao_find_ideal_estate_v18_hostinger_poi_mapbox.md`  
**Última atualização:** 2026-03-15  
**Status:** Ativo

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
12. [Roadmap por Fase (0–8)](#12-roadmap-por-fase-08)
13. [Segurança](#13-segurança)
14. [Observabilidade](#14-observabilidade)
15. [Estratégia de Testes](#15-estratégia-de-testes)
16. [Registro de Riscos](#16-registro-de-riscos)
17. [Decisões Técnicas Fechadas](#17-decisões-técnicas-fechadas)

---

## 1. Visão do Produto

### Problema

Encontrar imóvel para alugar ou comprar em São Paulo é um processo fragmentado: o usuário compara plataformas separadas, faz cálculos de deslocamento mentalmente e não tem visão integrada de qualidade urbana (transporte, segurança, área verde, risco de alagamento) para os bairros candidatos.

### Solução

**Find Ideal Estate** é um ambiente de decisão imobiliária guiado por mapa. O usuário parte de um endereço de referência (trabalho, escola), configura seu perfil de deslocamento (modal, tempo máximo) e o produto:

1. Descobre pontos de transporte elegíveis no raio configurado;
2. Gera zonas geoespaciais de isócrona para cada ponto selecionado;
3. Enriquece cada zona com dados urbanos analíticos (segurança, verde, alagamento, POIs);
4. Busca e deduplica imóveis das principais plataformas dentro de cada zona;
5. Apresenta comparação objetiva com dados explicáveis — sem fórmulas opacas;
6. Gera relatório PDF para compartilhamento e arquivo.

### Princípios

1. **Mapa como plano principal.** A interface nunca esconde o mapa; o painel é auxiliar ao espaço.
2. **Progresso real, nunca spinner vazio.** Cada etapa de processamento emite eventos SSE granulares — o usuário sempre sabe o que está acontecendo.
3. **Dados explicáveis.** Nenhum indicador composto com pesos opacos. Métricas objetivas comparativas: tempo de viagem, m² de verde, ocorrências de segurança, preço mediano.

### Personas

| Persona | Situação | Necessidade principal |
|---|---|---|
| Relocador urbano | Mudar de bairro, manter emprego atual | Quais bairros permitem chegar ao trabalho em até 30 min de metrô? |
| Comprador de primeiro imóvel | Busca ativa com prazo definido | Comparar regiões por preço, segurança e acesso ao transporte |
| Profissional em mudança | Nova cidade ou cidade nova | Análise rápida sem conhecimento prévio dos bairros |

---

## 2. Progress Tracker

### Fases de backend / infraestrutura

| Fase | Título | Status | Concluída em | Observações |
|---|---|---|---|---|
| 0 | Fundação: monorepo, DB, CI | ✅ Concluída | 2026-03-16 | Stack validada no compose `onde_morar` (`api/postgres/redis`) + Alembic OK |
| 1 | Core domain: journey, job, SSE | ✅ Concluída | 2026-03-16 | M1.1-M1.4 concluídos com migration aplicada e smoke SSE Redis real |
| 2 | Dramatiq + worker infra | ✅ Concluída | 2026-03-17 | StubBroker/RedisBroker, retry policy, cancelamento cooperativo, watchdog, smoke SSE |
| 3 | Transporte: GTFS + Valhalla + OTP | 🔄 Em progresso | — | M3.1-M3.4 concluídos; restante bloqueia Fase 4 |
| 4 | Zonas: isócronas + enriquecimento | ⬜ Não iniciada | — | Bloqueia Fase 5 |
| 5 | Imóveis: scrapers + dedup + cache | ⬜ Não iniciada | — | Scrapers existem; precisa integração Dramatiq |
| 6 | Dashboard + relatório PDF | ⬜ Não iniciada | — | WeasyPrint + R2 |
| 7 | Scheduler noturno (prewarm) | ⬜ Não iniciada | — | APScheduler, prioridades de fila |
| 8 | Auth + planos + Stripe | ⬜ Não iniciada | — | fastapi-users, magic link, Resend |

### Fases de frontend

| Fase | Título | Status | Concluída em | Observações |
|---|---|---|---|---|
| FE0 | Setup Vite/React inicial | 🔄 Em progresso | — | Herdado do sistema anterior |
| FE1 | MapLibre + MapTiler integrado | 🔄 Em progresso | — | Tiles funcionando |
| FE2 | Etapa 1: formulário de config | 🔄 Em progresso | — | — |
| FE3 | Migração para Next.js App Router | ⬜ Não iniciada | — | Bloqueia FE4+ |
| FE4 | Etapa 2: seleção de transporte | ⬜ Não iniciada | — | — |
| FE5 | Etapa 3: progressão SSE + zonas | ⬜ Não iniciada | — | — |
| FE6 | Etapa 4: comparação de zonas | ⬜ Não iniciada | — | Badges incrementais |
| FE7 | Etapa 5 + 6: imóveis + dashboard | ⬜ Não iniciada | — | Painel expandido, 2 abas |
| FE8 | Relatório + auth + planos | ⬜ Não iniciada | — | Download PDF, upgrade CTA |

> **Regra de milestone:** a fase só é marcada como concluída após confirmação explícita do responsável. Não marcar na ausência de confirmação.

---

## 3. Arquitetura do Sistema

### Diagrama de alto nível

```
┌─────────────────────────────────────────────────────────────────┐
│  VERCEL (CDN global, gratuito)                                  │
│  Next.js App Router                                             │
│  MapLibre GL JS + MapTiler tiles                                │
│  TanStack Query + Zustand + shadcn/ui                           │
│  SSE client / REST commands                                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────────────┐
│  HOSTINGER — topologia inicial: 1× VPS KVM 4                    │
│                                                                 │
│  Reverse proxy + TLS                                            │
│  api (FastAPI + Uvicorn)                                        │
│  worker-general (Dramatiq)                                      │
│  worker-scheduler                                               │
│  PostgreSQL 16 + PostGIS                                        │
│  Redis                                                          │
│  Valhalla                                                       │
│  OTP 2                                                          │
│  OSM/GTFS importados localmente                                 │
│  worker-scrape-browser (Dramatiq + Playwright, conc. 1)         │
│                                                                 │
│  Escalação: 2º VPS na Hostinger apenas por contenção medida     │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                  ┌───────────▼──────────┐
                  │  Object Storage      │
                  │  R2 / S3             │
                  │  relatórios PDF      │
                  │  artefatos exportados│
                  └──────────────────────┘
```

### Estrutura do monorepo

```
find-ideal-estate/
  apps/
    web/          ← Next.js App Router
    api/          ← FastAPI monólito
  packages/
    contracts/    ← DTOs compartilhados (nunca modelos internos)
    design-system/
  infra/
    docker/
    migrations/   ← Alembic
    seeds/
  docs/
```

### Estrutura do backend (`apps/api`)

```
apps/api/src/
  core/
    config.py · logging.py · security.py
    db.py · redis.py · sse.py · errors.py
  modules/
    auth/         journeys/     jobs/
    transport/    zones/        urban_analysis/
    pois/         listings/     deduplication/
    reports/      usage_limits/ datasets/
  adapters/
    mapbox/       otp/          osm/
    scraping/     legacy_scripts/
  workers/
    queue.py
    handlers/
  api/
    routes/
    schemas/
```

### Estrutura do frontend (`apps/web`)

```
apps/web/src/
  app/
  features/
    map/              search/      transport-selection/
    zones/            listings/    reports/
    dashboard/
  components/
    shell/     panel/    map-controls/
    cards/     charts/   feedback/
  state/
    ui-store.ts      ← Zustand: painel, abas, hover, popups
    journey-store.ts ← Zustand: parâmetros, seleções, etapas stale
    map-store.ts     ← Zustand: layers, viewport
  lib/
    api/  sse/  formatters/  validators/
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

### Topologia

| Serviço | Plataforma | Custo estimado | Observações |
|---|---|---|---|
| Frontend Next.js | Vercel (free) | R$ 0 | CDN global, preview por branch |
| Backend completo inicial (`api`, `worker-general`, `worker-scheduler`, PostgreSQL/PostGIS, Redis, Valhalla, OTP, Playwright) | Hostinger VPS KVM 4 | R$ 59,99/mês promocional · R$ 149,99/mês renovação | Topologia inicial canônica |
| Object Storage (relatórios) | R2 / S3 | ~R$ 0–10/mês | Depende do volume de PDFs |
| **Total estimado inicial** | | **~R$ 60–70/mês promocional** · **~R$ 150–170/mês renovação** | Sem Bright Data, sem 2º VPS |

### Escalação prevista na própria Hostinger

| Situação | Topologia | Critério de entrada |
|---|---|---|
| Inicial | **1× VPS KVM 4** | Sem usuários ou baixa concorrência |
| Escala 1 | **2 VPS**: APP/DATA + GEO/SCRAPE | Contenção medida entre API/DB e Playwright/Valhalla/OTP |
| Escala 2 | **2 VPS + ajuste de plano** | `queue_depth(scrape_browser)` sustentado alto ou saturação de CPU/RAM |

### Processos

| Processo | Localização | Filas consumidas |
|---|---|---|
| `api` | Hostinger VPS KVM 4 (topologia inicial) | — (recebe HTTP + SSE) |
| `worker-general` | Hostinger VPS KVM 4 (topologia inicial) | transport, zones, enrichment, dedup, reports, prewarm |
| `worker-scheduler` | Hostinger VPS KVM 4 (topologia inicial) | agenda jobs noturnos e watchdog |
| `worker-scrape-browser` | Hostinger VPS KVM 4 (topologia inicial) | scrape_browser (conc. 1) |
| `worker-scrape-browser` | Hostinger VPS GEO/SCRAPE (quando escalado) | scrape_browser / scrape_http |

### Variáveis de ambiente obrigatórias

```
DATABASE_URL
REDIS_URL
MAPBOX_ACCESS_TOKEN     ← apenas backend, nunca frontend
MAPTILER_API_KEY        ← apenas frontend via Next.js env
VALHALLA_URL            ← URL interna Hostinger VPS
OTP_URL                 ← URL interna Hostinger VPS
R2_BUCKET / S3_BUCKET
RESEND_API_KEY          ← Fase 8
STRIPE_SECRET_KEY       ← Fase 8
STRIPE_WEBHOOK_SECRET   ← Fase 8
```

### Escalação do VPS

Separar `worker-scrape-browser` em VPS próprio somente quando `p95` de isócrona walking
subir acima de 500ms no horário de prewarm (03:00–05:30).
Monitorar via métrica `valhalla_isochrone_p95_ms`.

### Bright Data

Escape hatch manual, nunca base da arquitetura.

- **Habilitar** para uma plataforma quando, na janela de 24h: `success_rate < 85%`
  OU `empty_result_rate > 20%` em zonas com histórico não vazio.
- **Desabilitar** após 72h consecutivas com `success_rate >= 95%`
  e `empty_result_rate <= 10%`.

---

## 5. Modelo de Dados

### Diagrama de relações

```
users ─────────────────────────────────────────────────┐
  │                                                     │
  └─ journeys ───────────────────────────────────┐      │
       │                                          │      │
       └─ jobs ────────── job_events              │      │
                                                  │      │
transport_points ──────────────────────────────── │──┐   │
                                                  │  │   │
zones ─────────────────────────────────────────── ┘  │   │
  │                                                   │   │
  ├─ zone_listing_caches ── properties ── listing_ads─┘───┘
  │                              │
  │                         listing_snapshots
  │
  ├─ listing_search_requests
  └─ dataset_versions

plans ── user_subscriptions ── users
      └─ usage_quotas

external_usage_ledger
scraping_degradation_events
webhook_events
```

### `users`

```sql
users (
  id            UUID PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  is_active     BOOLEAN DEFAULT true,
  is_superuser  BOOLEAN DEFAULT false,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
)
```

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

### `plans`

```sql
plans (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug             TEXT UNIQUE NOT NULL,  -- 'free' | 'pro'
  name             TEXT NOT NULL,
  price_brl        NUMERIC(8,2),
  price_annual_brl NUMERIC(8,2),
  features         JSONB,
  created_at       TIMESTAMPTZ DEFAULT NOW()
)
```

### `user_subscriptions`

```sql
user_subscriptions (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                UUID REFERENCES users(id),
  plan_id                UUID REFERENCES plans(id),
  stripe_subscription_id TEXT,
  status                 TEXT NOT NULL,  -- 'active' | 'past_due' | 'cancelled'
  current_period_start   TIMESTAMPTZ,
  current_period_end     TIMESTAMPTZ,
  created_at             TIMESTAMPTZ DEFAULT NOW(),
  updated_at             TIMESTAMPTZ DEFAULT NOW()
)
```

### `usage_quotas`

```sql
usage_quotas (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID REFERENCES users(id),
  plan_id        UUID REFERENCES plans(id),
  period_start   TIMESTAMPTZ,
  period_end     TIMESTAMPTZ,
  zone_analyses  INT DEFAULT 0,
  reports_gen    INT DEFAULT 0,
  updated_at     TIMESTAMPTZ DEFAULT NOW()
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
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider     TEXT NOT NULL,   -- 'stripe' | 'mobility_db'
  event_type   TEXT NOT NULL,
  payload      JSONB,
  processed    BOOLEAN DEFAULT false,
  processed_at TIMESTAMPTZ,
  error        TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW()
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

### Controle de plano antes do scraping

```python
async def get_effective_plan(user: User | None, session_id: str | None) -> PlanSlug:
    if user and user.has_active_subscription():
        return PlanSlug.PRO
    return PlanSlug.FREE   # anônimo e free: mesmo tratamento

async def request_listings(journey_id, zone_id, user, session_id, config):
    plan  = await plans.get_effective_plan(user=user, session_id=session_id)
    cache = await zone_listing_caches.get(zone_id, config)

    await listing_search_requests.record(
        journey_id=journey_id,
        user_id=user.id if user else None,
        session_id=session_id,
        zone_fingerprint=config.zone_fingerprint,
        search_location_normalized=config.search_location_normalized,
        search_location_label=config.search_location_label,
        search_location_type=config.search_location_type,
        search_type=config.search_type,
        usage_type=config.usage_type,
        platforms_hash=config.platforms_hash,
        result_source=(
            "cache_hit" if cache and cache.is_usable() else "cache_miss"
        ),
    )

    if plan.slug == PlanSlug.FREE:
        if cache and cache.is_usable():
            return ListingsRequestResult(source="cache", ...)
        return ListingsRequestResult(
            source="none",
            freshness_status="queued_for_next_prewarm",
            upgrade_reason="fresh_listings",
            next_refresh_window="03:00–05:30",
        )

    # PRO: dispara Playwright imediatamente
    job = await jobs.enqueue_scraping(
        zone_id=zone_id, config=config, priority=Priority.USER_REQUEST
    )
    return ListingsRequestResult(source="scraping", job_id=job.id, ...)
```

### Prewarm noturno

```python
# APScheduler
scheduler.add_job(
    prewarm_requested_search_locations_24h,
    trigger="cron",
    hour=3,
    kwargs={"lookback_hours": 24, "limit": 100},
)
```

- O conjunto-alvo do prewarm é composto **somente** pelos endereços/search locations pesquisados na Etapa 5 nas últimas 24 horas.
- Ordenação de prioridade: `COUNT(*) DESC`, `MAX(requested_at) DESC` e, em empate, cache mais antigo primeiro.
- Não existe fallback por zona popular, geohash, região, hot list manual ou cold start artificial.
- **Alerta crítico:** prewarm não iniciou em 30 min do horário, ou < 60% dos endereços-alvo processados com sucesso.

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
- Raio da zona (metros)
- Modal: Transporte público | A pé | Carro (PRO — lock + CTA gratuito)
- Tempo máximo (minutos)
- Distância máxima até seed de transporte
- Checkboxes de análise: verde, alagamento, segurança, POIs
- Botão "Achar pontos de transporte"

**Mapa:** cursor vira pin somente sobre o mapa ao entrar em modo de seleção.

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
Plataformas FREE: QuintoAndar + Zap. PRO: + VivaReal (lock + CTA no FREE).
Resultado preliminar com badge de frescor; diff incremental ao revalidar.

**Aba Dashboard da zona:**
Preço médio atual e histórico (Recharts LineChart, max 365 pontos, `dot={false}` acima de 90).
Distribuição por faixa (Recharts BarChart).
Segurança, área verde, área alagável, contagem de POIs, resumo transporte.

**Mapa (ao clicar "ver acessibilidade"):** melhor rota a pé até cada categoria de POI
e até o transporte. Alternância entre categorias sem recarregar.

### Gerenciamento de estado

| Store | Biblioteca | Conteúdo |
|---|---|---|
| `ui-store` | Zustand | painel, aba ativa, layer menu, popups, hover |
| `journey-store` | Zustand | ponto principal, seleções, parâmetros, etapas stale |
| `map-store` | Zustand | layers visíveis, viewport, instância mapa |
| Server state | TanStack Query | zonas, imóveis, métricas, progresso de jobs |
| SSE bridge | custom hook | invalida queries TanStack ao receber eventos SSE |

### Regras de performance do mapa

- Mapa vive em componente próprio com refs estáveis — mudanças no painel não recriam instância.
- GeoJSON apenas para seleção ativa e subconjuntos < 500 features.
- POIs carregados sob demanda via Mapbox Search Box API por bounding box + categoria; nunca tudo de uma vez.
- Vector tiles / PMTiles para camadas base pesadas.
- Overlays analíticos server-driven.

---

## 10. Autenticação e Modelo de Acesso

### Biblioteca

**`fastapi-users`** — integrado na Fase 8.

- Magic link por email (primário): zero senha, zero fricção.
- OAuth Google: configurável após magic link, sem reescrita.
- Integração SQLAlchemy 2 nativa.
- Cookie HTTP-only com rotação automática de sessão.

### Provedor de email

**Resend** (`resend.com`) — 3.000 emails/mês gratuitos. SDK Python oficial.

```python
RESEND_API_KEY: str
EMAIL_FROM: str = "noreply@find-ideal-estate.com.br"
```

### Fluxo anônimo → autenticado

O usuário acessa sem cadastro. Jornada associa-se a `anonymous_session_id` (cookie).
Autenticação exigida apenas em momentos de alto valor:
- Download do relatório PDF.
- Salvar jornada.
- Acessar histórico.

No cadastro, jornada anônima migrada atomicamente:

```sql
BEGIN;
UPDATE journeys
   SET user_id = :new_user_id, anonymous_session_id = NULL
 WHERE anonymous_session_id = :session_id AND user_id IS NULL;
COMMIT;
```

**TTL de sessão anônima:** 7 dias de inatividade.
Jornadas com relatório gerado: 30 dias.

### Mapa de dependência de auth por fase

| Feature | Fase | Depende de auth? |
|---|---|---|
| Análise de transporte e zonas | 4 | Não |
| Cache de imóveis (FREE) | 6 | Não |
| Badge de frescor | 6 | Não |
| Download do relatório PDF | 7 | Sim (CTA de cadastro) |
| Histórico de análises | 7 | Sim |
| Scraping fresh (PRO) | 8 | Sim |
| Plano Pro / Stripe | 8 | Sim |
| Quotas por plano | 8 | Sim |

**Fases 6–7 sem auth completa:** `get_effective_plan()` retorna `FREE` para todas as sessões.
A distinção FREE/PRO real só é ativada na Fase 8.

---

## 11. Monetização

### Planos

| Funcionalidade | Gratuito | Pro (R$29/mês ou R$249/ano) |
|---|---|---|
| Análises de zona | 2/mês | Ilimitado |
| Modal de isócrona | Transporte público + a pé | + Carro |
| Imóveis | Cache pré-aquecido (12h) | Scraping fresco sob demanda |
| Tempo até ver imóveis | Imediato | 30–90s |
| Relatório PDF | 2/mês (exige cadastro) | Ilimitado |
| Histórico de análises | Não | Sim |
| Plataformas disponíveis | QuintoAndar + Zap | + VivaReal |
| Dashboard histórico | 30 dias | 90 dias |

**Relatório avulso:** R$9,90 por relatório (usuário gratuito).
Três avulsos equivalem ao plano mensal — argumento natural de upgrade.

### CTAs contextualizadas

- VivaReal no FREE: `"Adicione VivaReal à sua busca — plano Pro por R$ 29/mês"`
- Isócrona de carro: `"Analise deslocamento de carro — plano Pro por R$ 29/mês"`
- Terceiro relatório: `"Baixe por R$ 9,90 ou acesse ilimitados no plano Pro"`
- Endereço sem cache (FREE): UI mostra opção de upgrade no momento de maior frustração
  (maior conversão).

### Stripe — webhooks obrigatórios

| Evento | Ação |
|---|---|
| `checkout.session.completed` | Criar `user_subscriptions` com `status = active` |
| `invoice.payment_succeeded` | Renovar `current_period_end` |
| `invoice.payment_failed` | Marcar `past_due`, enviar email de aviso |
| `customer.subscription.updated` | Sincronizar upgrade/downgrade |
| `customer.subscription.deleted` | Marcar `cancelled`, rebaixar para FREE |
| `charge.refunded` | Registrar no ledger |

---

## 12. Roadmap por Fase (0–8)

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

#### M3.1 — Migração frontend Vite → Next.js App Router ✅
- [x] Novo `apps/web/` com Next.js 14+ App Router
- [x] MapLibre GL JS integrado; `MapShell` com `preserveDrawingBuffer: true`
- [x] MapTiler como único provedor de tiles (chave via `NEXT_PUBLIC_MAPTILER_API_KEY`)
- [x] Etapa 1 portada: formulário de configuração funcionando
- [x] `next build` sem erros; `next start` responsivo

**Verificação:** `next build` verde; formulário de Etapa 1 salva jornada via `POST /journeys`.

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

#### M3.6 — Job `TRANSPORT_SEARCH` real ⬜
- [ ] `ST_DWithin` sobre `gtfs_stops` + `geosampa_metro_stations` + `geosampa_trem_stations`
- [ ] Filtro por `modal` selecionado na jornada
- [ ] Ranking: distância a pé asc; desempate por qtd de rotas desc
- [ ] Persiste lista em `transport_points`; emite `job.completed` via SSE
- [ ] `GET /journeys/{id}/transport-points` retorna lista enriquecida

**Verificação:** ponto em SP (lat -23.55, lon -46.63), raio 300m → lista de paradas/estações com `walk_distance_m` ± 10% do real.

#### M3.7 — Proxy de geocoding ⬜
- [ ] `POST /api/geocode` → chama Mapbox Search Box API
- [ ] Cache Redis 24h por string normalizada
- [ ] Rate limit: 30 req/min por sessão via `external_usage_ledger`
- [ ] Debounce da request quando chamada em < 300ms da anterior (retorna cached)
- [ ] Não expõe token Mapbox ao frontend

**Verificação:** `POST /api/geocode {"q": "Av Paulista"}` retorna list de sugestões;
segunda chamada idêntica tem `cache_hit=true` em `external_usage_ledger`.

#### M3.8 — Frontend Etapa 2: seleção de transporte ⬜
- [ ] Lista de pontos de transporte com distância a pé, tipo, qtd de linhas
- [ ] Hover na lista acende ponto correspondente no mapa
- [ ] Círculo de alcance desenhado ao abrir a etapa
- [ ] Botão "Gerar zonas" enfileira job e avança para Etapa 3

**Verificação:** hover em item da lista → marcador no mapa pisca; clique "Gerar zonas" → `POST /jobs` com tipo `ZONE_GENERATION`.

---

### Fase 4 — Zonas: isócronas + enriquecimento + DI ⬜

**Objetivo:** geração e enriquecimento de zonas com badges incrementais, incluindo POIs obtidos sob demanda via Mapbox.
**Esforço estimado:** 8–10 dias · **Status:** ⬜ Não iniciada
**Dependências bloqueantes:** M3.4, M3.6. Dados GeoSampa importados e ambiente geoespacial local (Valhalla/OTP) operacional.

#### M4.1 — dependency-injector ⬜
- [ ] Container principal em `apps/api/src/core/container.py`
- [ ] Providers: `ValhallAdapter`, `OTPAdapter`, `TransportService`, `ZoneService`
- [ ] Integrado ao FastAPI `lifespan` (não via decoradores globais)
- [ ] Módulos de Fase 0–3 migrados ao container sem alterar comportamento

**Verificação:** `GET /health` com DI ativo → mesmos resultados; testes unitários passam com providers mockados.

#### M4.2 — Fingerprint e reaproveitamento de zona ⬜
- [ ] `compute_zone_fingerprint(lat, lon, modal, max_time, radius, dataset_version)` → SHA-256
- [ ] lat/lon arredondados a 5 casas decimais antes do hash
- [ ] `zones.fingerprint` com constraint UNIQUE
- [ ] Antes de chamar Valhalla: checagem por fingerprint existente no banco
- [ ] Zona reutilizada emite `zone.reused` em vez de `zone.generated`

**Verificação:** duas jornadas com mesmos parâmetros → `SELECT count(*) FROM zones WHERE fingerprint = :fp` = 1.

#### M4.3 — Job `ZONE_GENERATION` ⬜
- [ ] Chamada Valhalla `/isochrone` para cada ponto de transporte selecionado
- [ ] Persiste polígono em `zones.isochrone_geom` (PostGIS POLYGON 4326)
- [ ] Emite `job.partial_result.ready` ao concluir cada zona (não aguarda todas)
- [ ] Estado de zona: `pending → generating → enriching → complete | failed`
- [ ] Zonas aparecem progressivamente no mapa via SSE

**Verificação:** selecionando 3 pontos de transporte → 3 polígonos chegam via SSE em sequência, não todos de uma vez.

#### M4.4 — 4 subjobs de enriquecimento paralelos ⬜
- [ ] `ZONE_ENRICHMENT` dispara 4 subjobs por zona (fila `enrichment`, conc. 4):
  - `EnrichGreen`: `ST_Area(ST_Intersection(zone, vegetacao))` → `green_area_m2`
  - `EnrichFlood`: `ST_Area(ST_Intersection(zone, mancha_inundacao))` → `flood_area_m2`
  - `EnrichSafety`: `COUNT(incidents WHERE ST_Within(incident, zone))` → `safety_incidents_count`
  - `EnrichPOIs`: consulta Mapbox Search Box API por categoria usando o centroid/bbox da zona; normaliza o retorno e agrega `poi_counts` por categoria
- [ ] `EnrichPOIs` usa cache efêmero por `zone_fingerprint + category_set + radius/bbox` antes de chamar a Mapbox
- [ ] Todos os 4 subjobs iniciam simultaneamente por zona

**Verificação:** `EXPLAIN ANALYZE` dos 4 queries rodam em paralelo; tempo total da zona < soma individual.

#### M4.5 — Badges incrementais ⬜
- [ ] `compute_badge(value, peer_median, threshold)` → `ZoneBadgeValue`
- [ ] Badge calculado com mediana parcial após cada zona concluir enriquecimento
- [ ] SSE `zone.badges.updated` com `{"provisional": true, "based_on": "X/Y zonas"}`
- [ ] Quando todas as zonas concluem: recalcula com mediana real → SSE `zones.badges.finalized`
- [ ] `zones.badges_provisional = false` após finalização

**Verificação:** com 3 zonas enriquecendo: 1ª a concluir emite badge provisional;
após 3ª: `zones.badges.finalized` emitido exatamente uma vez.

#### M4.6 — Frontend Etapas 3 e 4 ⬜
- [ ] **Etapa 3:** barra de progresso real (% do SSE), etapa corrente, botão cancelar ativo
- [ ] Zonas aparecem no mapa progressivamente ao receber `job.partial_result.ready`
- [ ] Rótulos numéricos nos polígonos (order por `travel_time_minutes`)
- [ ] **Etapa 4:** lista ordenada por `travel_time_minutes` asc
- [ ] Badges exibidos com indicador provisional/finalizado
- [ ] Filtros: modal, tempo máximo, badge mínimo
- [ ] CTA "Buscar imóveis" visível na zona selecionada

**Verificação:** cancelar durante Etapa 3 → spinner para; dados parciais persistem na lista.

---

### Fase 5 — Imóveis: scrapers + deduplicação + cache ⬜

**Objetivo:** scrapers Playwright integrados ao sistema de filas com cache geoespacial.
**Esforço estimado:** 10–12 dias · **Status:** ⬜ Não iniciada
**Dependências bloqueantes:** M4.3. `worker-scrape-browser` rodando em Hostinger VPS.

#### M5.1 — Tabelas e máquina de estados ⬜
- [ ] Migrations: `properties`, `listing_ads`, `listing_snapshots`, `zone_listing_caches`
- [ ] `ZoneCacheStatus` implementado como máquina de estados explícita:
  `pending → scraping → partial → complete | failed | cancelled_partial`
- [ ] Toda transição de estado passa por método único `transition_to(new_state)` com validação

**Verificação:** tentar `transition_to(complete)` a partir de `pending` → `InvalidStateTransition`.

#### M5.2 — Lock de scraping ⬜
- [ ] Lock Redis: `SET scraping_lock:{fingerprint}:{config_hash} 1 EX 300 NX`
- [ ] Worker tenta adquirir lock antes de iniciar scraping; se falhar → aguarda + reabre cache
- [ ] Lock liberado explicitamente em `finally` (evita esperar TTL em sucesso)
- [ ] Teste: duas goroutines tentam lock para mesma zona → somente uma scrape

**Verificação:** teste de lock concorrente passa sem escrita duplicada no banco.

#### M5.3 — Adaptadores Playwright ⬜
- [ ] `QuintoAndarScraper` migrado do script legado para handler Dramatiq
- [ ] `ZapImoveisScraper` migrado
- [ ] `VivaRealScraper` migrado
- [ ] Cada scraper: user-agent realista, delays entre ações, `robots.txt` verificado
- [ ] `scraping_degradation_events` criado quando `success_rate < 85%` em 24h

**Verificação:** scraper de QA retorna ≥ 5 imóveis para zona de teste em SP sem erro 4xx/5xx.

#### M5.4 — Stale-while-revalidate e hit parcial ⬜
- [ ] Hit total: cache `complete` + dentro do TTL → retorna imediatamente
- [ ] Hit parcial: cache por interseção de polígonos (`ST_Within`) com outra zona de geometria similar
- [ ] Miss total: enfileira job de scraping
- [ ] `PreliminaryResultThresholds` aplicados antes de sinalizar `listings.preliminary.ready`

**Verificação:** buscar imóveis em zona A → criar zona B que cobre 70% de A → resultado parcial de A serve para B.

#### M5.5 — Deduplicação ⬜
- [ ] `compute_property_fingerprint(address_normalized, lat, lon, area_m2, bedrooms)` → SHA-256
- [ ] Mesmo imóvel em 2 plataformas → 1 `property`, 2 `listing_ads`
- [ ] `current_best_price` calculado como `MIN(price)` entre listing_ads ativos
- [ ] `second_best_price` = segundo menor preço ativo (mostra economia multi-plataforma)
- [ ] Badge de duplicidade: `"Disponível em 2 plataformas · menor: R$ X"`

**Verificação:** inserir mesmo imóvel via 2 plataformas → `SELECT count(*) FROM properties WHERE fingerprint = :fp` = 1.

#### M5.6 — `listing_search_requests` ⬜
- [ ] Registrar somente buscas confirmadas pelo clique em "Buscar imóveis" na Etapa 5, inclusive cache hit, cache miss e scraping fresh
- [ ] Persistir `zone_fingerprint`, `search_location_normalized`, `search_type`, `usage_type`, `platforms_hash` e `requested_at`
- [ ] Busca de usuário FREE sem cache também entra na fila lógica de demanda para o prewarm seguinte
- [ ] Query base da Fase 7: agregação das buscas das últimas 24h por endereço/search location

**Verificação:** 3 buscas para o mesmo endereço em 24h → agregação retorna `demand_count = 3`.

#### M5.7 — Frontend Etapas 5 e início de 6 ⬜
- [ ] **Etapa 5:** combobox autocomplete filtrado por `ST_Contains(zone, address_point)`
- [ ] Bairros > logradouros > referências na ordenação do autocomplete
- [ ] "Buscar imóveis" habilitado somente após endereço selecionado
- [ ] **Etapa 6 inicial:** listagem de imóveis com cache (badge de frescor: `"Dados de Xh atrás"`)
- [ ] Diff incremental: novos/removidos ao revalidar sem recarregar lista inteira
- [ ] Cards: foto, preço, metragem, plataforma, badge de duplicidade, link externo

**Verificação:** imóvel aparece em < 500ms (cache hit); diff ao revalidar não pisca a lista.

---

### Fase 6 — Dashboard + relatório PDF ⬜

**Objetivo:** análise urbana completa e geração de PDF para compartilhamento.
**Esforço estimado:** 7–8 dias · **Status:** ⬜ Não iniciada
**Dependências bloqueantes:** M4.5, M5.5.

#### M6.1 — Rollups de preço ⬜
- [ ] `property_price_rollups` calculados periodicamente (diário ou por trigger de ingestão)
- [ ] Campos: `date`, `zone_fingerprint`, `search_type`, `median_price`, `p25_price`, `p75_price`, `sample_count`
- [ ] Retenção: 365 dias de histórico

**Verificação:** após ingestão de 20 imóveis → rollup calculado; mediana dentro do IQR esperado.

#### M6.2 — Dashboard da zona ⬜
- [ ] **Aba Dashboard** no frontend (Etapa 6, segunda aba):
  - Preço mediano atual + variação (↑↓) vs. mês anterior
  - LineChart: histórico de 30 dias (FREE) / 90 dias (PRO) com `dot={false}` acima de 90 pontos
  - BarChart: distribuição por faixas de aluguel/compra (10 faixas)
  - Segurança: contagem de ocorrências + badge
  - Área verde: m² + badge
  - Risco de alagamento: % da área + badge
  - POIs: contagem por categoria (top 6 categorias)
  - Transporte: tempo médio ao ponto-semente + linhas disponíveis

**Verificação:** Dashboard carrega com dados reais para zona de teste; LineChart mostra exatamente 30 pontos para sessão FREE.

#### M6.3 — Job `REPORT_GENERATE` ⬜
- [ ] Template Jinja2 HTML com seções: cabeçalho da jornada, mapa (imagem base64), lista de zonas comparativa, detalhes dos imóveis, dashboard
- [ ] WeasyPrint: HTML → PDF
- [ ] Upload para R2/S3; signed URL com TTL de 7 dias
- [ ] `GET /reports/{id}/url` regenera signed URL sem re-gerar o PDF
- [ ] `report.ready` SSE com `{url, expires_at}`

**Verificação:** PDF gerado em < 20s para jornada com 5 zonas e 20 imóveis; tamanho < 5MB.

#### M6.4 — Captura do mapa no frontend ⬜
- [ ] `MapShell` inicializado com `preserveDrawingBuffer: true`
- [ ] `map.getCanvas().toDataURL('image/png')` chamado antes de `POST /reports`
- [ ] Imagem incluída no payload (base64); endpoint valida presença da imagem
- [ ] Fallback: se canvas vazio (todo transparente) → erro descritivo para o usuário

**Verificação:** relatório gerado com imagem de mapa não-transparente.

#### M6.5 — Quotas e CTA de cadastro ⬜
- [ ] Sessão anônima: 2 relatórios/mês via `usage_quotas` por IP/session
- [ ] Ao atingir limite: modal `"Crie uma conta gratuita para baixar mais relatórios"`
- [ ] `get_effective_plan()` retorna FREE para todas as sessões (auth real somente na Fase 8)
- [ ] Quota por sessão: contagem via Redis (KEY `quota:report:{session_id}:{month}`, TTL 31 dias)

**Verificação:** 3ª geração de relatório por mesma sessão → 403 com `upgrade_reason = "report_quota_exceeded"`.

#### M6.6 — Mapa de acessibilidade de imóvel ⬜
- [ ] "Ver acessibilidade" em card de imóvel → mapa mostra rota a pé até ponto de transporte
- [ ] Rotas para categorias de POI: escola, supermercado, farmácia, parque (top 4)
- [ ] Alternância entre categorias sem recarregar (Zustand: categoria ativa → layer toggle)
- [ ] Distância e tempo estimado exibidos no painel

**Verificação:** clicar "Ver acessibilidade" → 5 rotas aparecem no mapa sem piscar.

---

### Fase 7 — Scheduler noturno (prewarm) ⬜

**Objetivo:** usuários gratuitos recebem dados de imóveis apenas para os endereços/search locations realmente pesquisados na Etapa 5 nas últimas 24 horas.
**Esforço estimado:** 4–5 dias · **Status:** ⬜ Não iniciada
**Dependências bloqueantes:** M5.6, M6.5.

#### M7.1 — APScheduler integrado ⬜
- [ ] APScheduler em `worker-scheduler` dedicado
- [ ] Jobs não bloqueiam API nem `worker-general`
- [ ] Um cron registrado:
  - `03:00`: `prewarm_requested_search_locations_24h(lookback_hours=24, limit=100)`
- [ ] Logs de início/fim de cada run com `prewarm_last_run_status`

**Verificação:** scheduler inicia com o stack e o cron de 03:00 é registrado corretamente.

#### M7.2 — `prewarm_requested_search_locations_24h` ⬜
- [ ] Query agrega `listing_search_requests` com `requested_at >= now() - interval '24 hours'`
- [ ] Ordenação: `COUNT(*) DESC`, `MAX(requested_at) DESC`, `cache_age DESC`
- [ ] Limite inicial de 100 endereços/search locations por run
- [ ] Cada item enfileira `LISTINGS_PREWARM` com `Priority.PREWARM = 5`
- [ ] Job de prewarm cede imediatamente a qualquer `USER_REQUEST`
- [ ] `last_prewarmed_at` do cache correspondente é atualizado ao concluir

**Verificação:** endereço mais buscado nas últimas 24h tem cache renovado após o run do prewarm.

#### M7.3 — Sem fallback e sem cold start artificial ⬜
- [ ] Nenhuma query por zonas populares, geohash, região ou listas manuais
- [ ] Se nenhum endereço foi pesquisado nas últimas 24h, o scheduler não enfileira scraping
- [ ] FREE sem cache recebe UI de fila para o próximo prewarm; não há scraping imediato

**Verificação:** base zerada + nenhuma busca em 24h → prewarm executa sem itens e finaliza como `success_empty`.

#### M7.4 — Métricas e alertas de prewarm ⬜
- [ ] Métrica `prewarm_coverage_rate`: `enderecos_processados / enderecos_enfileirados`
- [ ] Métrica `prewarm_target_count_24h`: quantidade de endereços distintos elegíveis no período
- [ ] `prewarm_last_run_status`: `success | success_empty | partial | failed`
- [ ] **Alerta crítico 1:** prewarm não inicia em 30 min → `prewarm_start_overdue`
- [ ] **Alerta crítico 2:** `prewarm_coverage_rate < 0.60` ao fim do run quando `prewarm_target_count_24h > 0`

**Verificação:** matar `worker-scrape-browser` durante o prewarm → alerta gerado em < 35 min.

#### M7.5 — UI para endereço sem cache (FREE) ⬜
- [ ] FREE sem cache disponível → banner: `"Este endereço entrou na fila de atualização noturna."`
- [ ] Linha secundária: `"Se houver anúncios disponíveis, eles aparecerão após a próxima atualização."`
- [ ] CTA contextual: `"Veja agora com o plano Pro — scraping sob demanda"`
- [ ] Endereço com cache fresco exibe badge explícito: `"Dados de 10h atrás"`

**Verificação:** endereço pesquisado hoje sem cache mostra banner correto; após o prewarm seguinte, o banner some e a lista é servida do cache.

---

### Fase 8 — Auth + planos + Stripe ⬜

**Objetivo:** produto monetizável com distinção FREE/PRO real e pagamento integrado.
**Esforço estimado:** 10–12 dias · **Status:** ⬜ Não iniciada
**Dependências bloqueantes:** M6.5, M7.4.

#### M8.1 — fastapi-users: magic link ⬜
- [ ] `fastapi-users` integrado com `SQLAlchemy 2` backend
- [ ] `UserManager.on_after_request_verify` → envia email via Resend
- [ ] Token: 32 bytes `secrets.token_urlsafe()`, expira em 15 min, single-use
- [ ] Comparação timing-safe: `hmac.compare_digest()`
- [ ] Cookie HTTP-only com rotação automática de sessão a cada login

**Verificação:** `POST /auth/request-magic-link` → email entregue em < 30s; clicar link → cookie de sessão; segunda vez → token inválido.

#### M8.2 — Migração de jornada anônima ⬜
- [ ] Hook `on_after_login`: verifica `anonymous_session_id` no cookie
- [ ] Transação atômica: `UPDATE journeys SET user_id = :uid WHERE anonymous_session_id = :sid AND user_id IS NULL`
- [ ] Cookie anônimo limpo após migração
- [ ] Jornadas do usuário antes do cadastro ficam acessíveis no histórico

**Verificação:** completar 2 etapas anonimamente → fazer cadastro → histórico mostra ambas as jornadas.

#### M8.3 — Tabelas de planos e quotas ⬜
- [ ] Seed: `plans` com `slug = 'free'` e `slug = 'pro'`
- [ ] `user_subscriptions` e `usage_quotas` migrados
- [ ] `get_effective_plan(user)` real: consulta `user_subscriptions` + `status = active`
- [ ] `UsageQuotaService.check_and_consume(user, operation)` → `QuotaExceededError` se esgotado
- [ ] Limites FREE: 2 análises de zona/mês, 2 relatórios/mês

**Verificação:** usuário sem subscrição → `get_effective_plan()` = FREE; 3ª análise → `QuotaExceededError`.

#### M8.4 — Features desbloqueadas para PRO ⬜
- [ ] **Isócrona de carro:** `car` modal habilitado para PRO; lock + CTA para FREE
- [ ] **VivaReal:** `VivaRealScraper` enfileirado somente quando `plan = PRO`
- [ ] **Scraping fresco:** `request_listings()` com lógica real FREE vs PRO
- [ ] **Dashboard histórico:** 30 dias FREE → 90 dias PRO
- [ ] **Histórico de análises:** `GET /journeys?user_id={id}` para autenticados

**Verificação:** usuário PRO → campo `car` habilitado no formulário; mesmo endpoint retorna 90 dias de dados.

#### M8.5 — Integração Stripe ⬜
- [ ] `POST /billing/checkout` → Stripe Checkout Session; retorna `{checkout_url}`
- [ ] `POST /webhooks/stripe` com `stripe.Webhook.construct_event()` obrigatório
- [ ] 6 eventos mapeados (ver seção 11): `checkout.session.completed`, `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`, `charge.refunded`
- [ ] Idempotência: `webhook_events.stripe_event_id` UNIQUE; duplicado ignorado silenciosamente
- [ ] PRO ativado em < 5s após `checkout.session.completed`

**Verificação:** teste com Stripe CLI `stripe trigger checkout.session.completed` → `user_subscriptions.status = active`; mesmo evento duas vezes → sem duplicação.

#### M8.6 — Dashboard do usuário ⬜
- [ ] Página `/account`: plano atual, uso do mês (análises + relatórios), data de renovação
- [ ] Botão "Fazer upgrade" redireciona para checkout Stripe
- [ ] Downgrade para FREE: funcionalidades PRO ficam travadas imediatamente
- [ ] `GET /account/usage` retorna `{plan, zone_analyses_used, reports_used, period_end}`

**Verificação:** usuário PRO cancela no Stripe → webhook recebido → `GET /account/usage` mostra plano FREE.

#### M8.7 — Testes E2E de auth e pagamento ⬜
- [ ] Playwright: fluxo completo `signup → magic link → login → checkout (Stripe test) → uso PRO`
- [ ] Cenário de downgrade: cancelar → funcionalidades PRO bloqueadas
- [ ] Smoke Dataset A executado com usuário autenticado FREE e PRO

**Verificação:** testes E2E passam em staging sem intervenção manual.

---

## 13. Segurança

### Token Mapbox

- `MAPBOX_ACCESS_TOKEN` exclusivamente no backend, nunca exposto ao cliente.
- Geocoding via `POST /api/geocode` (proxy server-side).
- POIs via módulo backend dedicado (`pois`) chamando Search Box Category Search.
- Rate limit e orçamento por operação registrados em `external_usage_ledger`.

### Rate limiting (Redis-based)

| Camada | Limite FREE | Limite anônimo |
|---|---|---|
| Geocoding | 100 req/hora | 50 req/hora |
| POIs (Search Box Category Search) | 60 req/hora | 30 req/hora |
| Criação de jornada | 10/dia | 5/dia |
| Geração de relatório | 2/mês | 2/mês |

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

### Webhooks Stripe

- `stripe.Webhook.construct_event()` obrigatório em todos os eventos recebidos.
- Idempotência: `webhook_events` com `stripe_event_id` UNIQUE —
  segundo recebimento do mesmo evento ignorado silenciosamente.

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
- Taxa de conversão FREE → PRO.

### Alertas críticos

1. Prewarm não iniciou em 30 min do horário programado.
2. < 60% dos endereços/search locations-alvo processados com sucesso no prewarm.
3. API sem resposta por > 60s (health check).
4. `worker-scrape-browser` sem heartbeat por > 5 min.
5. Postgres: `connection pool waiters > 10` por > 2 min.

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

### Fixtures obrigatórias

- GTFS feed reduzido (100 paradas, 10 linhas) para integração.
- Polígonos de vegetação e alagamento para 3 zonas de teste.
- 30 imóveis sintéticos nas 3 zonas.

### CI checks obrigatórios

`mypy` (strict em `core/` e `modules/`) · `ruff` · testes unitários ·
testes integração · smoke Dataset A em staging

---

## 16. Registro de Riscos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Playwright bloqueado pelas plataformas | Alta | Alto | `success_rate` monitorado; Bright Data como escape hatch por plataforma |
| Valhalla OOM (isócrona carro + prewarm) | Média | Alto | Concorrência 2 na fila `zones`; scraping de prewarm restrito a endereços demandados nas últimas 24h |
| Redis pub/sub congestionado | Baixa | Médio | Canal por `job_id`; cleanup automático ao desconectar |
| Prewarm não termina antes do pico matinal | Média | Alto | Limite de 100 endereços por run; alerta em 30 min; escalar VPS se p95 prewarm > 2h |
| S3/R2 signed URL expirada antes do download | Baixa | Baixo | Endpoint de regeneração; retenção de 30 dias |
| Custo Mapbox Search (geocoding + POIs) > orçamento mensal | Média | Médio | Cache efêmero; rate limit por operação; debounce; orçamento diário; reduzir categorias e raio quando necessário |
| Stripe webhook duplicado ativando PRO duas vezes | Baixa | Médio | Idempotência por `stripe_event_id` UNIQUE em `webhook_events` |
| Migração anônima → autenticado perdendo jornada | Baixa | Alto | Transação atômica; fallback: jornada anônima permanece acessível |
| GTFS desatualizado gerando rotas incorretas | Média | Médio | Webhook Mobility Database dispara ingestão automática |
| WeasyPrint consumindo > 600MB | Baixa | Médio | Concorrência 1 na fila `reports`; timeout de job em 60s |

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
| Auth backend | **fastapi-users** | Magic link + OAuth2 + SQLAlchemy 2 sem implementação manual |
| Email provider | **Resend** | 3k/mês gratuito, SDK Python, deliverability |
| Isócrona / rota | **Valhalla self-hosted** | Sem ToS de armazenamento; cache por fingerprint; latência 80–200ms |
| Transporte público | **OTP 2 + GTFS** | Sem custo por request; dados locais; sem proibição de storage |
| Progresso real-time | **SSE (não WebSocket)** | Fluxo unidirecional; mais simples, proxy-friendly |
| Geocoding | **Mapbox Search Box API (proxy)** | Já integrado; custo baixo com cache Redis 24h |
| POIs | **Mapbox Search Box API — Category Search** | Já alinhado ao legado; busca sob demanda por categoria/raio com cache efêmero |
| PDF generator | **WeasyPrint** | HTML/CSS, SVG, Python-native, sem Node no worker |
| DI Fases 0–3 | **Composição manual no lifespan** | Baixa complexidade, sem overhead |
| DI Fase 4+ | **dependency-injector** | Container/Provider explícito, migração incremental |
| Scraping browser | **Playwright no Hostinger VPS** | IP brasileiro; isolado do api/worker-general |
| Scraping HTTP | **httpx no Hostinger VPS (fila scrape_http)** | Válido para plataformas que o permitam |
| Proxy residencial | **Bright Data somente como escape hatch** | Ativação por plataforma; nunca base da arquitetura |
| Auth nas Fases 6–7 | **Toda sessão = FREE** | Elimina dependência circular; PRO ativado na Fase 8 |
| Plataformas FREE | **QuintoAndar + Zap** | Restrição computacional, não de implementação |
| Plataforma PRO extra | **VivaReal** | Terceiro scraper Playwright disponível |
| Preço Pro | **R$29/mês ou R$249/ano** | — |
| Relatório avulso | **R$9,90** | — |
