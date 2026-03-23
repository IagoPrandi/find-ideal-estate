# Imóvel Ideal — Documentação Técnica Completa

**Versão do documento:** 1.1  
**Data:** 2026-03-06  
**Versão do projeto:** MVP Local v1.4

---

## Sumário

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura do Sistema](#2-arquitetura-do-sistema)
3. [Estrutura de Diretórios](#3-estrutura-de-diretórios)
4. [Infraestrutura (Docker)](#4-infraestrutura-docker)
5. [Backend — FastAPI](#5-backend--fastapi)
   - 5.1 [Endpoints da API](#51-endpoints-da-api)
   - 5.2 [Runner (Pipeline)](#52-runner-pipeline)
   - 5.3 [RunStore](#53-runstore)
   - 5.4 [Schemas Pydantic](#54-schemas-pydantic)
6. [Adapters](#6-adapters)
7. [Core — Módulos de Negócio](#7-core--módulos-de-negócio)
8. [Scripts (cods_ok)](#8-scripts-cods_ok)
9. [Frontend (UI)](#9-frontend-ui)
10. [APIs Externas](#10-apis-externas)
11. [Estrutura de Artifacts (runs/)](#11-estrutura-de-artifacts-runs)
12. [Data Cache Local](#12-data-cache-local)
13. [Configuração e Variáveis de Ambiente](#13-configuração-e-variáveis-de-ambiente)
14. [Scoring de Imóveis](#14-scoring-de-imóveis)
15. [Fluxo E2E Completo](#15-fluxo-e2e-completo)
16. [Dependências Python](#16-dependências-python)
17. [Requisitos Não-Funcionais (NFRs)](#17-requisitos-não-funcionais-nfrs)

---

## 1. Visão Geral

**Imóvel Ideal** é um MVP local para busca de imóveis em São Paulo com enrichment geoespacial. O sistema permite que o usuário:

1. Marque **pontos de referência** no mapa (trabalho, faculdade, metrô etc.).
2. Receba **zonas candidatas** de moradia alcançáveis por ônibus (GTFS) e/ou trilhos (GeoSampa), dentro de um tempo máximo de deslocamento configurável.
3. Visualize cada zona enriquecida com métricas de:
   - **alagamento** (mancha de inundação — GeoSampa)
   - **área verde** (vegetação significativa — GeoSampa)
   - **segurança pública** (ocorrências SSP, comparativo vs médias municipais)
4. Selecione zonas de interesse e colete automaticamente:
   - **ruas** dentro da zona (via Mapbox Tilequery)
   - **POIs por categoria** (mercado, farmácia, parque, restaurante, academia — via Mapbox Search Box)
   - **paradas de ônibus e estações de metrô/trem** do cache local
   - **imóveis por rua** via meta-scraping (QuintoAndar + VivaReal)
5. Obtenha um **ranking de imóveis** com score composto (preço, transporte, POIs) e exporte em JSON/CSV/GeoJSON.

**Execução 100% local**, sem login, sem deploy, sem multiusuário. Toda persistência é em arquivo no diretório `runs/`.

---

## 2. Arquitetura do Sistema

```
┌──────────────────────────────────────────────────────────────────┐
│                         Docker Compose                           │
│  ┌───────────────────────────┐  ┌──────────────────────────────┐ │
│  │  ui (Vite + React + TS)   │  │  api (FastAPI + Playwright)  │ │
│  │  porta 5173               │  │  porta 8000                  │ │
│  │  Mapbox GL JS             │  │  Uvicorn                     │ │
│  └───────────┬───────────────┘  └──────────────┬───────────────┘ │
│              │  HTTP REST                       │                 │
│              └──────────────────────────────────┘                 │
│                                                                    │
│  Volumes: ./runs, ./cache, ./data_cache (ro), ./profiles          │
└──────────────────────────────────────────────────────────────────┘

Backend interno:
api/FastAPI
  ├── Runner (asyncio.to_thread)
  │    ├── CandidateZonesAdapter → candidate_zones_from_cache_v10_fixed2.py
  │    ├── ZoneEnrichAdapter     → zone_enrich_green_flood_v8_tiled_groups_fixed.py
  │    ├── PublicSafetyOps       → segurancaRegiao.py
  │    └── Consolidate           → core/consolidate.py
  │
  ├── ZoneOps (build_zone_detail)
  │    ├── StreetsAdapter         → encontrarRuasRaio.py
  │    ├── PoisAdapter            → pois_categoria_raio.py
  │    └── Transport (GTFS + GPKG local)
  │
  └── ListingsOps (scrape + finalize)
       └── ListingsAdapter        → realestate_meta_search.py
```

**Rede Docker:** `imovel-ideal`  
**API:** `http://localhost:8000`  
**UI:** `http://localhost:5173`

---

## 3. Estrutura de Diretórios

```
principal/
├── app/                        # Aplicação FastAPI
│   ├── main.py                 # Definição de rotas (endpoints)
│   ├── runner.py               # Orquestrador assíncrono do pipeline
│   ├── schemas.py              # Modelos Pydantic (request/response)
│   ├── store.py                # Persistência de estado do run (JSON em disco)
│   └── __init__.py
│
├── adapters/                   # Wrappers de subprocess para scripts externos
│   ├── candidate_zones_adapter.py   # Wrap de candidate_zones_from_cache_v10_fixed2.py
│   ├── zone_enrich_adapter.py       # Wrap de zone_enrich_green_flood_v8_tiled_groups_fixed.py
│   ├── listings_adapter.py          # Wrap de realestate_meta_search.py
│   ├── streets_adapter.py           # Wrap de encontrarRuasRaio.py
│   └── pois_adapter.py              # Wrap de pois_categoria_raio.py
│
├── core/                       # Lógica de negócio pura (sem subprocess)
│   ├── consolidate.py          # Consolidação e deduplicação de zonas multi-ponto
│   ├── zone_ops.py             # Detalhe de zonas (ruas/POIs/transporte/rotas)
│   ├── listings_ops.py         # Scraping de imóveis por zona + finalização
│   └── public_safety_ops.py    # Artifacts de segurança pública (SSP)
│
├── cods_ok/                    # Scripts Python autônomos (não alterar lógica)
│   ├── candidate_zones_from_cache_v10_fixed2.py  # Geração de zonas candidatas (GTFS/GPKG)
│   ├── zone_enrich_green_flood_v8_tiled_groups_fixed.py  # Enriquecimento verde/inundação
│   ├── gpkg_grid_tiler_v3_splitmerge.py          # Geração de tile_index.csv para verde
│   ├── encontrarRuasRaio.py                       # Coleta de ruas via Mapbox Tilequery
│   ├── pois_categoria_raio.py                     # Coleta de POIs via Mapbox Search Box
│   ├── realestate_meta_search.py                  # Meta-scraping (QuintoAndar + VivaReal)
│   ├── quintoAndar.py                             # Parser/scraper QuintoAndar
│   ├── vivaReal.py                                # Parser/scraper VivaReal
│   ├── zapImoveis.py                              # Parser/scraper ZAP Imóveis
│   └── segurancaRegiao.py                         # Consulta de segurança pública (SSP/CEM)
│
├── apps/web/                   # Frontend canônico (Vite + React + TypeScript)
│   ├── src/
│   │   ├── features/app/FindIdealApp.tsx  # App principal (fluxo 3 etapas)
│   │   ├── App.test.tsx        # Testes de fluxo frontend (Vitest)
│   │   └── ...
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── ui/                         # Legado — use `apps/web` (ver `ui/README.md`)
│
├── data_cache/                 # Cache local de dados (montado read-only no Docker)
│   ├── gtfs/                   # Arquivos GTFS (stops.txt, trips.txt, etc.)
│   └── geosampa/               # Arquivos GeoPackage (.gpkg) do GeoSampa SP
│
├── cache/                      # Cache de runtime (tiles de vegetação gerados)
│   └── green_tiles_v3/
│       └── tile_index.csv
│
├── runs/                       # Artifacts por run_id (gerados em execução)
│   └── <run_id>/               # Ex: 20260302145349_49859cdb
│       ├── input.json
│       ├── status.json
│       ├── selected_zones.json
│       ├── logs/events.jsonl
│       ├── security/
│       ├── zones/
│       └── final/
│
├── profiles/                   # Perfil persistente do navegador (VivaReal)
├── docker/
│   ├── api.Dockerfile
│   └── ui.Dockerfile
├── docker-compose.yml
├── platforms.yaml              # Configuração das plataformas de scraping
├── pyproject.toml
├── requirements.txt
└── .env                        # Variáveis de ambiente (não versionado)
```

---

## 4. Infraestrutura (Docker)

### Serviços

| Serviço | Imagem base | Porta | Responsabilidade |
|---------|-------------|-------|------------------|
| `api` | `mcr.microsoft.com/playwright/python:v1.50.0-jammy` | `8000` | FastAPI + pipeline + Playwright |
| `ui` | Node.js | `5173` | Vite dev server (React/TS) |

### Volumes montados no `api`

| Volume host | Volume container | Modo |
|-------------|-----------------|------|
| `./data_cache` | `/app/data_cache` | read-only |
| `./runs` | `/app/runs` | read-write |
| `./cache` | `/app/cache` | read-write |
| `./profiles` | `/app/profiles` | read-write |

### Comandos de operação

```bash
# Subir todos os serviços (build automático se necessário)
docker compose -p onde_morar_mvp up -d --build

# Rebuild apenas da api (após mudanças de código backend)
docker compose -p onde_morar_mvp build api
docker compose -p onde_morar_mvp up -d api

# Ver logs
docker compose -p onde_morar_mvp logs -f api

# Parar tudo
docker compose -p onde_morar_mvp down
```

### Healthcheck do `api`
- **Endpoint:** `GET /health`
- **Intervalo:** 10s | **Timeout:** 3s | **Retries:** 5

---

## 5. Backend — FastAPI

**Arquivo principal:** `app/main.py`  
**Versão:** `0.2.0`  
**CORS:** origens configuráveis via `CORS_ALLOW_ORIGINS` (default: `http://localhost:5173,http://127.0.0.1:5173`)

### 5.1 Endpoints da API

#### `GET /health`
- **Descrição:** Health check básico
- **Response:** `{"status": "ok"}`

#### `GET /health/ready`
- **Descrição:** Readiness check
- **Response:** `{"status": "ready"}`

---

#### `POST /runs`
- **Descrição:** Cria um novo run e inicia o pipeline de geração de zonas em background
- **Request Body** (`RunCreateRequest`):
  ```json
  {
    "reference_points": [
      {"name": "Trabalho", "lat": -23.5505, "lon": -46.6333}
    ],
    "params": {
      "t_bus": 40,
      "t_rail": 40,
      "seed_bus_max_dist_m": 1000,
      "seed_rail_max_dist_m": 2000,
      "buffer_m": 700,
      "zone_dedupe_m": 50,
      "public_safety_enabled": false,
      "listing_mode": "rent"
    }
  }
  ```
- **Response** (`RunCreateResponse`):
  ```json
  {
    "run_id": "20260302145349_49859cdb",
    "status": {
      "state": "running",
      "stage": "validate",
      "stages": [...],
      "created_at": "2026-03-02T14:53:49Z",
      "updated_at": "2026-03-02T14:53:49Z"
    }
  }
  ```
- **Efeito:** cria `runs/<run_id>/` com `input.json`, `status.json`; dispara `runner.run_pipeline(run_id)` como `asyncio.create_task`

---

#### `GET /runs/{run_id}/status`
- **Descrição:** Retorna o status atual do pipeline
- **Response** (`RunStatusResponse`):
  ```json
  {
    "run_id": "...",
    "status": {
      "state": "running|success|failed",
      "stage": "validate|public_safety|zones_by_ref|zones_enrich|zones_consolidate|done",
      "stages": [{"name": "...", "state": "running|success|failed|skipped", "updated_at": "..."}],
      "created_at": "...",
      "updated_at": "..."
    }
  }
  ```
- **Erro:** `404` se `run_id` não existe

---

#### `GET /runs/{run_id}/zones`
- **Descrição:** Retorna o GeoJSON de zonas consolidadas; adiciona `zone_name` e `zone_index` (sequencial) nas propriedades
- **Response:** `application/geo+json` — `FeatureCollection` com features de polígono
- **Campos de cada feature (properties):**
  - `zone_uid` — hash hexadecimal de 16 chars
  - `zone_name` — "Zona 1", "Zona 2"…
  - `zone_index` — índice sequencial
  - `score` — score de qualidade da zona
  - `time_agg` — tempo máximo de deslocamento de qualquer ref
  - `time_by_ref` — mapa `ref_i → minutos`
  - `flood_ratio_r800`, `green_ratio_r700` — ratios de alagamento/verde em buffer
  - `mode` — `"bus"` ou `"rail"`
  - `trace` — informações do trajeto que gerou a zona (`route_id`, `seed_bus_stop_id`, `downstream_stop_id` etc.)
- **Erro:** `404` se zonas não foram geradas ainda

---

#### `GET /runs/{run_id}/security`
- **Descrição:** Retorna artifact agregado de segurança pública (SSP/CEM)
- **Response:** `application/json` — objeto com ocorrências por tipo por ponto de referência
- **Erro:** `404` se segurança pública não foi habilitada/executada

---

#### `GET /runs/{run_id}/transport/routes`
- **Descrição:** Retorna linhas de ônibus, metrô e trem para o run (geometria real via GeoSampa)
- **Response:** `application/json`:
  ```json
  {
    "bus_lines": [{"id": "...", "name": "...", "geometry": {...}}],
    "metro_lines": [...],
    "train_lines": [...]
  }
  ```
- **Fonte de dados:** GeoPackage locais (`SIRGAS_GPKG_linhaonibus.gpkg`, `geoportal_linha_metro_v4.gpkg`, `geoportal_linha_trem_v2.gpkg`)

---

#### `GET /transport/stops`
- **Descrição:** Retorna paradas de ônibus e estações de metrô/trem. Aceita consulta por:
  - `bbox` (viewport): `minLon,minLat,maxLon,maxLat`
  - ou `lon` + `lat` + `radius_m` (default 2500m)
- **Response:**
  ```json
  {
    "bus_stops": [{"id": "...", "name": "...", "lat": -23.5, "lon": -46.6, "distance_m": 120}],
    "stations": [{"id": "...", "name": "...", "lat": ..., "lon": ...}]
  }
  ```
- **Fonte:** `data_cache/gtfs/stops.txt` + GPKGs de estações

---

#### `POST /runs/{run_id}/zones/select`
- **Descrição:** Registra quais zonas o usuário selecionou para detalhamento
- **Request Body** (`ZoneSelectionRequest`):
  ```json
  {"zone_uids": ["abc123", "def456"]}
  ```
- **Response:** `{"message": "2 zones selected"}`
- **Efeito:** cria `runs/<run_id>/selected_zones.json`

---

#### `POST /runs/{run_id}/zones/{zone_uid}/detail`
- **Descrição:** Coleta ruas, POIs e pontos de transporte da zona; retorna sumário rico
- **Request:** sem body
- **Flags opcionais de inclusão** (lidas de `params` do run — todas `true` por default):
  - `zone_detail_include_pois` — inclui contagem e pontos de POIs
  - `zone_detail_include_transport` — inclui paradas/estações e linhas
  - `zone_detail_include_green` — inclui `green_area_ratio`
  - `zone_detail_include_flood` — inclui `flood_area_ratio`
  - `zone_detail_include_public_safety` — inclui bloco `public_safety` com dados SSP
- **Response** (`ZoneDetailResponse`):
  ```json
  {
    "zone_uid": "...",
    "zone_name": "Zona 1",
    "green_area_ratio": 0.12,
    "flood_area_ratio": 0.03,
    "poi_count_by_category": {"mercado": 3, "farmacia": 2},
    "bus_lines_count": 5,
    "train_lines_count": 1,
    "bus_stop_count": 12,
    "train_station_count": 1,
    "lines_used_for_generation": [{"mode": "bus", "route_id": "...", "line_name": "..."}],
    "reference_transport_point": {"kind": "bus_stop", "id": "...", "name": "...", "lat": ..., "lon": ...},
    "seed_transport_point": {...},
    "downstream_transport_point": {...},
    "transport_points": [...],
    "poi_points": [...],
    "streets_count": 8,
    "has_street_data": true,
    "has_poi_data": true,
    "has_transport_data": true,
    "public_safety": {
      "enabled": true,
      "year": 2025,
      "radius_km": 1.0,
      "result": {},
      "summary": {
        "ocorrencias_no_raio_total": 142,
        "top_delitos_no_raio": [{"tipo_delito": "furto", "qtd": 80}],
        "delta_pct_vs_cidade": 12.3,
        "regiao_media_dia": 0.39,
        "cidade_media_dia": 0.35,
        "delegacias_mais_proximas": [{"nome": "...", "dist_km": 0.8, "total_ocorrencias": 210}]
      }
    }
  }
  ```
- **Nota:** se `public_safety_enabled=false`, o campo `public_safety` retorna `{"enabled": false, "reason": "public_safety_enabled=false"}`
- **Efeito colateral:** cria artifacts em `runs/<run_id>/zones/detail/<zone_uid>/`; se segurança for coletada, persiste em `runs/<run_id>/zones/detail/<zone_uid>/public_safety.json`

---

#### `GET /runs/{run_id}/zones/{zone_uid}/streets`
- **Descrição:** Retorna lista de ruas da zona (a partir de `streets.json` já gerado)
- **Response:** `{"zone_uid": "...", "streets": ["Rua X", "Avenida Y"]}`
- **Erro:** `404` se detail não foi executado ainda

---

#### `POST /runs/{run_id}/zones/{zone_uid}/listings`
- **Descrição:** Executa o meta-scraping de imóveis por rua para a zona
- **Request Body** (opcional, `ListingsScrapeRequest`):
  ```json
  {"street_filter": "Rua das Flores"}
  ```
- **Comportamento:**
  - se `street_filter` fornecido: coleta somente aquela rua
  - se não: coleta até `max_streets_per_zone` ruas (default: 3)
  - ruas sem tipo de logradouro válido são rejeitadas
  - por default exige resultados de todas as plataformas (`require_all_listing_platforms=true`); lança erro se alguma retornar 0 resultados
- **Response** (`ListingsScrapeResponse`):
  ```json
  {
    "zone_uid": "...",
    "listings_count": 5,
    "listings_total": 127,
    "platform_counts": {"quinto_andar": 45, "vivareal": 60, "zapimoveis": 22}
  }
  ```
- **Campos:**
  - `listings_count` — número de arquivos de resultado (run dirs por rua)
  - `listings_total` — total de itens de imóveis somados de todos os arquivos
  - `platform_counts` — breakdown por plataforma (`quinto_andar`, `vivareal`, `zapimoveis`)

---

#### `POST /runs/{run_id}/finalize`
- **Descrição:** Consolida imóveis de todas as zonas selecionadas; aplica score; exporta arquivos finais
- **Pré-requisito:** `selected_zones.json` deve existir com ao menos uma zona
- **Response** (`FinalizeResponse`):
  ```json
  {
    "listings_final_json": "runs/20260302.../final/listings_final.json",
    "listings_final_csv": "runs/20260302.../final/listings_final.csv",
    "listings_final_geojson": "runs/20260302.../final/listings_final.geojson",
    "zones_final_geojson": "runs/20260302.../final/zones_final.geojson"
  }
  ```
- **Filtros aplicados ao finalizar:**
  - `address` deve conter tipo de logradouro válido (rua, avenida, alameda etc.)
  - `address` não pode conter "acesso"
  - `state` deve estar preenchido (campo de estado do imóvel no scraper)
  - coordenadas (`lat`/`lon`) válidas (para inclusão no GeoJSON)

---

#### `GET /runs/{run_id}/final/listings`
- **Response:** `listings_final.geojson` — GeoJSON com pontos de imóveis

#### `GET /runs/{run_id}/final/listings.csv`
- **Response:** `listings_final.csv`

#### `GET /runs/{run_id}/final/listings.json`
- **Response:** `listings_final.json`

---

### 5.2 Runner (Pipeline)

**Arquivo:** `app/runner.py`  
**Classe:** `Runner`

O pipeline é executado de forma assíncrona. Etapas pesadas rodam em `asyncio.to_thread` para não bloquear o event loop do FastAPI (permitindo polling de `/status` durante execução).

#### Etapas do pipeline

| Etapa | Stage name | Obrigatória | Descrição |
|-------|-----------|-------------|-----------|
| Validação | `validate` | Sim | Valida input e inicializa |
| Segurança Pública | `public_safety` | Não (param `public_safety_enabled`) | SSP + CEM por ponto de referência |
| Zonas por Ref | `zones_by_ref` | Sim | Executa `candidate_zones` para cada ponto |
| Enriquecimento | `zones_enrich` | Sim | Enriquece cada ref com verde/inundação |
| Consolidação | `zones_consolidate` | Sim | Deduplicação espacial e merge multi-ref |

#### Estados de etapa
- `running` — em execução
- `success` — concluída com sucesso
- `failed` — falhou (propaga estado `failed` ao run)
- `skipped` — etapa opcional não habilitada

#### Tratamento de erros
- `public_safety`: falha não-fatal por padrão (controlado por `public_safety_fail_on_error`)
- Demais: falha fatal → estado do run passa para `failed`
- Logs gravados em `runs/<run_id>/logs/events.jsonl`

---

### 5.3 RunStore

**Arquivo:** `app/store.py`  
**Classe:** `RunStore`

Persistência baseada em arquivo JSON por `run_id`.

#### Métodos principais

| Método | Descrição |
|--------|-----------|
| `create_run(payload)` | Gera `run_id`, cria diretório, salva `input.json` e `status.json` |
| `get_status(run_id)` | Lê `status.json` e retorna `RunStatus` |
| `get_input(run_id)` | Lê `input.json` |
| `update_status(run_id, state, stage)` | Atualiza campos `state`, `stage`, `updated_at` em `status.json` |
| `append_stage(run_id, name, state)` | Adiciona/atualiza entrada na lista `stages` |
| `set_failed(run_id, stage, error_type, message)` | Marca run como falho com detalhe de erro |
| `append_log(run_id, level, stage, message, **extra)` | Appende linha JSONL em `logs/events.jsonl` |

#### Geração do `run_id`
```
run_id = <YYYYMMDDHHMMSS>_<sha256(input serializado)[:8]>
```
Determinístico: mesmo input → mesmo `run_id`.

---

### 5.4 Schemas Pydantic

**Arquivo:** `app/schemas.py`

| Schema | Uso | Mudanças recentes |
|--------|-----|------------------|
| `ReferencePoint` | Ponto de referência (`name`, `lat`, `lon`) | — |
| `RunCreateRequest` | Body do `POST /runs` | — |
| `RunStatus` | Estado interno do run | — |
| `RunCreateResponse` | Response do `POST /runs` | — |
| `RunStatusResponse` | Response do `GET /status` | — |
| `ZoneSelectionRequest` | Body do `POST .../zones/select` | — |
| `SimpleMessageResponse` | Response genérica de mensagem | — |
| `ZonePoint` | Ponto geográfico tipado (poi/bus_stop/station) | — |
| `ZoneDetailResponse` | Response do `POST .../zones/{uid}/detail` | **+** `public_safety: Optional[Dict]` |
| `ListingsScrapeRequest` | Body opcional do `POST .../listings` | — |
| `ListingsScrapeResponse` | Response do `POST .../listings` | **+** `listings_total: int`, **+** `platform_counts: Dict[str,int]` |
| `FinalizeResponse` | Response do `POST .../finalize` | — |

---

## 6. Adapters

Os adapters invocam scripts externos via `subprocess.run(args, check=True)` e padronizam a interface Python→CLI.

### `adapters/candidate_zones_adapter.py`

**Função:** `run_candidate_zones(cache_dir, out_dir, seed_lat, seed_lon, params)`

**Script invocado:** `cods_ok/candidate_zones_from_cache_v10_fixed2.py`

**Parâmetros CLI mapeados:**

| Parâmetro Python `params` | Flag CLI |
|--------------------------|---------|
| `buffer_m` | `--buffer-m` |
| `t_bus` | `--t-bus` |
| `t_rail` | `--t-rail` |
| `seed_bus_max_dist_m` | `--seed-bus-max-dist-m` |
| `seed_rail_max_dist_m` | `--seed-rail-max-dist-m` |
| `dedupe_radius_m` | `--dedupe-radius-m` |

**Flags fixas:** `--auto-rail-seed` (busca automaticamente a semente de trilho mais próxima)

**Output:** diretório `out_dir/` com `zones.geojson`, `ranking.csv`, `trace.json`

---

### `adapters/zone_enrich_adapter.py`

**Função:** `run_zone_enrich(runs_dir, geodir, out_dir, params)`

**Script invocado:** `cods_ok/zone_enrich_green_flood_v8_tiled_groups_fixed.py`

**Resolução de tiles de vegetação:**
1. Verifica parâmetros `green_tiles_dir` e `green_tile_index` em `params`
2. Usa `cache/green_tiles_v3/tile_index.csv` se existir (cache persistente)
3. Fallback para `data_cache/geosampa/green_tiles_v3/`
4. Se `tile_index.csv` não existir em nenhum lugar → invoca `gpkg_grid_tiler_v3_splitmerge.py` para gerá-los automaticamente a partir de `SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg`

**Output:** `out_dir/zones_enriched.geojson`, `out_dir/ranking_enriched.csv`

---

### `adapters/listings_adapter.py`

**Função:** `run_listings_all(config_path, out_dir, mode, address, center_lat, center_lon, radius_m, max_pages, headless)`

**Script invocado:** `cods_ok/realestate_meta_search.py`

**Wrapper xvfb:** usa `xvfb-run -a` automaticamente se disponível (ambiente headless Linux)

**Parâmetros:**

| Parâmetro | Descrição | Default |
|-----------|-----------|---------|
| `config_path` | Caminho do `platforms.yaml` | - |
| `out_dir` | Diretório de saída | - |
| `mode` | `"rent"` ou `"buy"` | - |
| `address` | Endereço de busca (ex: "Rua X, São Paulo, SP") | - |
| `center_lat/lon` | Centro para filtro por raio | - |
| `radius_m` | Raio de busca em metros | 1500 |
| `max_pages` | Máximo de páginas por plataforma | 2 |
| `headless` | Navegador sem interface gráfica | `True` |

**Output:** diretório de run mais recente dentro de `out_dir/runs/`

---

### `adapters/streets_adapter.py`

**Função:** `run_streets(lon, lat, radius_m, out_path, step_m, query_radius_m, max_workers)`

**Script invocado:** `cods_ok/encontrarRuasRaio.py`

**Parâmetros:**

| Parâmetro | Descrição | Default |
|-----------|-----------|---------|
| `step_m` | Passo da grade de amostragem | 150m |
| `query_radius_m` | Raio de cada consulta Mapbox Tilequery | 120m |
| `max_workers` | Threads paralelas | 8 |

**Output:** JSON em `out_path` com lista de ruas únicas dentro do raio

---

### `adapters/pois_adapter.py`

**Função:** `run_pois(lon, lat, radius_m, out_path, limit)`

**Script invocado:** `cods_ok/pois_categoria_raio.py`

**Parâmetros:**

| Parâmetro | Descrição | Default |
|-----------|-----------|---------|
| `radius_m` | Raio de busca | - |
| `limit` | Limite de POIs por categoria | 25 |

**Output:** JSON em `out_path` com resultados por categoria

---

## 7. Core — Módulos de Negócio

### `core/consolidate.py`

**Função principal:** `consolidate_zones(run_dir, zone_dedupe_m) → Path`

**Input:** todos os `zones_enriched.geojson` em `runs/<run_id>/zones/by_ref/ref_*/enriched/`

**Algoritmo:**
1. Carrega todas as features enriquecidas
2. Reprojeção para UTM EPSG:31983 (metros)
3. Clusterização greedy por distância de centróides (`eps_m` = `zone_dedupe_m`)
4. Por cluster: seleciona a feature com maior score como representativa
5. Gera `zone_uid = sha256(round(cx,1)|round(cy,1)|buffer_m)[:16]`
6. Agrega `time_by_ref` (mínimo por ref no cluster) e `time_agg` (máximo dos times_by_ref)

**Output:**
```
runs/<run_id>/zones/consolidated/
  zones_consolidated.geojson    # FeatureCollection consolidada
  ranking_consolidated.csv      # Tabela de ranking
```

---

### `core/zone_ops.py`

#### `build_zone_detail(run_dir, zone_uid, params) → Dict[str, Path]`
Coleta ruas, POIs e transporte de uma zona. Cria artifacts em `runs/<run_id>/zones/detail/<zone_uid>/`.

**Lógica de raio:** calculado como máximo da distância centróide → cantos da bounding box + 150m (mínimo 300m).

**Retorna:** `{"streets": Path, "pois": Path, "transport": Path}`

#### `build_zone_detail` — parâmetros relevantes de `params`

| Param | Descrição | Default |
|-------|-----------|---------|
| `zone_detail_radius_m` | Raio mínimo para busca de ruas | 1200m |

#### `haversine_m(lat1, lon1, lat2, lon2) → float`
Distância haversine em metros entre dois pontos geográficos.

#### `zone_centroid_lonlat(zone_feature) → (lon, lat)`
Extrai centróide do feature (de `properties.centroid_lon/lat` ou calcula a partir da geometria).

#### `get_zone_feature(run_dir, zone_uid) → Dict`
Busca o feature GeoJSON de uma zona pelo `zone_uid` no arquivo consolidado.

#### `build_run_transport_layers(run_dir) → Dict`
Monta camadas de rotas de transporte (ônibus/metrô/trem) a partir dos GeoPackages do GeoSampa.

#### `build_transport_stops_for_point(lon, lat, radius_m, bbox) → Dict`
Retorna paradas de ônibus (GTFS `stops.txt`) e estações (GPKGs) num raio ou bbox.

---

### `core/listings_ops.py`

#### `scrape_zone_listings(run_dir, zone_uid, params) → List[Path]`
Executa scraping de imóveis por rua para uma zona.

**Fluxo:**
1. Obtém centróide e `streets.json` da zona
2. Filtra ruas com tipo de logradouro válido (excluindo "acesso")
3. Para cada rua: chama `run_listings_all` via adapter
4. Procura `compiled_listings_parsed.json` primeiro; fallback para `compiled_listings.json`
5. Salva resultado em `runs/.../zones/detail/<zone_uid>/streets/<slug>/listings/compiled_listings.json`
6. Acumula `platform_counts_total` por plataforma
7. Se `require_all_listing_platforms=true` e alguma tiver 0 → lança `RuntimeError`

**Filtro de ruas válidas:**
```
Tipos aceitos: rua, avenida, alameda, travessa, estrada, rodovia, praça, largo, viela, beco
Tokens rejeitados: acesso
```

**Plataformas rastreadas (`_REQUIRED_LISTING_PLATFORMS`):** `quinto_andar`, `vivareal`, `zapimoveis`

**Parâmetros de `params`:**

| Param | Descrição | Default |
|-------|-----------|---------|
| `street_filter` | Filtrar por rua específica | `None` (todas) |
| `max_streets_per_zone` | Máximo de ruas | 3 |
| `listing_mode` | `"rent"` ou `"buy"` | `"rent"` |
| `listing_radius_m` | Raio de busca | 1500m |
| `listing_max_pages` | Máximo de páginas | 2 |
| `listings_config` | Caminho do `platforms.yaml` | `"platforms.yaml"` |
| `listings_headless` | Modo headless | `True` |
| `require_all_listing_platforms` | Exige ≥1 resultado de cada plataforma | `True` |

**Helpers internos:**
- `_platform_counts_from_payload(payload)` — conta itens por plataforma a partir do payload JSON
- `_infer_state_from_address(address)` — extrai UF via regex `", XX"` do endereço (ex: `", SP"` → `"SP"`)
- `_REQUIRED_LISTING_PLATFORMS` — constante com as 3 plataformas obrigatórias

#### `finalize_run(run_dir, selected_zone_uids, params) → Dict[str, Path]`
Consolida imóveis de todas as zonas selecionadas, aplica scoring e exporta.

**Filtros de qualidade:**
- `address` deve ter tipo de logradouro válido e não conter "acesso"
- `state`: se ausente, inferido de `_infer_state_from_address()`; se `require_state_in_listing=true` e ainda vazio → imóvel rejeitado (default do param: `false`)
- Coordenadas válidas para inclusão no GeoJSON

**Enriquecimento de segurança pública por zona:**
- Chama `get_zone_public_safety()` para cada zona selecionada
- Adiciona a cada imóvel os campos:
  - `zone_public_safety_enabled` — bool
  - `zone_public_safety_year` — int
  - `zone_public_safety_radius_km` — float
  - `zone_public_safety_occurrences_total` — int
  - `zone_public_safety_delta_pct_vs_cidade` — float

**Score calculado por imóvel:**
```python
score = w_price * price_score + w_transport * transport_score + w_pois * poi_score
```
(ver seção 14 para detalhes)

**Params adicionais:**

| Param | Descrição | Default |
|-------|-----------|--------|
| `require_state_in_listing` | Rejeita imóvel se estado ausente após inferência | `false` |

**Output:**
```
runs/<run_id>/final/
  listings_final.json      # Lista ordenada por score (com campos zone_public_safety_*)
  listings_final.csv       # CSV com todos os campos
  listings_final.geojson   # Apenas imóveis com coordenadas válidas
  zones_final.geojson      # Cópia das zonas consolidadas
```

---

### `core/public_safety_ops.py`

#### `build_public_safety_artifacts(run_dir, reference_points, params) → (Path, List[Path])`
Coleta dados de segurança pública (SSP/CEM) por ponto de referência dinamicamente via `segurancaRegiao.py`. Usada pelo Runner na etapa `public_safety`.

**Parâmetros de `params`:**

| Param | Descrição | Default |
|-------|-----------|---------|
| `public_safety_enabled` | Habilita a etapa | `false` |
| `public_safety_fail_on_error` | Falha fatal em erro | `false` |
| `public_safety_radius_km` | Raio de consulta SSP | 1.0 km |
| `public_safety_year` | Ano dos dados SSP | 2025 |

**Output por ref:**
```
runs/<run_id>/security/by_ref/ref_<i>/public_safety.json
```
**Output agregado:**
```
runs/<run_id>/security/public_safety.json
```

#### `get_zone_public_safety(run_dir, zone_uid, lat, lon, params) → Dict`
Retorna dados de segurança pública para uma zona específica. Chamada pelo endpoint `zone_detail` e por `finalize_run`.

**Lógica:**
1. Se `public_safety_enabled=false` → retorna `{"enabled": False, "reason": "..."}`
2. Se `runs/<run_id>/zones/detail/<zone_uid>/public_safety.json` já existir → reutiliza cache
3. Caso contrário, chama `segurancaRegiao.run_query(lat, lon, radius_km, ano)` e persiste
4. Em caso de erro: propaga se `public_safety_fail_on_error=true`; senão retorna `{"enabled": False, "error": "..."}`

**Estrutura de retorno:**
```json
{
  "enabled": true,
  "year": 2025,
  "radius_km": 1.0,
  "result": { "...dados brutos SSP..." },
  "summary": {
    "ocorrencias_no_raio_total": 142,
    "top_delitos_no_raio": [{"tipo_delito": "furto", "qtd": 80}],
    "delta_pct_vs_cidade": 12.3,
    "regiao_media_dia": 0.39,
    "cidade_media_dia": 0.35,
    "delegacias_mais_proximas": [{"nome": "...", "dist_km": 0.8, "total_ocorrencias": 210}]
  }
}
```

**Artifact persistido:**
```
runs/<run_id>/zones/detail/<zone_uid>/public_safety.json
```

#### `_build_public_safety_summary(result) → Dict`
Helper interno: extrai sumário legível dos dados brutos SSP — total de ocorrências, top 5 tipos de delito, comparativo com média municipal e delegacias próximas.

---

## 8. Scripts (cods_ok)

> Scripts autônomos invocados via subprocess. **Não alterar lógica interna.**

### `candidate_zones_from_cache_v10_fixed2.py`
**Propósito:** Gera zonas candidatas de moradia alcançáveis por transporte público a partir de uma semente.

**Inputs:**
- `--cache-dir`: diretório com GTFS e GeoPackages
- `--seed-bus-coord=lat,lon`: semente para ônibus
- `--auto-rail-seed`: busca automaticamente a estação de trilho mais próxima
- `--out-dir`: diretório de saída
- `--buffer-m`: raio do buffer da zona (default: 700m)
- `--t-bus`: tempo máximo de ônibus em minutos (default: 40)
- `--t-rail`: tempo máximo de trem/metrô em minutos (default: 40)
- `--seed-bus-max-dist-m`: distância máxima da semente à parada de ônibus
- `--seed-rail-max-dist-m`: distância máxima da semente à estação de trilho

**Outputs:**
```
out_dir/
  zones.geojson        # Zonas como polígonos (buffers)
  ranking.csv          # Ranking de zonas
  trace.json           # Trajeto usado para gerar cada zona
```

---

### `zone_enrich_green_flood_v8_tiled_groups_fixed.py`
**Propósito:** Enriquece zonas com métricas de vegetação e inundação.

**Inputs:**
- Diretório com `zones.geojson` de entrada
- `--green-tile-index`: CSV com índice de tiles de vegetação
- `--flood-gpkg`: GeoPackage de manchas de inundação
- `--out-dir`: saída

**Outputs:**
```
out_dir/
  zones_enriched.geojson     # Zonas com green_ratio_r700 e flood_ratio_r800
  ranking_enriched.csv
```

**Propriedades adicionadas nas zonas:**
- `green_ratio_r700`: ratio de área verde em buffer de 700m
- `flood_ratio_r800`: ratio de área de inundação em buffer de 800m

---

### `gpkg_grid_tiler_v3_splitmerge.py`
**Propósito:** Gera tiles (grade espacial) a partir do GeoPackage de vegetação para acelerar o enriquecimento.

**Input:** `SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg`
**Output:** `tile_index.csv` + GeoPackages por tile em `green_tiles_v3/`

---

### `encontrarRuasRaio.py`
**Propósito:** Coleta nomes de ruas dentro de um raio via Mapbox Tilequery.

**Inputs:** `--lon`, `--lat`, `--radius`, `--step`, `--query-radius`, `--max-workers`, `--out`
**Output:** JSON com lista deduplicada de ruas no raio

**API externa:** Mapbox Tilequery API (`MAPBOX_ACCESS_TOKEN`)

---

### `pois_categoria_raio.py`
**Propósito:** Coleta POIs por categoria de interesse num raio via Mapbox Search Box.

**Inputs:** `--lon`, `--lat`, `--radius`, `--limit`, `--out`
**Output:** JSON com `{"results": [{nome, categoria, latitude, longitude, canonical_id}]}`

**API externa:** Mapbox Search Box Category API (`MAPBOX_ACCESS_TOKEN`)

---

### `realestate_meta_search.py`
**Propósito:** Meta-scraper que intercepta chamadas de rede do navegador (Playwright) nas plataformas configuradas em `platforms.yaml`.

**Inputs:**
- `all` (subcomando)
- `--config`: caminho do `platforms.yaml`
- `--mode`: `rent` ou `buy`
- `--lat`, `--lon`: centro de busca
- `--address`: logradouro de busca
- `--radius-m`: raio
- `--max-pages`: máximo de páginas
- `--out-dir`: diretório de saída
- `--headless`: modo headless

**Plataformas suportadas** (configuradas em `platforms.yaml`):
- **QuintoAndar**: intercepta `__NEXT_DATA__` JSON embutido
- **VivaReal**: intercepta chamadas para `api/graphql`
- **ZAP Imóveis**: intercepta `glue-api.zapimoveis.com.br/v2/listings`

---

### `quintoAndar.py`, `vivaReal.py`, `zapImoveis.py`
Parsers/scrapers específicos por plataforma. Normalizam os campos para o esquema padrão:
- `id`, `lat`, `lon`, `address`, `price`, `area_m2`, `bedrooms`, `bathrooms`, `parking`, `url`, `state`

---

### `segurancaRegiao.py`
**Propósito:** Consulta dados de ocorrências criminais (SSP) e delegacias (CEM/USP) por coordenada e raio.

**Interface:** expõe `run_query(lat, lon, radius_km, ano)` → `Dict`

**Output por ponto:**
```json
{
  "ocorrencias_by_type": {...},
  "share_ratio_vs_municipio": {...},
  "delegacias_proximas": [...]
}
```

---

## 9. Frontend (UI)

**Stack:** Vite 5 + React 18 + TypeScript 5 + Tailwind CSS 3 + MapLibre GL JS + MapTiler

**Localização:** `apps/web/` (diretório `ui/` está deprecado; ver `ui/README.md`)

### Estrutura de navegação (3 etapas)

#### Etapa 1 — Referências
- Clique no mapa define **ponto principal** (seed de geração de zonas)
- Adicão de **interesses opcionais** com categoria/rótulo
- Toggle **Alugar / Comprar**
- Controles de **tempo máximo de viagem** (ônibus e trem/metrô) e **distância máxima de seed** via sliders sincronizados com inputs numéricos
- CTA **"Gerar Zonas Candidatas"** → `POST /runs`
- Polling de `GET /runs/{run_id}/status` com backoff exponencial + jitter

#### Etapa 2 — Zonas
- Renderização de zonas consolidadas como polígonos/círculos no mapa
- Hubs numerados com badge de tempo e ícone de modo (ônibus/trilho)
- Seleção por clique no mapa ou checkbox na tabela (bidirecional)
- Filtros rápidos: ordenar por score/tempo, exibir só selecionadas
- Camadas togláveis: rotas de ônibus, metrô/trem, pontos de ônibus, zonas candidatas
- CTA **"Detalhar Selecionadas"** → `POST .../zones/{uid}/detail`

#### Etapa 3 — Imóveis
- Pinos de imóveis com label de preço no mapa
- Clique no pin sincroniza com card no painel
- Cards com: preço, plataforma, tamanho (m²), quartos, distâncias
- Expansão de card: distâncias a POIs por categoria de interesse
- **Comparação múltipla:** seleção de vários cards → tabela comparativa com destaque de melhor/pior valor
- Filtro por rua (select com lista das ruas disponíveis)
- Ordenação por preço e tamanho
- CTA "Ver anúncio original"

### Camadas do mapa

| Camada | Sempre visível | Depende de run |
|--------|---------------|----------------|
| Pontos de ônibus | Sim (via bbox) | Não |
| Estações metrô/trem | Sim (via bbox) | Não |
| Zonas candidatas | Não | Sim |
| Rotas de ônibus | Não | Sim |
| Linhas metrô/trem | Não | Sim |
| POIs da zona | Não | Sim (pós-detail) |
| Pins de imóveis | Não | Sim (pós-listings) |

### Contratos Zod (validação de resposta da API)
- Status de run
- GeoJSON de zonas
- ZoneDetailResponse
- Listings finais

### Responsividade
- Desktop: split-screen (mapa 65–72%, painel ~400px fixo)
- Mobile: mapa full-screen + painel como **bottom sheet** deslizante
- Painel minimizável com botão acompanhante no mapa

### Acessibilidade
- Foco visível global
- Fechamento de modais por `Esc`
- Labels semânticos nos controles do mapa

### Scripts npm disponíveis

| Script | Descrição |
|--------|-----------|
| `dev` | Servidor de desenvolvimento Vite |
| `build` | Build de produção |
| `test` | Vitest (watch mode) |
| `test:run` | Vitest (single run) |
| `typecheck` | TypeScript sem emit |
| `lint` | ESLint strict (0 warnings) |
| `format` | Prettier |

---

## 10. APIs Externas

### Mapbox

| API | Uso | Autenticação |
|-----|-----|-------------|
| Mapbox Tilequery | Coleta nomes de ruas (`encontrarRuasRaio.py`) | `MAPBOX_ACCESS_TOKEN` |
| Mapbox Search Box Category | Coleta POIs por categoria (`pois_categoria_raio.py`) | `MAPBOX_ACCESS_TOKEN` |
| MapLibre GL JS + MapTiler | Tiles e mapa interativo (`apps/web/`) | `VITE_MAPTILER_API_KEY` (mesmo valor que `MAPTILER_API_KEY` no compose) |

**Variáveis:** `MAPBOX_ACCESS_TOKEN` — apenas backend/scripts legados (Tilequery, etc.). O frontend Vite usa **MapLibre** + **MapTiler** (`VITE_MAPTILER_API_KEY`), alinhado ao PRD.

### Plataformas de Imóveis (Scraping via Playwright)

| Plataforma | URL base | Modo de captura |
|-----------|---------|-----------------|
| QuintoAndar | `quintoandar.com.br` | `__NEXT_DATA__` JSON embutido na página |
| VivaReal | `vivareal.com.br` | Interceptação de chamadas GraphQL |
| ZAP Imóveis | `zapimoveis.com.br` | Interceptação de `glue-api.zapimoveis.com.br/v2/listings` |

**Nota:** scraping requer Playwright com Chromium instalado. O perfil persistente do navegador (para o VivaReal) é armazenado em `profiles/`.

### SSP (Segurança Pública) — opcional
- Consulta a base de boletins de ocorrência da Secretaria de Segurança Pública de SP
- CEM/USP: localizações de delegacias
- Ativo apenas com `public_safety_enabled=true` nos params

---

## 11. Estrutura de Artifacts (runs/)

Cada execução cria um diretório `runs/<run_id>/` com a seguinte estrutura:

```
runs/<run_id>/
│
├── input.json                          # Input original (reference_points + params)
├── status.json                         # Estado do pipeline
├── selected_zones.json                 # Zonas selecionadas pelo usuário
│
├── logs/
│   └── events.jsonl                    # Log estruturado (JSONL, uma entrada por linha)
│
├── security/                           # (opcional) Etapa public_safety
│   ├── public_safety.json              # Agregado de todas as refs
│   └── by_ref/
│       └── ref_<i>/
│           └── public_safety.json      # Por ponto de referência
│
├── zones/
│   ├── by_ref/
│   │   └── ref_<i>/
│   │       ├── raw/
│   │       │   └── outputs/
│   │       │       ├── zones.geojson
│   │       │       ├── ranking.csv
│   │       │       └── trace.json
│   │       └── enriched/
│   │           ├── zones_enriched.geojson
│   │           └── ranking_enriched.csv
│   │
│   ├── consolidated/
│   │   ├── zones_consolidated.geojson  # Resultado final consolidado de zonas
│   │   └── ranking_consolidated.csv
│   │
│   └── detail/
│       └── <zone_uid>/                 # Por zona selecionada
│           ├── streets.json            # Lista de ruas da zona
│           ├── pois.json               # POIs por categoria
│           ├── transport.json          # Paradas/estações na zona
│           ├── public_safety.json      # Cache SSP por zona (get_zone_public_safety)
│           └── streets/
│               └── <street_slug>/
│                   └── listings/
│                       ├── results.csv
│                       ├── compiled_listings.json   # Imóveis normalizados
│                       └── runs/
│                           └── run_<timestamp>/     # Run dir do scraper
│
└── final/
    ├── listings_final.json             # Lista rankeada (com campos zone_public_safety_*)
    ├── listings_final.csv              # Em CSV
    ├── listings_final.geojson          # Imóveis com coordenadas válidas
    └── zones_final.geojson             # Cópia das zonas consolidadas
```

### Estrutura do `events.jsonl` (log)
```json
{"ts": "2026-03-02T14:53:49Z", "run_id": "...", "level": "info|warning|error", "stage": "...", "message": "...", "...": "extra fields"}
```

---

## 12. Data Cache Local

Dados que devem existir localmente **antes** de executar o pipeline.

### `data_cache/gtfs/`

| Arquivo | Obrigatório | Uso |
|---------|-------------|-----|
| `stops.txt` | Sim | Paradas de ônibus (coordenadas, IDs) |
| `trips.txt` | Sim | Viagens |
| `stop_times.txt` | Sim | Horários por parada |
| `frequencies.txt` | Opcional | Frequências |
| `routes.txt` | Sim | Linhas |
| `calendar.txt` | Opcional | Calendário |

### `data_cache/geosampa/`

| Arquivo | Obrigatório | Uso |
|---------|-------------|-----|
| `geoportal_estacao_metro_v2.gpkg` | Sim | Estações de metrô |
| `geoportal_estacao_trem_v2.gpkg` | Sim | Estações de trem |
| `geoportal_linha_metro_v4.gpkg` | Recomendado | Linhas de metrô (rotas) |
| `geoportal_linha_trem_v2.gpkg` | Recomendado | Linhas de trem (rotas) |
| `SIRGAS_GPKG_linhaonibus.gpkg` | Recomendado | Linhas de ônibus (rotas) |
| `geoportal_ponto_onibus.gpkg` | Recomendado | Pontos de ônibus |
| `SIRGAS_GPKG_mancha_inundacao.gpkg` | Sim | Manchas de inundação |
| `SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg` | Sim | Vegetação significativa |

### `cache/green_tiles_v3/` (gerado automaticamente)
- `tile_index.csv`: índice de tiles de vegetação
- GeoPackages de tiles: `tile_<n>.gpkg`

> Se `tile_index.csv` não existir, o adapter gera os tiles automaticamente via `gpkg_grid_tiler_v3_splitmerge.py`.

---

## 13. Configuração e Variáveis de Ambiente

### `.env` (backend)

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `MAPTILER_API_KEY` | Recomendada | Tiles MapTiler (API e, via compose, `VITE_MAPTILER_API_KEY` no UI) |
| `MAPBOX_ACCESS_TOKEN` | **Sim** (scripts legados) | Token Mapbox para ruas e POIs (backend/offline) |
| `CORS_ALLOW_ORIGINS` | Não | Origens CORS permitidas (default: `http://localhost:5173,http://127.0.0.1:5173`) |
| `RUNS_DIR` | Não | Diretório de runs (default: `runs`) |

### Variáveis no `docker-compose.yml` (UI)

| Variável | Descrição |
|----------|-----------|
| `VITE_API_BASE` | URL base da API (default: `http://localhost:8000`) |
| `VITE_MAPTILER_API_KEY` | Chave MapTiler (tiles + geocoding no browser; default no compose: `MAPTILER_API_KEY`) |

### `platforms.yaml`

Configura o comportamento do scraper por plataforma. **3 plataformas configuradas** (a 3ª foi adicionada recentemente):

| Plataforma | Chave | Modo de captura | `prefer_headful` |
|-----------|-------|-----------------|------------------|
| QuintoAndar | `quinto_andar` | `__NEXT_DATA__` JSON na página | `false` |
| VivaReal | `vivareal` | Interceptação GraphQL (`api/graphql`) | `true` |
| ZAP Imóveis | `zapimoveis` | Interceptação `glue-api.zapimoveis.com.br/v2/listings` | `false` | ← **adicionado** |

**Estrutura por entrada:**

```yaml
platforms:
  <platform_name>:
    start_urls:
      rent: [...]   # URLs de aluguel
      buy: [...]    # URLs de compra
    include_url_substrings: [...]  # Filtro de URLs para interceptação
    listing_path: "..."            # Caminho JSON para os dados (vazio = usa heurística)
    fields:
      id: "..."
      lat: "..."
      lon: "..."
      address: "..."
      price: "..."
      area_m2: "..."
      bedrooms: "..."
      bathrooms: "..."
      parking: "..."
      url: "..."
    prefer_headful: true/false     # Modo headful para plataformas que detectam headless
```

**Configuração ZAP Imóveis (adicionada):** usa o serviço Glue API do grupo OLX (`glue-api.zapimoveis.com.br`), o mesmo backend do VivaReal com schema similar. Campo `parking` mapeado para `parkingSpaces` (diferente das outras plataformas).

### Parâmetros do pipeline (`params` em `POST /runs`)

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `t_bus` | int | 40 | Tempo máximo de ônibus (minutos) |
| `t_rail` | int | 40 | Tempo máximo de trem/metrô (minutos) |
| `buffer_m` | float | 700 | Raio do buffer de zona (metros) |
| `seed_bus_max_dist_m` | float | — | Distância máxima até parada de ônibus |
| `seed_rail_max_dist_m` | float | — | Distância máxima até estação |
| `dedupe_radius_m` | float | — | Raio de deduplicação de zonas |
| `zone_dedupe_m` | float | 50 | Epsilon de clusterização na consolidação |
| `zone_detail_radius_m` | float | 1200 | Raio mínimo de busca de ruas por zona |
| `public_safety_enabled` | bool | false | Habilita etapa de segurança pública |
| `public_safety_fail_on_error` | bool | false | Torna erros de segurança fatais |
| `public_safety_radius_km` | float | 1.0 | Raio SSP em km |
| `public_safety_year` | int | 2025 | Ano dos dados SSP |
| `listing_mode` | str | "rent" | "rent" ou "buy" |
| `listing_radius_m` | float | 1500 | Raio de busca de imóveis |
| `listing_max_pages` | int | 2 | Máximo de páginas por plataforma |
| `max_streets_per_zone` | int | 3 | Máximo de ruas por zona para scraping |
| `listings_config` | str | "platforms.yaml" | Caminho da config de plataformas |
| `listings_headless` | bool | true | Playwright em modo headless |
| `require_all_listing_platforms` | bool | true | Exige ≥1 resultado de cada plataforma obrigatória |
| `require_state_in_listing` | bool | false | Rejeita imóvel se `state` ausente mesmo após inferência |
| `zone_detail_include_pois` | bool | true | Inclui POIs na resposta de detalhe de zona |
| `zone_detail_include_transport` | bool | true | Inclui transporte na resposta de detalhe de zona |
| `zone_detail_include_green` | bool | true | Inclui `green_area_ratio` na resposta de detalhe de zona |
| `zone_detail_include_flood` | bool | true | Inclui `flood_area_ratio` na resposta de detalhe de zona |
| `zone_detail_include_public_safety` | bool | true | Inclui bloco SSP (`public_safety`) na resposta de detalhe |
| `price_ref` | float | 5000 | Preço de referência (para score) |
| `transport_ref_m` | float | 1500 | Distância transporte de referência (score) |
| `pois_ref_m` | float | 1500 | Distância POI de referência (score) |
| `w_price` | float | 0.5 | Peso do preço no score |
| `w_transport` | float | 0.3 | Peso do transporte no score |
| `w_pois` | float | 0.2 | Peso dos POIs no score |

---

## 14. Scoring de Imóveis

O score final de cada imóvel (`score_listing_v1`) é calculado em `finalize_run`:

```python
# Sub-scores (0.0 a 1.0)
price_score     = max(0.0, 1.0 - (price / price_ref))
transport_score = max(0.0, 1.0 - (dist_transport_m / transport_ref_m))
poi_score       = max(0.0, 1.0 - (dist_poi_m / pois_ref_m))

# Score final ponderado
score = w_price * price_score + w_transport * transport_score + w_pois * poi_score
```

**Defaults:** `w_price=0.5`, `w_transport=0.3`, `w_pois=0.2` (soma = 1.0)

**Valores de referência (default):**
- `price_ref = 5000` (R$)
- `transport_ref_m = 1500m`
- `pois_ref_m = 1500m`

**Imóveis sem coordenadas** são incluídos no JSON/CSV mas excluídos do GeoJSON.

---

## 15. Fluxo E2E Completo

```
Usuário (UI)
│
├─ Etapa 1: Define pontos de referência (lat/lon) + params
│   └─ POST /runs → run_id criado, pipeline inicia em background
│
├─ Polling: GET /runs/{run_id}/status
│   ├─ stage: validate → public_safety → zones_by_ref → zones_enrich → zones_consolidate → done
│   └─ Quando state="success": navega para etapa 2
│
├─ Etapa 2: Visualiza zonas no mapa
│   ├─ GET /runs/{run_id}/zones → GeoJSON de zonas
│   ├─ GET /transport/stops?bbox=... → paradas no viewport
│   ├─ GET /runs/{run_id}/transport/routes → rotas reais (opcional)
│   ├─ Usuário seleciona zonas de interesse
│   └─ POST /runs/{run_id}/zones/select → registra seleção
│
├─ Etapa 3a: Detalha zonas selecionadas
│   └─ POST /runs/{run_id}/zones/{uid}/detail (para cada zona)
│       → Coleta ruas (Mapbox), POIs (Mapbox), transporte (local)
│
├─ Etapa 3b: Coleta imóveis
│   ├─ GET /runs/{run_id}/zones/{uid}/streets → lista de ruas
│   └─ POST /runs/{run_id}/zones/{uid}/listings → scraping por rua
│       → Playwright abre QuintoAndar/VivaReal, intercepta dados
│
├─ Etapa 3c: Finaliza e ranqueia
│   └─ POST /runs/{run_id}/finalize
│       → Score por imóvel, filtros de qualidade, exports
│
└─ Resultado final
    ├─ GET /runs/{run_id}/final/listings      → GeoJSON de imóveis
    ├─ GET /runs/{run_id}/final/listings.csv  → CSV
    └─ GET /runs/{run_id}/final/listings.json → JSON rankeado
```

---

## 16. Dependências Python

### Produção (`requirements.txt`)

| Pacote | Versão mínima | Uso |
|--------|--------------|-----|
| `fastapi` | ≥0.111 | Framework web |
| `uvicorn[standard]` | ≥0.30 | ASGI server |
| `pydantic` | ≥2.7 | Schemas/validação |
| `requests` | ≥2.32 | HTTP (scripts) |
| `python-dotenv` | ≥1.0 | Variáveis de ambiente |
| `PyYAML` | ≥6.0 | `platforms.yaml` |
| `numpy` | ≥1.26 | Cálculos numéricos |
| `pandas` | ≥2.2 | Manipulação de dados |
| `openpyxl` | ≥3.1 | Leitura de Excel |
| `pyarrow` | ≥16.0 | Serialização eficiente |
| `networkx` | ≥3.0 | Grafos de rota |
| `shapely` | ≥2.0 | Geometrias geoespaciais |
| `pyproj` | ≥3.6 | Reprojeção de coordenadas |
| `fiona` | ≥1.9 | Leitura de GeoPackage |
| `geopandas` | ≥0.14 | DataFrames geoespaciais |
| `playwright` | ==1.50.0 | Automação de navegador |
| `pyshp` | ≥2.3 | Shapefiles |
| `Unidecode` | ≥1.3 | Normalização de texto |
| `orjson` | ≥3.10 | JSON rápido |
| `rapidfuzz` | ≥3.9 | Fuzzy matching |
| `tqdm` | ≥4.66 | Barras de progresso |

### Desenvolvimento (`pyproject.toml`)

| Pacote | Uso |
|--------|-----|
| `pytest` + `pytest-cov` | Testes e cobertura |
| `mypy` | Type checking |
| `black` | Formatação |
| `isort` | Ordenação de imports |
| `ruff` | Linting rápido |

### Frontend (`apps/web/package.json`)

| Pacote | Versão | Uso |
|--------|--------|-----|
| `react` + `react-dom` | 18.3.1 | UI framework |
| `maplibre-gl` | ^4.7 | Mapa interativo (tiles MapTiler) |
| `zod` | 3.24.1 | Validação de schemas |
| `lucide-react` | ^0.576.0 | Ícones |
| `tailwindcss` | 3.4.17 | CSS utilitário |
| `vite` | 5.4.11 | Build/Dev server |
| `typescript` | 5.7.3 | Tipagem estática |
| `vitest` | 3.0.7 | Testes unitários |

---

## 17. Requisitos Não-Funcionais (NFRs)

| NFR | Meta |
|-----|------|
| Taxa de sucesso E2E (smoke) | ≥ 95% com dados de teste fixos |
| `GET /status` p95 | < 300ms |
| `GET /zones` p95 (até 2.000 features) | < 800ms |
| Retries externos | Backoff + jitter, apenas em chamadas idempotentes |
| Idempotência | Reexecução do mesmo `run_id` não duplica artifacts |
| Observabilidade | Logs estruturados JSONL por etapa com `run_id` e `error_type` |
| Segurança | Nenhuma credencial em código, logs ou artifacts exportados |
| Concorrência | Etapas pesadas em `asyncio.to_thread` (não bloqueia event loop) |
| Persistência | 100% baseada em arquivo (sem banco de dados) |
