# Plano de Migração — Imóvel Ideal
## MVP Local → Produto Escalável com Monetização

**Versão do documento:** 1.0  
**Data:** 2026-03-04  
**Autor:** GitHub Copilot  
**Documentos de referência:** [PRD.md](PRD.md) · [BEST_PRACTICES.md](BEST_PRACTICES.md) · [BEST_PRACTICES_REMEDIATION_PLAN.md](BEST_PRACTICES_REMEDIATION_PLAN.md) · [DOCUMENTATION.md](DOCUMENTATION.md) · [ARQUITETURA-SISTEMA.md](ARQUITETURA-SISTEMA.md)  
**Skills utilizadas:** `develop-frontend` · `release-config-management` · `security-threat-checklist` · `ops-observability-runbook`

---

## Sumário

1. [Decisões Estratégicas](#1-decisões-estratégicas)
2. [Estado Atual — Diagnóstico](#2-estado-atual--diagnóstico)
3. [Arquitetura Final Alvo](#3-arquitetura-final-alvo)
4. [Progress Tracker Global](#4-progress-tracker-global)
5. [Fase 0 — Baseline e Infraestrutura de Testes](#5-fase-0--baseline-e-infraestrutura-de-testes)
6. [Fase 1 — Hardening e Organização do Backend](#6-fase-1--hardening-e-organização-do-backend)
7. [Fase 2 — Banco de Dados SQLite + Camada de Persistência](#7-fase-2--banco-de-dados-sqlite--camada-de-persistência)
8. [Fase 3 — Integração Stripe Pix + Gate de Pagamento](#8-fase-3--integração-stripe-pix--gate-de-pagamento)
9. [Fase 4 — Decomposição do Frontend](#9-fase-4--decomposição-do-frontend)
10. [Fase 5 — UX/UI Melhorias](#10-fase-5--uxui-melhorias)
11. [Fase 6 — Geração de PDF e Entrega do Relatório](#11-fase-6--geração-de-pdf-e-entrega-do-relatório)
12. [Fase 7 — Observabilidade, Deploy e Hardening Final](#12-fase-7--observabilidade-deploy-e-hardening-final)
13. [Fase 8 — Suíte E2E e Automação de Non-Regression](#13-fase-8--suíte-e2e-e-automação-de-non-regression)
14. [Invariantes de Dados](#14-invariantes-de-dados)
15. [Critérios de Rollback](#15-critérios-de-rollback)
16. [Glossário de Artefatos](#16-glossário-de-artefatos)

---

## 1. Decisões Estratégicas

| Dimensão | Decisão | Justificativa |
|---|---|---|
| **Abordagem** | Incremental — manter Python/FastAPI | Preserva lógica geoespacial complexa (`geopandas`, `pyproj`, `shapely`, `cods_ok/`). Menor risco de regressão. Rewrite total seria inviável no horizonte de 1–2 meses. |
| **Horizonte** | Médio prazo — 1–2 meses para produção | Qualidade sólida antes de abrir para usuários. |
| **Banco de dados** | SQLite como passo intermediário | Elimina complexidade de Postgres agora. `SQLAlchemy` async garante migração futura sem mudança de código de serviço. |
| **Monetização inicial** | Pagamento único por relatório (Stripe Pix, R$19–29) | Phase 1 da visão. Menor complexidade de billing. Entrega valor imediato. |
| **Frontend** | Decomposição incremental do `App.tsx` monolítico | Nunca mais de 300 linhas por componente. Zustand para estado global. |
| **PDF** | WeasyPrint (Python-native) | Evita segundo runtime Node.js/Puppeteer no container `api` que já carrega Playwright. |
| **Scripts geoespaciais** | `cods_ok/` preservados integralmente | Não alterar lógica de negócio comprovada. Melhorar apenas a interface (adapters, timeouts, error handling). |

---

## 2. Estado Atual — Diagnóstico

### 2.1 Forças

| Item | Localização | Observação |
|---|---|---|
| Pipeline por estágios com logging estruturado | [app/runner.py](app/runner.py) · `runs/<id>/logs/events.jsonl` | `asyncio.to_thread` evita bloqueio do event loop |
| Contratos Pydantic no backend | [app/schemas.py](app/schemas.py) | Todos os 12 schemas documentados |
| Contratos Zod no frontend | [ui/src/api/schemas.ts](ui/src/api/schemas.ts) | `safeParse` em todas as respostas |
| Cliente HTTP centralizado | [ui/src/api/client.ts](ui/src/api/client.ts) | `ApiError` com `recoverable`, `apiActionHint()` |
| Plano de testes existente | [TEST_PLAN.md](TEST_PLAN.md) | Cobertura E2E com datasets A/B/C |
| Smoke E2E funcionando | `scripts/e2e_smoke_dataset_a.ps1` | `FINAL_COUNT=413` validado em 2026-02-20 |

### 2.2 Dívidas Técnicas (por prioridade)

| Prioridade | Problema | Localização | Impacto |
|---|---|---|---|
| 🔴 P0 | Monolito `App.tsx` com 3.276 linhas | [ui/src/App.tsx](ui/src/App.tsx) | Impossível testar, debugar ou evoluir UX |
| 🔴 P0 | Business logic incrustada em `main.py` (100+ linhas no endpoint `zone_detail`) | [app/main.py](app/main.py#L160) | Viola ownership; impede testes unitários do core |
| 🔴 P0 | Sem proteção de path traversal em `run_id` | [app/store.py](app/store.py#L16) | `run_id = "../../etc"` escapa do `runs/` |
| 🔴 P0 | `listings_count` retorna contagem de arquivos, não de itens | [app/main.py](app/main.py#L318) | Dado exibido na UI está errado |
| 🔴 P0 | Nenhum timeout nos adapters (`subprocess.run` pode pendurar indefinidamente) | [adapters/](adapters/) | Pipeline pode travar sem recuperação |
| 🟡 P1 | Sem `app/config.py` — env vars lidas ad-hoc via `os.getenv()` | [app/main.py](app/main.py#L37) | Config drift entre ciclos de deploy |
| 🟡 P1 | `pyproject.toml` diverge de `requirements.txt` (9 deps vs 20+) | [pyproject.toml](pyproject.toml) | Build não-reprodutível; `pyproject.toml` é dead code |
| 🟡 P1 | `has_street_data/poi_data/transport_data` tipadoss como `z.unknown()` no frontend | [ui/src/api/schemas.ts](ui/src/api/schemas.ts) | Mismatch silencioso de tipos |
| 🟡 P1 | Arquivos mortos: `App.jsx`, `main.jsx` | `ui/src/` | Confusão sobre qual arquivo é ativo |
| 🟡 P1 | `_load_json` duplicado em `core/zone_ops.py` e `core/listings_ops.py` | [core/zone_ops.py](core/zone_ops.py) · [core/listings_ops.py](core/listings_ops.py) | Violação DRY; futura divergência |
| 🟡 P1 | `data_cache` hardcoded em `zone_ops.py` (`Path("data_cache")`) ignorando param | [core/zone_ops.py](core/zone_ops.py) | Cache dir inconsistente com runner |
| 🟡 P1 | `segurancaRegiao.py` carregado via `importlib` a cada chamada | [core/public_safety_ops.py](core/public_safety_ops.py) | Re-execução desnecessária; sem cache de módulo |
| 🟢 P2 | Magic numbers no score (`price_ref=5000`, `w_price=0.5` etc.) sem validação | [core/listings_ops.py](core/listings_ops.py) | Score pode dividir por zero se refs forem 0 |
| 🟢 P2 | Clustering O(n²) em `consolidate.py` | [core/consolidate.py](core/consolidate.py) | Degrada com muitas zonas |
| 🟢 P2 | Sem middleware de observabilidade (request_id, latência por endpoint) | [app/main.py](app/main.py) | Impossível rastrear erros em produção |

### 2.3 Fluxo de Dados E2E Atual (simplificado)

```
POST /runs
  └─► RunStore.create_run() → runs/<run_id>/{status.json, input.json, logs/}
      └─► asyncio.create_task(runner.run_pipeline)
            ├─ [validate] → lê input.json
            ├─ [public_safety] opt → cods_ok/segurancaRegiao.py via importlib
            ├─ [zones_by_ref] → subprocess: candidate_zones_from_cache_v10_fixed2.py
            │     └─► data_cache/gtfs/*.txt + geosampa/*.gpkg
            ├─ [zones_enrich] → subprocess: zone_enrich_green_flood_v8_tiled_groups_fixed.py
            │     └─► data_cache/geosampa/ + cache/green_tiles_v3/
            └─ [zones_consolidate] → core/consolidate.py (centroid clustering UTM-31983)
                  └─► runs/<run_id>/zones/consolidated/zones_consolidated.geojson

POST /runs/{id}/zones/{uid}/detail
  ├─ subprocess: encontrarRuasRaio.py (Mapbox Tilequery) → streets.json
  ├─ subprocess: pois_categoria_raio.py (Mapbox Search Box) → pois.json
  ├─ importlib: segurancaRegiao.py → public_safety.json
  └─ leitura: data_cache/gtfs/stops.txt + geosampa/*.gpkg → transport.json

POST /runs/{id}/zones/{uid}/listings
  └─ subprocess: realestate_meta_search.py all (Playwright)
       ├─ quintoAndar.py, vivaReal.py, zapImoveis.py
       └─► compiled_listings.json por rua

POST /runs/{id}/finalize
  └─ core/listings_ops.finalize_run()
       ├─ filtra listings (endereço válido + estado + coords)
       ├─ score_listing_v1 (haversine POI + transporte)
       └─► listings_final.{json,csv,geojson} + zones_final.geojson
```

---

## 3. Arquitetura Final Alvo

### 3.1 Estrutura de Diretórios (Backend)

```
principal/
├── app/
│   ├── main.py                  ← rotas HTTP apenas (~150 linhas); sem business logic
│   ├── config.py                ← NEW: Pydantic BaseSettings, validação na startup
│   ├── database.py              ← NEW: SQLAlchemy async engine, get_db()
│   ├── models.py                ← NEW: tabelas sessions, reports, payments
│   ├── runner.py                ← inalterado (pipeline stages)
│   ├── schemas.py               ← manter + adicionar schemas de report/payment
│   ├── store.py                 ← hardening: path-traversal check + write atômico
│   ├── services/
│   │   ├── __init__.py
│   │   ├── runs_service.py      ← NEW: create_run, dispatch pipeline
│   │   ├── zones_service.py     ← NEW: zone_detail, select, streets (extraído de main.py)
│   │   ├── listings_service.py  ← NEW: scraping + finalize
│   │   ├── transport_service.py ← NEW: rotas + stops
│   │   ├── report_service.py    ← NEW: CRUD de reports + sessions
│   │   └── payment_service.py   ← NEW: Stripe Payment Intent + webhook
│   ├── templates/
│   │   └── report.html          ← NEW: template Jinja2 para PDF
│   └── utils/
│       ├── __init__.py
│       ├── json_io.py           ← NEW: _load_json, safe_write_json atômico
│       └── logging.py           ← NEW: EventLogger(run_id) wrapper
│
├── core/                        ← regras de negócio puras (inalteradas funcionalmente)
│   ├── consolidate.py
│   ├── listings_ops.py          ← fix: usar app.utils.json_io; fix data_cache path
│   ├── public_safety_ops.py     ← fix: cache de módulo importlib
│   └── zone_ops.py              ← fix: usar app.utils.json_io; fix data_cache path
│
├── adapters/                    ← apenas integração subprocess
│   ├── candidate_zones_adapter.py  ← fix: timeout=300, TimeoutExpired categorizado
│   ├── zone_enrich_adapter.py      ← fix: timeout=300, TimeoutExpired categorizado
│   ├── listings_adapter.py         ← fix: timeout=600, TimeoutExpired categorizado
│   ├── streets_adapter.py          ← fix: timeout=120, TimeoutExpired categorizado
│   └── pois_adapter.py             ← fix: timeout=120, TimeoutExpired categorizado
│
├── cods_ok/                     ← NÃO ALTERAR (scripts geoespaciais autônomos)
│
├── tests/
│   ├── fixtures/
│   │   ├── dataset_a_input.json     ← NEW: input fixo smoke rápido
│   │   ├── dataset_b_input.json     ← NEW: 2 refs com sobreposição
│   │   ├── dataset_c_input.json     ← NEW: 3 refs, volume máximo
│   │   └── baseline_A_checksums.json ← NEW: checksums dos artifacts do baseline
│   ├── test_hello.py            ← existente
│   ├── test_runner_async.py     ← existente; expandir
│   ├── test_app_main.py         ← NEW: smoke de endpoints + validação 404
│   ├── test_invariants.py       ← NEW: 6 invariantes de dados pós-pipeline
│   ├── test_store.py            ← NEW: path-traversal, create_run, append_log
│   ├── test_config.py           ← NEW: validação de config na startup
│   ├── test_database.py         ← NEW: CRUD session/report/payment in-memory
│   ├── test_payment_service.py  ← NEW: mock Stripe, transições de estado
│   ├── test_pdf_service.py      ← NEW: geração de PDF com run_id de fixture
│   └── e2e/
│       └── test_full_flow.spec.ts ← NEW: Playwright E2E pelos 3 datasets
│
├── scripts/
│   ├── e2e_smoke_dataset_a.ps1  ← existente
│   ├── capture_baseline.ps1     ← NEW: congela artifacts + checksums
│   └── validate_invariants.ps1  ← NEW: roda test_invariants contra um run_id
│
├── docs/
│   └── runbook.md               ← NEW: troubleshooting, rollback, FAQ
│
├── data/
│   └── db.sqlite                ← NEW: banco SQLite (volume Docker, gitignored)
│
├── docker-compose.yml           ← update: volume data/, env vars completas
├── docker/api.Dockerfile        ← update: WeasyPrint deps
├── pyproject.toml               ← sync com requirements.txt (fonte única)
├── .env.example                 ← update: todas as variáveis documentadas
└── MIGRATION_PLAN.md            ← este documento
```

### 3.2 Estrutura de Diretórios (Frontend)

```
ui/src/
├── main.tsx
├── App.tsx                        ← orquestrador leve (~150 linhas)
├── styles.css
├── vite-env.d.ts
│
├── api/
│   ├── client.ts                  ← manter; fix: ReportSchema adicionado
│   └── schemas.ts                 ← fix: z.unknown() → z.boolean() + novos schemas
│
├── state/
│   ├── runState.ts                ← NEW: Zustand — runId, runStatus, zonesCollection
│   ├── mapState.ts                ← NEW: Zustand — viewport, layerVisibility
│   └── listingState.ts            ← NEW: Zustand — listings, focusedKey, sortMode
│
├── hooks/
│   ├── useRunPolling.ts           ← NEW: extrai setInterval/backoff de App.tsx
│   ├── useZoneDetail.ts           ← NEW: zone detail + listings loading flow
│   ├── useTransportStops.ts       ← NEW: debounced viewport fetch
│   └── useMapbox.ts               ← NEW: map init, source/layer management
│
├── features/
│   ├── reference/
│   │   ├── ReferencePanel.tsx     ← NEW: Step 1 — pontos + sliders + CTA
│   │   ├── ReferenceMarkers.tsx   ← NEW: marcadores no mapa
│   │   └── ReferenceConfig.tsx    ← NEW: raio, tempo, modo
│   ├── zones/
│   │   ├── ZonesPanel.tsx         ← NEW: Step 2 — tabela de zonas
│   │   ├── ZoneCard.tsx           ← NEW: card individual com métricas
│   │   ├── ZoneDetailView.tsx     ← NEW: POIs, transporte, segurança
│   │   └── ZoneLayer.tsx          ← NEW: círculos no mapa
│   ├── listings/
│   │   ├── ListingsPanel.tsx      ← NEW: Step 3 — cards + filtros + sort
│   │   ├── ListingCard.tsx        ← NEW: card de imóvel
│   │   ├── ListingCompare.tsx     ← NEW: tabela de comparação
│   │   └── ListingLayer.tsx       ← NEW: pins no mapa
│   ├── map/
│   │   ├── MapContainer.tsx       ← NEW: wrapper Mapbox GL
│   │   └── LayerMenu.tsx          ← NEW: toggle de camadas
│   └── payment/
│       ├── CheckoutModal.tsx      ← NEW: QR Code Pix + countdown + polling
│       └── ReportStatus.tsx       ← NEW: barra de progresso do pipeline
│
├── components/
│   ├── Button.tsx                 ← NEW
│   ├── Card.tsx                   ← NEW
│   ├── Badge.tsx                  ← NEW
│   ├── ProgressBar.tsx            ← NEW
│   ├── Modal.tsx                  ← NEW (Radix Dialog)
│   └── Spinner.tsx                ← NEW
│
└── types/
    └── zod.d.ts                   ← existente
```

### 3.3 Fluxo com Monetização (Pós-Migração)

```
POST /reports  (NEW)
  ├─ cria/recupera session anônima (ip_hash, user_agent_hash)
  ├─ cria report (state=pending_payment)
  └─► Stripe Payment Intent (Pix) → {pix_qr_code, pix_expire_at, report_id}

[Usuário escaneia QR Code]

POST /webhooks/stripe  (NEW)
  ├─ valida assinatura Stripe
  ├─ payment_intent.succeeded → report.state = paid
  └─► asyncio.create_task(runner.run_pipeline(run_id))

GET /reports/{report_id}/status  (NEW — polling do frontend)
  ├─ pending_payment → exibe QR Code
  ├─ processing → exibe ProgressBar com stages
  ├─ done → exibe run_id, botão de download
  └─ failed → exibe mensagem de erro + contato

[Pipeline concluído]

GET /reports/{report_id}/download  (NEW)
  └─► serve report.pdf (gerado por WeasyPrint)
```

---

## 4. Progress Tracker Global

> **Legenda:** ⬜ Não iniciado · 🔄 Em andamento · ✅ Concluído · ❌ Bloqueado

| Fase | Nome | Status | Dependência | Critério de saída |
|---|---|---|---|---|
| **0** | Baseline e Infra de Testes | ⬜ | — | Smoke E2E verde; checksums congelados; `test_invariants.py` passa |
| **1** | Hardening e Organização do Backend | ⬜ | Fase 0 ✅ | `pytest tests/` verde; snapshot diff zero; sem segredos |
| **2** | SQLite + Camada de Persistência | ⬜ | Fase 1 ✅ | Pipeline E2E intacto; CRUD session/report verde |
| **3** | Stripe Pix + Gate de Pagamento | ⬜ | Fase 2 ✅ | Fluxo Stripe Test Mode funciona; modo dev sem Stripe funciona |
| **4** | Decomposição do Frontend | ⬜ | Fase 1 ✅ | `npm run test` verde; nenhum componente > 300 linhas; Zustand |
| **5** | UX/UI Melhorias | ⬜ | Fase 4 ✅ | Lighthouse a11y ≥ 80; estados loading/erro/vazio tratados |
| **6** | PDF e Entrega do Relatório | ⬜ | Fase 3 ✅ + Fase 5 ✅ | PDF gerado com dataset A; download funciona Chrome/Firefox |
| **7** | Observabilidade, Deploy e Hardening | ⬜ | Fase 6 ✅ | `docker compose up --build` clean; rate limiting ativo; runbook |
| **8** | Suíte E2E e Automação Non-Regression | ⬜ | Fase 7 ✅ | Playwright E2E A/B/C verde; contract tests verde; CI |

---

## 5. Fase 0 — Baseline e Infraestrutura de Testes

**Objetivo:** congelar o estado funcional atual. Nenhuma fase pode avançar sem este baseline aprovado.  
**Arquivos alterados:** `tests/`, `scripts/`, `tests/fixtures/`  
**Arquivos NÃO alterados:** toda lógica de negócio existente  

### 5.1 Passos de Execução

#### 5.1.1 — Congelar Baseline

- [ ] **P0.1** Executar smoke E2E completo com dataset A fixo dentro do Docker:
  ```powershell
  docker compose -p onde_morar_mvp up -d --build
  # aguardar healthcheck
  .\scripts\e2e_smoke_dataset_a.ps1
  ```
  Registrar o `run_id` retornado como `RUN_ID_BASELINE_A`.

- [ ] **P0.2** Verificar que o pipeline terminou em `state=success`:
  ```powershell
  $r = "RUN_ID_BASELINE_A"
  (Get-Content "runs/$r/status.json" -Raw | ConvertFrom-Json).state
  # expected: "success"
  ```

- [ ] **P0.3** Verificar contagem de imóveis finais (registrar o número como `BASELINE_A_FINAL_COUNT`):
  ```powershell
  (Get-Content "runs/$r/final/listings_final.json" -Raw | ConvertFrom-Json).Count
  ```

- [ ] **P0.4** Criar `tests/fixtures/` e os arquivos de input fixos:
  - `tests/fixtures/dataset_a_input.json` — 1 ref point (ponto de trabalho fixo), params padrão, `public_safety_enabled: true`
  - `tests/fixtures/dataset_b_input.json` — 2 ref points com sobreposição espacial intencional, para testar deduplicação de `zone_uid`
  - `tests/fixtures/dataset_c_input.json` — 3 ref points, `max_streets_per_zone: 5`, volume máximo para teste de stress controlado

- [ ] **P0.5** Criar `scripts/capture_baseline.ps1`:
  ```powershell
  # Roda pipeline com dataset_a_input.json, calcula checksums SHA256 de:
  #   runs/<id>/final/listings_final.json
  #   runs/<id>/final/listings_final.geojson
  #   runs/<id>/zones/consolidated/zones_consolidated.geojson
  # Salva em tests/fixtures/baseline_A_checksums.json com estrutura:
  # { "run_id": "...", "date": "...", "checksums": { "listings_final_json": "...", ... }, "counts": { "zones": N, "listings": N } }
  ```

- [ ] **P0.6** Executar o script e confirmar que `tests/fixtures/baseline_A_checksums.json` foi gerado.

#### 5.1.2 — Testes Novos

- [ ] **P0.7** Criar `tests/test_invariants.py` — valida as 6 invariantes após qualquer run:
  ```python
  # INV-1: zones_consolidated.geojson tem features não-vazia (quando baseline tem)
  # INV-2: todos zone_uid são únicos no GeoJSON de zonas
  # INV-3: listings_final.json contém apenas endereços com logradouro válido
  # INV-4: listings_final.geojson não contém items com coords inválidas (lat=0,lon=0)
  # INV-5: campo 'state' preenchido em todos os listings finais válidos
  # INV-6: listings_final.csv, listings_final.json e listings_final.geojson são parseáveis e têm mesma cardinalidade lógica
  ```

- [ ] **P0.8** Criar `tests/test_app_main.py` — smoke dos endpoints sem pipeline real:
  ```python
  # GET /health → 200, {"status": "ok"}
  # GET /health/ready → 200, {"status": "ready"}
  # GET /runs/nonexistent/status → 404
  # GET /runs/nonexistent/zones → 404
  # GET /runs/nonexistent/final/listings.json → 404
  # POST /runs com body inválido (sem reference_points) → 422
  # POST /runs com reference_points vazio ([]) → 422
  ```
  Usar `pytest-asyncio` + `httpx.AsyncClient(app=app, base_url="http://test")`.

- [ ] **P0.9** Expandir `tests/test_runner_async.py`:
  - Adicionar cenário com `public_safety_enabled: true` (mock de `build_public_safety_artifacts`)
  - Adicionar cenário com 2 reference points (mock de `run_candidate_zones` e `run_zone_enrich`)
  - Adicionar cenário de falha em `zones_by_ref` → assertar `state=failed`

- [ ] **P0.10** Corrigir **bug P0 crítico** — `listings_count` em [app/main.py](app/main.py):
  ```python
  # ANTES (linha ~318):
  return ListingsScrapeResponse(zone_uid=zone_uid, listings_count=len(listing_files))
  # DEPOIS:
  return ListingsScrapeResponse(zone_uid=zone_uid, listings_count=total_items)
  ```

- [ ] **P0.11** Confirmar que `tests/test_hello.py` ainda passa (`assert 1 + 1 == 2`).

### 5.2 Checklist de Validação da Fase 0

| Gate | Critério | Status |
|---|---|---|
| **GATE-A** | `pytest tests/` verde (0 falhas) | ⬜ |
| **GATE-A** | `npm run lint && npm run typecheck` verde no `ui/` | ⬜ |
| **GATE-B** | `test_invariants.py` passa com `RUN_ID_BASELINE_A` | ⬜ |
| **GATE-B** | `test_app_main.py` todos os cenários passam | ⬜ |
| **GATE-B** | `test_runner_async.py` expandido, todos passam | ⬜ |
| **GATE-D** | Smoke E2E Dataset A no Docker completa com `state=success` | ⬜ |
| **GATE-D** | `listings_final.json` conta ≥ `BASELINE_A_FINAL_COUNT` (ou documentar regressão aceitável) | ⬜ |
| **OUTRO** | `tests/fixtures/baseline_A_checksums.json` gerado e commitado | ⬜ |
| **OUTRO** | Bug `listings_count` corrigido e validado no frontend | ⬜ |

### 5.3 Critério de Saída da Fase 0

> ✅ Todos os gates acima marcados. Qualquer falha bloqueia avanço para Fase 1.

---

## 6. Fase 1 — Hardening e Organização do Backend

**Objetivo:** eliminar dívidas de segurança (P0), centralizar configuração, extrair business logic de `main.py`, criar utilitários compartilhados. **Zero breaking changes nos contratos de API.**  
**Arquivos alterados:** [app/main.py](app/main.py) · [app/store.py](app/store.py) · [app/schemas.py](app/schemas.py) · [core/zone_ops.py](core/zone_ops.py) · [core/listings_ops.py](core/listings_ops.py) · [core/public_safety_ops.py](core/public_safety_ops.py) · todos os `adapters/` · [ui/src/api/schemas.ts](ui/src/api/schemas.ts) · [pyproject.toml](pyproject.toml) · [requirements.txt](requirements.txt) · `.env.example`  
**Arquivos criados:** `app/config.py` · `app/services/` (4 módulos) · `app/utils/json_io.py` · `app/utils/logging.py` · `tests/test_store.py` · `tests/test_config.py`

### 6.1 Passos de Execução

#### Bloco A — Configuração Centralizada

- [ ] **P1.1** Adicionar `pydantic-settings>=2.2` ao [pyproject.toml](pyproject.toml) e [requirements.txt](requirements.txt).

- [ ] **P1.2** Criar `app/config.py`:
  ```python
  from pydantic_settings import BaseSettings, SettingsConfigDict
  from pathlib import Path
  from typing import List

  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", extra="ignore")

      runs_dir: str = "runs"
      data_cache_dir: str = "data_cache"
      cache_dir: str = "cache"
      cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
      mapbox_access_token: str = ""
      stripe_secret_key: str = ""
      stripe_webhook_secret: str = ""
      stripe_dev_mode: bool = False
      base_url: str = "http://localhost:8000"

      @property
      def cors_origins_list(self) -> List[str]:
          return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

  settings = Settings()
  ```

- [ ] **P1.3** Substituir todos `os.getenv()` em [app/main.py](app/main.py) e [core/zone_ops.py](core/zone_ops.py) por referências a `settings.*`.

- [ ] **P1.4** Criar `tests/test_config.py`:
  ```python
  # Testa que Settings() carrega valores default corretamente
  # Testa que cors_origins_list parseia string multi-origem
  # Testa que Settings() falha se variável obrigatória apontada como required estiver ausente
  ```

#### Bloco B — Hardening de Segurança

- [ ] **P1.5** Adicionar `_validate_run_id(run_id)` em [app/store.py](app/store.py):
  ```python
  import re

  _RUN_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]{5,50}$')

  def _validate_run_id(self, run_id: str) -> None:
      if not _RUN_ID_RE.match(run_id):
          raise ValueError(f"invalid run_id format: {run_id!r}")
  ```
  Chamar em todos os métodos públicos de `RunStore` que recebem `run_id`.

- [ ] **P1.6** Adicionar `_validate_zone_uid(zone_uid)` similar, validar em endpoints de `main.py`.

- [ ] **P1.7** Criar `tests/test_store.py`:
  ```python
  # path traversal: run_id="../../etc" → ValueError
  # run_id com "/" → ValueError
  # run_id válido "20260304_abc12345" → OK
  # create_run → cria diretório e status.json
  # append_log → escreve linha JSONL válida
  ```

#### Bloco C — Utilitários Compartilhados

- [ ] **P1.8** Criar `app/utils/__init__.py` (vazio).

- [ ] **P1.9** Criar `app/utils/json_io.py`:
  ```python
  import json
  import os
  from pathlib import Path
  from typing import Any, Dict

  def load_json(path: Path) -> Dict[str, Any]:
      """Lê JSON de arquivo. Lança FileNotFoundError ou json.JSONDecodeError explicitamente."""
      return json.loads(path.read_text(encoding="utf-8"))

  def safe_write_json(path: Path, data: Any, indent: int = 2) -> None:
      """Escrita atômica: escreve em .tmp e faz rename. Evita arquivo parcialmente escrito."""
      path.parent.mkdir(parents=True, exist_ok=True)
      tmp = path.with_suffix(".tmp")
      tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
      os.replace(tmp, path)
  ```

- [ ] **P1.10** Criar `app/utils/logging.py`:
  ```python
  from app.store import RunStore

  class EventLogger:
      def __init__(self, store: RunStore, run_id: str) -> None:
          self._store = store
          self._run_id = run_id

      def info(self, stage: str, message: str, **extra) -> None:
          self._store.append_log(self._run_id, "info", stage, message, **extra)

      def warning(self, stage: str, message: str, **extra) -> None:
          self._store.append_log(self._run_id, "warning", stage, message, **extra)

      def error(self, stage: str, message: str, **extra) -> None:
          self._store.append_log(self._run_id, "error", stage, message, **extra)
  ```

- [ ] **P1.11** Substituir `_load_json` em [core/zone_ops.py](core/zone_ops.py) e [core/listings_ops.py](core/listings_ops.py) por `from app.utils.json_io import load_json`.

- [ ] **P1.12** Corrigir hardcode `Path("data_cache")` em [core/zone_ops.py](core/zone_ops.py) — substituir por `Path(settings.data_cache_dir)`.

#### Bloco D — Cache de Módulo Public Safety

- [ ] **P1.13** Em [core/public_safety_ops.py](core/public_safety_ops.py), converter `_load_public_safety_module()` para usar `@functools.lru_cache(maxsize=1)`:
  ```python
  import functools

  @functools.lru_cache(maxsize=1)
  def _load_public_safety_module():
      # importlib.util.spec_from_file_location(...) — mesmo código atual
      ...
  ```
  O módulo será carregado apenas uma vez por processo.

#### Bloco E — Hardening dos Adapters (Timeout + Error Categorization)

- [ ] **P1.14** Em cada adapter, adicionar `timeout` parametrizável ao `subprocess.run`:

  | Adapter | Timeout padrão |
  |---|---|
  | `candidate_zones_adapter.py` | 300s |
  | `zone_enrich_adapter.py` | 300s |
  | `listings_adapter.py` | 600s |
  | `streets_adapter.py` | 120s |
  | `pois_adapter.py` | 120s |

  ```python
  import subprocess

  try:
      result = subprocess.run(args, check=True, timeout=timeout_s, ...)
  except subprocess.TimeoutExpired as ex:
      raise RuntimeError(f"[{adapter_name}] timeout após {timeout_s}s") from ex
  except subprocess.CalledProcessError as ex:
      raise RuntimeError(f"[{adapter_name}] processo falhou (exit={ex.returncode})") from ex
  ```

#### Bloco F — Extração de Serviços de `main.py`

- [ ] **P1.15** Criar `app/services/__init__.py` (vazio).

- [ ] **P1.16** Criar `app/services/zones_service.py` — mover todo o bloco do endpoint `zone_detail` (linhas ~160–290 de [app/main.py](app/main.py)) para função `build_zone_detail_response(run_dir, run_id, zone_uid, store) -> ZoneDetailResponse`.

- [ ] **P1.17** Criar `app/services/listings_service.py` — mover lógica de `zone_listings` e `finalize` para funções dedicadas.

- [ ] **P1.18** Criar `app/services/transport_service.py` — mover lógica de `run_transport_routes` e `transport_stops`.

- [ ] **P1.19** Criar `app/services/runs_service.py` — encapsular `create_run + create_task pipeline`.

- [ ] **P1.20** Reescrever [app/main.py](app/main.py) para ter apenas rotas HTTP chamando os serviços. Alvo: ≤ 150 linhas.

#### Bloco G — Frontend Fix

- [ ] **P1.21** Em [ui/src/api/schemas.ts](ui/src/api/schemas.ts), substituir:
  ```typescript
  // ANTES:
  has_street_data: z.unknown(),
  has_poi_data: z.unknown(),
  has_transport_data: z.unknown(),
  // DEPOIS:
  has_street_data: z.boolean(),
  has_poi_data: z.boolean(),
  has_transport_data: z.boolean(),
  ```

- [ ] **P1.22** Remover arquivos mortos: `ui/src/App.jsx`, `ui/src/main.jsx`.

#### Bloco H — Dependências

- [ ] **P1.23** Sincronizar [pyproject.toml](pyproject.toml) com [requirements.txt](requirements.txt). Tornar `pyproject.toml` a fonte única com todas as 20+ dependências. Gerar `requirements.lock` via `pip-compile` (ou manter `requirements.txt` como lock explícito).

- [ ] **P1.24** Atualizar `.env.example` com todas as variáveis de `app/config.py` documentadas.

### 6.2 Checklist de Validação da Fase 1

| Gate | Critério | Status |
|---|---|---|
| **GATE-A** | `pytest tests/` verde (incluindo `test_store.py`, `test_config.py`) | ⬜ |
| **GATE-A** | `npm run lint && npm run typecheck` verde | ⬜ |
| **GATE-A** | Scan de segredos: nenhum token/key em código ou `.env.example` | ⬜ |
| **GATE-B** | `test_store.py` — path traversal e CRUD passam | ⬜ |
| **GATE-B** | `test_runner_async.py` expandido — todos os cenários passam | ⬜ |
| **GATE-C** | Snapshot diff de `POST /runs`, `GET /status`, `GET /zones`, `POST /detail`, `GET /final/listings.json` — zero campos removidos ou tipos alterados | ⬜ |
| **GATE-D** | Smoke E2E Dataset A no Docker completa com `state=success` | ⬜ |
| **GATE-D** | `test_invariants.py` passa com o run do smoke | ⬜ |
| **GATE-D** | `main.py` ≤ 150 linhas (verificar `wc -l app/main.py`) | ⬜ |
| **OUTRO** | Nenhum `os.getenv()` remanescente em `app/main.py` | ⬜ |
| **OUTRO** | `_load_json` duplicado removido de `core/` | ⬜ |

### 6.3 Critério de Saída da Fase 1

> ✅ Todos os gates acima marcados. `main.py` ≤ 150 linhas. Zero breaking changes de contrato.

---

## 7. Fase 2 — Banco de Dados SQLite + Camada de Persistência

**Objetivo:** introduzir SQLite para dados de produto (sessions anônimas, reports, payments). Os artifacts do pipeline geoespacial continuam em arquivo (imutável). A persistência é abstraída via SQLAlchemy para migração futura para Postgres sem mudança de serviço.  
**Arquivos criados:** `app/database.py` · `app/models.py` · `app/services/report_service.py` · `tests/test_database.py`  
**Arquivos alterados:** [app/main.py](app/main.py) · [docker-compose.yml](docker-compose.yml) · [docker/api.Dockerfile](docker/api.Dockerfile) · [pyproject.toml](pyproject.toml)

### 7.1 Passos de Execução

#### Bloco A — Dependências

- [ ] **P2.1** Adicionar ao [pyproject.toml](pyproject.toml) e [requirements.txt](requirements.txt):
  ```
  sqlalchemy>=2.0
  aiosqlite>=0.20
  ```

#### Bloco B — Engine e Base

- [ ] **P2.2** Criar `app/database.py`:
  ```python
  from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
  from sqlalchemy.orm import DeclarativeBase
  from app.config import settings

  DB_URL = f"sqlite+aiosqlite:///{settings.db_path}"
  engine = create_async_engine(DB_URL, echo=False)
  AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

  class Base(DeclarativeBase):
      pass

  async def get_db():
      async with AsyncSessionLocal() as session:
          yield session

  async def init_db():
      async with engine.begin() as conn:
          await conn.run_sync(Base.metadata.create_all)
  ```

- [ ] **P2.3** Adicionar `db_path: str = "data/db.sqlite"` ao `app/config.py` (Settings).

- [ ] **P2.4** Em [app/main.py](app/main.py), adicionar startup event:
  ```python
  from app.database import init_db

  @app.on_event("startup")
  async def startup():
      await init_db()
  ```

#### Bloco C — Modelos

- [ ] **P2.5** Criar `app/models.py`:

  ```python
  import uuid
  from datetime import datetime, timezone
  from enum import Enum as PyEnum
  from sqlalchemy import String, DateTime, Numeric, Enum, ForeignKey
  from sqlalchemy.orm import Mapped, mapped_column, relationship
  from app.database import Base

  class ReportState(PyEnum):
      pending_payment = "pending_payment"
      paid = "paid"
      processing = "processing"
      done = "done"
      failed = "failed"

  class Session(Base):
      __tablename__ = "sessions"
      session_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
      ip_hash: Mapped[str] = mapped_column(String(64), nullable=True)
      user_agent_hash: Mapped[str] = mapped_column(String(64), nullable=True)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
      reports: Mapped[list["Report"]] = relationship(back_populates="session")

  class Report(Base):
      __tablename__ = "reports"
      report_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
      run_id: Mapped[str] = mapped_column(String(50), nullable=True)
      session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.session_id"), nullable=True)
      state: Mapped[ReportState] = mapped_column(Enum(ReportState), default=ReportState.pending_payment)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
      expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
      session: Mapped["Session"] = relationship(back_populates="reports")
      payment: Mapped["Payment"] = relationship(back_populates="report", uselist=False)

  class Payment(Base):
      __tablename__ = "payments"
      payment_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
      report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.report_id"), unique=True)
      stripe_payment_intent_id: Mapped[str] = mapped_column(String(100), nullable=True)
      amount_brl: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
      status: Mapped[str] = mapped_column(String(30), default="created")
      pix_qr_code: Mapped[str] = mapped_column(String(2048), nullable=True)
      pix_expire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
      confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
      report: Mapped["Report"] = relationship(back_populates="payment")
  ```

#### Bloco D — Serviço de Reports

- [ ] **P2.6** Criar `app/services/report_service.py`:
  ```python
  # create_session(db, ip_hash, user_agent_hash) -> Session
  # create_report(db, session_id, run_id?) -> Report
  # get_report(db, report_id) -> Report | None
  # transition_report_state(db, report_id, new_state) -> Report
  # associate_run_id(db, report_id, run_id) -> Report
  ```

#### Bloco E — Infraestrutura

- [ ] **P2.7** Criar diretório `data/` na raiz (gitignored para `data/*.sqlite`).

- [ ] **P2.8** Atualizar [docker-compose.yml](docker-compose.yml) — adicionar volume `./data:/app/data` (rw) ao serviço `api`.

- [ ] **P2.9** Adicionar `data/` ao `.gitignore` (manter `data/.gitkeep`).

#### Bloco F — Testes

- [ ] **P2.10** Criar `tests/test_database.py`:
  ```python
  # Usa banco in-memory: "sqlite+aiosqlite:///:memory:"
  # test_create_session: cria session, verifica session_id UUID
  # test_create_report: cria report com session_id, verifica state=pending_payment
  # test_transition_state: pending_payment → paid → processing → done
  # test_transition_invalid: paid → pending_payment → deve falhar (estado inválido)
  # test_payment_created: associa payment a report, verifica FK
  ```

### 7.2 Checklist de Validação da Fase 2

| Gate | Critério | Status |
|---|---|---|
| **GATE-A** | `pytest tests/` verde | ⬜ |
| **GATE-A** | `test_database.py` todos os cenários passam | ⬜ |
| **GATE-B** | `report_service.py` — CRUD + transições de estado cobertas | ⬜ |
| **GATE-D** | Pipeline E2E Dataset A no Docker intacto — artifacts geoespaciais idênticos ao baseline (checksums iguais) | ⬜ |
| **GATE-D** | `data/db.sqlite` criado no startup do container | ⬜ |
| **OUTRO** | `data/` no `.gitignore`; `data/.gitkeep` commitado | ⬜ |

### 7.3 Critério de Saída da Fase 2

> ✅ Pipeline geoespacial intacto. SQLite inicializado. CRUD de sessions/reports/payments verde.

---

## 8. Fase 3 — Integração Stripe Pix + Gate de Pagamento

**Objetivo:** usuário só acessa o pipeline após pagamento confirmado via webhook Stripe. Modo dev (`STRIPE_DEV_MODE=true`) pula o pagamento para desenvolvimento local.  
**Arquivos criados:** `app/services/payment_service.py` · `tests/test_payment_service.py`  
**Arquivos alterados:** [app/main.py](app/main.py) · `app/schemas.py` · [app/config.py](app/config.py) · [app/runner.py](app/runner.py) · [docker-compose.yml](docker-compose.yml)

### 8.1 Passos de Execução

#### Bloco A — Dependências

- [ ] **P3.1** Adicionar ao [pyproject.toml](pyproject.toml) e [requirements.txt](requirements.txt):
  ```
  stripe>=10.0
  ```

#### Bloco B — Serviço de Pagamento

- [ ] **P3.2** Criar `app/services/payment_service.py`:

  ```python
  import stripe
  from app.config import settings

  stripe.api_key = settings.stripe_secret_key

  async def create_payment_intent(report_id: str, amount_brl: float) -> dict:
      """
      Cria Payment Intent com Pix como método.
      Retorna: {payment_intent_id, client_secret, pix_qr_code, pix_expire_at}
      """
      ...

  async def handle_stripe_webhook(payload: bytes, sig_header: str) -> dict:
      """
      Valida assinatura Stripe.
      Em payment_intent.succeeded → chama report_service.transition(report_id, paid)
      e dispara runner.run_pipeline(run_id).
      Retorna: {event_type, processed: bool}
      """
      ...
  ```

- [ ] **P3.3** Modo dev — em `create_payment_intent`, se `settings.stripe_dev_mode`:
  ```python
  if settings.stripe_dev_mode:
      # Simula pagamento imediato, retorna pix_qr_code mock
      return {"payment_intent_id": "dev_mock", "pix_qr_code": "DEV_QR", "pix_expire_at": None}
  ```

- [ ] **P3.4** Modo dev — em `POST /reports`, se `STRIPE_DEV_MODE=true`, após criar report:
  ```python
  # Transita imediatamente para paid e dispara pipeline
  # Útil para desenvolvimento/teste local sem Stripe real
  ```

#### Bloco C — Novos Endpoints

- [ ] **P3.5** Adicionar Pydantic schemas em [app/schemas.py](app/schemas.py):
  ```python
  class CreateReportRequest(BaseModel):
      reference_points: List[ReferencePoint]
      params: Dict[str, Any] = {}

  class CreateReportResponse(BaseModel):
      report_id: str
      pix_qr_code: Optional[str]
      pix_expire_at: Optional[str]
      amount_brl: float
      state: str  # "pending_payment" | "processing" (se dev_mode)

  class ReportStatusResponse(BaseModel):
      report_id: str
      state: str
      run_id: Optional[str]
      error_message: Optional[str]
  ```

- [ ] **P3.6** Adicionar em [app/main.py](app/main.py) (via `app/services/`):
  - `POST /reports` — cria session + report + payment intent → retorna `CreateReportResponse`
  - `GET /reports/{report_id}/status` → `ReportStatusResponse`
  - `POST /webhooks/stripe` — recebe webhook Stripe (sem auth Bearer, com assinatura Stripe)
  - `GET /reports/{report_id}/download` — serve `report.pdf` (implementado na Fase 6; retorna 404 placeholder aqui)

#### Bloco D — Atualização do Frontend (Checkout Flow)

- [ ] **P3.7** Adicionar ao [ui/src/api/client.ts](ui/src/api/client.ts):
  ```typescript
  export async function createReport(payload: CreateReportPayload): Promise<CreateReportResponse>
  export async function getReportStatus(reportId: string): Promise<ReportStatusResponse>
  ```

- [ ] **P3.8** Adicionar ao [ui/src/api/schemas.ts](ui/src/api/schemas.ts):
  ```typescript
  export const CreateReportResponseSchema = z.object({ ... })
  export const ReportStatusResponseSchema = z.object({ ... })
  ```

- [ ] **P3.9** Atualizar `App.tsx` — botão "Gerar Zonas Candidatas" agora chama `POST /reports` em vez de `POST /runs`. Se `state=pending_payment`, exibe QR Code. Se `state=processing`, exibe ProgressBar. Se `state=done`, carrega `run_id` e continua fluxo existente.  
  ⚠️ Esta é uma mudança de fluxo no frontend mas não altera os contratos geoespaciais. O Passo 2 e 3 do UI continuam idênticos.

#### Bloco E — Testes

- [ ] **P3.10** Criar `tests/test_payment_service.py`:
  ```python
  # Mock stripe.PaymentIntent.create, stripe.Webhook.construct_event
  # test_create_payment_intent_dev_mode: stripe_dev_mode=True → retorna mock sem chamar Stripe
  # test_create_payment_intent_real: verifica parâmetros enviados ao Stripe
  # test_webhook_payment_succeeded: evento succeeded → report.state=paid
  # test_webhook_invalid_signature: lança ValueError
  # test_webhook_unrelated_event: evento irrelevante → processed=False, sem efeito colateral
  ```

### 8.2 Checklist de Validação da Fase 3

| Gate | Critério | Status |
|---|---|---|
| **GATE-A** | `pytest tests/` verde | ⬜ |
| **GATE-A** | `test_payment_service.py` todos cenários passam | ⬜ |
| **GATE-B** | `POST /reports` retorna `pix_qr_code` em modo Stripe real e `DEV_QR` em dev mode | ⬜ |
| **GATE-B** | Webhook com assinatura inválida retorna 400 | ⬜ |
| **GATE-C** | Contratos `POST /runs`, `GET /zones`, `GET /final/listings.json` inalterados (snapshot diff zero) | ⬜ |
| **GATE-D** | Com `STRIPE_DEV_MODE=true`: pipeline inicia imediatamente após `POST /reports` | ⬜ |
| **GATE-D** | Com `STRIPE_DEV_MODE=true`: smoke E2E Dataset A completa com `state=success` | ⬜ |
| **OUTRO** | `STRIPE_SECRET_KEY` e `STRIPE_WEBHOOK_SECRET` não aparecem em logs ou código | ⬜ |

### 8.3 Critério de Saída da Fase 3

> ✅ Fluxo de pagamento funcional em modo dev. Webhook com assinatura Stripe validada. Pipeline E2E intacto.

---

## 9. Fase 4 — Decomposição do Frontend

**Objetivo:** transformar [ui/src/App.tsx](ui/src/App.tsx) (3.276 linhas) em arquitetura componentizada. **Zero mudança de comportamento visível ou contratos de API.** Cada componente ≤ 300 linhas.  
**Arquivos criados:** toda estrutura `state/`, `hooks/`, `features/`, `components/` descrita na seção 3.2  
**Arquivos alterados:** [ui/src/App.tsx](ui/src/App.tsx) · [ui/src/api/client.ts](ui/src/api/client.ts)  
**Dependências novas:** `zustand>=4.0` · `@radix-ui/react-dialog` · `@radix-ui/react-slider`

### 9.1 Passos de Execução

#### Sprint 4.1 — Estado Global (Zustand)

- [ ] **P4.1** Instalar Zustand:
  ```bash
  cd ui && npm install zustand @radix-ui/react-dialog @radix-ui/react-slider
  ```

- [ ] **P4.2** Criar `ui/src/state/runState.ts`:
  ```typescript
  // Zustand store com slices:
  // - runId: string | null
  // - runStatus: RunStatus | null
  // - reportId: string | null
  // - isCreatingReport: boolean
  // - isPolling: boolean
  // - activeStep: 1 | 2 | 3
  // - zonesCollection: ZoneFeature[]
  // - selectedZoneUid: string | null
  // - zoneDetailData: ZoneDetailResponse | null
  // Actions: setRunId, setStatus, startPolling, stopPolling, selectZone
  ```

- [ ] **P4.3** Criar `ui/src/state/mapState.ts`:
  ```typescript
  // layerVisibility: { routes: bool, train: bool, busStops: bool, zones: bool, flood: bool, green: bool, pois: bool }
  // viewport: { lon, lat, zoom }
  // isMapReady: boolean
  // Actions: toggleLayer, setViewport, setMapReady
  ```

- [ ] **P4.4** Criar `ui/src/state/listingState.ts`:
  ```typescript
  // finalListings: ListingFeature[]
  // listingsWithoutCoords: any[]
  // focusedListingKey: string | null
  // selectedListingKeys: string[]
  // listingSortMode: 'score' | 'price_asc' | 'price_desc' | 'area'
  // Actions: setListings, focusListing, toggleSelectListing, setSortMode
  ```

- [ ] **P4.5** Criar `ui/src/hooks/useRunPolling.ts`:
  ```typescript
  // Extrai setInterval/clearInterval + backoff exponencial + jitter de App.tsx
  // Interface: useRunPolling(runId: string | null, onSuccess: () => void, onFailed: () => void)
  // Retorna: { isPolling, currentStatus }
  ```

- [ ] **P4.6** Criar `ui/src/hooks/useTransportStops.ts`:
  ```typescript
  // Extrai lógica de debounce + fetch por viewport de App.tsx
  // Interface: useTransportStops(mapRef, isMapReady, layerVisible)
  ```

- [ ] **P4.7** Criar `ui/src/hooks/useMapbox.ts`:
  ```typescript
  // Encapsula: map.addSource, map.addLayer, map.setData, map.resize
  // Interface: useMapbox(containerRef) → { mapRef, isReady, error }
  ```

#### Sprint 4.2 — Componentes Compartilhados

- [ ] **P4.8** Criar `ui/src/components/Button.tsx` — variantes: `primary`, `secondary`, `danger`. Props: `loading`, `disabled`, `onClick`.

- [ ] **P4.9** Criar `ui/src/components/Card.tsx` — container padrão com sombra e padding.

- [ ] **P4.10** Criar `ui/src/components/Badge.tsx` — variantes: `green`, `yellow`, `red`, `gray`.

- [ ] **P4.11** Criar `ui/src/components/ProgressBar.tsx` — barra animada com label de stage e ETA.

- [ ] **P4.12** Criar `ui/src/components/Modal.tsx` — wrapper `@radix-ui/react-dialog` com foco gerenciado e `Esc` para fechar.

- [ ] **P4.13** Criar `ui/src/components/Spinner.tsx` — spinner CSS animado reutilizável.

#### Sprint 4.3 — Feature: Referências

- [ ] **P4.14** Criar `ui/src/features/reference/ReferencePanel.tsx` — Step 1: campo de pontos, toggle alugar/comprar, sliders de raio e tempo, CTA. Toda lógica extraída de `App.tsx`. ≤ 250 linhas.

- [ ] **P4.15** Criar `ui/src/features/reference/ReferenceMarkers.tsx` — gerencia marcadores Mapbox para ponto principal e interesses. Usa `mapRef` via context/prop.

- [ ] **P4.16** Criar `ui/src/features/reference/ReferenceConfig.tsx` — sliders de `zoneRadiusM`, `maxTravelTimeMin`, `seedBusSearchMaxDistM`, `seedRailSearchMaxDistM` usando `@radix-ui/react-slider`.

- [ ] **P4.17** Teste: `ReferencePanel` renderiza, sliders atualizam estado, CTA dispara `createReport`.

#### Sprint 4.4 — Feature: Zonas

- [ ] **P4.18** Criar `ui/src/features/zones/ZoneCard.tsx` — card com métricas de zona (verde, inundação, transporte, POIs).

- [ ] **P4.19** Criar `ui/src/features/zones/ZoneDetailView.tsx` — detalhe expandido com listas de POIs, transporte e segurança pública.

- [ ] **P4.20** Criar `ui/src/features/zones/ZonesPanel.tsx` — tabela de zonas, seleção, filtros, CTA "Detalhar zona". ≤ 300 linhas.

- [ ] **P4.21** Criar `ui/src/features/zones/ZoneLayer.tsx` — gerencia a layer de círculos no mapa (addSource/setData).

- [ ] **P4.22** Teste: `ZonesPanel` renderiza lista vazia, lista com 3 zonas, seleção por checkbox.

#### Sprint 4.5 — Feature: Listings

- [ ] **P4.23** Criar `ui/src/features/listings/ListingCard.tsx` — card individual com preço, área, tipo, endereço, bloco de explicabilidade, link de abertura.

- [ ] **P4.24** Criar `ui/src/features/listings/ListingCompare.tsx` — tabela multi-select de comparação side-by-side.

- [ ] **P4.25** Criar `ui/src/features/listings/ListingsPanel.tsx` — cards + filtro por rua + sort (score/preço/área). ≤ 300 linhas.

- [ ] **P4.26** Criar `ui/src/features/listings/ListingLayer.tsx` — gerencia pins de imóveis no mapa com label de preço.

- [ ] **P4.27** Teste: `ListingsPanel` renderiza vazio, com listings, sort por preço funciona.

#### Sprint 4.6 — Feature: Mapa e Pagamento

- [ ] **P4.28** Criar `ui/src/features/map/MapContainer.tsx` — wrapper Mapbox GL JS, expõe `mapRef` via `useMapbox`.

- [ ] **P4.29** Criar `ui/src/features/map/LayerMenu.tsx` — toggle de 7 camadas, mini checkbox list.

- [ ] **P4.30** Criar `ui/src/features/payment/CheckoutModal.tsx` — exibe QR Code Pix, countdown (15 min), polling `/reports/{id}/status`, transição para ProgressBar quando `state=processing`.

- [ ] **P4.31** Criar `ui/src/features/payment/ReportStatus.tsx` — ProgressBar de stages com ETA por etapa (usa `stages[]` do `RunStatusResponse`).

#### Sprint 4.7 — Montagem Final

- [ ] **P4.32** Reescrever `ui/src/App.tsx` como orquestrador leve:
  - Inicializa Zustand stores
  - Renderiza `<MapContainer>` + `<ReferencePanel | ZonesPanel | ListingsPanel>` baseado em `activeStep`
  - `<CheckoutModal>` via modal overlay
  - `<LayerMenu>` no canto
  - `<ReportStatus>` no overlay de progresso
  - **Alvo: ≤ 150 linhas**

- [ ] **P4.33** Confirmar que nenhum `useRef`, `useState` ou `useEffect` ficou em `App.tsx` para state de domínio (permitido apenas para `mapContainerRef`).

### 9.2 Checklist de Validação da Fase 4

| Gate | Critério | Status |
|---|---|---|
| **GATE-A** | `npm run lint && npm run typecheck` verde | ⬜ |
| **GATE-A** | Nenhum componente > 300 linhas | ⬜ |
| **GATE-B** | `npm run test` verde — testes de `ReferencePanel`, `ZonesPanel`, `ListingsPanel` | ⬜ |
| **GATE-B** | `App.tsx` ≤ 150 linhas | ⬜ |
| **GATE-C** | Todos os contratos de API consumidos via Zod continuam validando sem erro | ⬜ |
| **GATE-D** | Fluxo completo funciona manualmente no browser (Steps 1→2→3→export) | ⬜ |
| **GATE-D** | `STRIPE_DEV_MODE=true`: CheckoutModal aparece, transita para ProgressBar e conclui | ⬜ |
| **OUTRO** | Zustand stores sem `useState` em App.tsx para estado de domínio | ⬜ |
| **OUTRO** | Radix Slider substitui `<input type="range">` em ReferenceConfig | ⬜ |

### 9.3 Critério de Saída da Fase 4

> ✅ `App.tsx` ≤ 150 linhas. Nenhum componente > 300 linhas. UI funciona identicamente ao estado pré-migração.

---

## 10. Fase 5 — UX/UI Melhorias

**Objetivo:** interface agradável, responsiva, com estados de loading/erro/vazio tratados com feedback acionável ao usuário.  
**Arquivos alterados:** features/*, components/*, `styles.css`

### 10.1 Passos de Execução

- [ ] **P5.1** **Loading states granulares** — `ProgressBar` animada atualizada por stage do runner:

  | Stage name | Label exibido ao usuário |
  |---|---|
  | `validate` | Verificando parâmetros... |
  | `public_safety` | Coletando dados de segurança... |
  | `zones_by_ref` | Calculando zonas de deslocamento... |
  | `zones_enrich` | Enriquecendo zonas com verde e alagamento... |
  | `zones_consolidate` | Consolidando zonas... |

- [ ] **P5.2** **Error recovery UI** — em cada estado de erro da API, exibir `apiActionHint(error)` (já existe em `client.ts` mas não é renderizado) com botão "Tentar novamente" quando `error.recoverable=true`.

- [ ] **P5.3** **Empty states** com ilustração + CTA:
  - Nenhuma zona encontrada → "Tente aumentar o raio ou o tempo máximo de deslocamento."
  - Nenhum imóvel coletado → "Tente selecionar mais ruas ou aumentar o raio."
  - Nenhuma rua na zona → "Esta zona não possui ruas mapeadas. Selecione outra."

- [ ] **P5.4** **Responsividade mobile** (≤768px):
  - Painel lateral vira bottom sheet deslizável.
  - Mapa ocupa 100vw/100vh no Step 1.
  - Botões com altura mínima de 44px (touch target).

- [ ] **P5.5** **Checkout UX**:
  - Countdown no `CheckoutModal` em formato `MM:SS` (PIX expira em 15min).
  - Após pagamento confirmado, fechar modal automaticamente e exibir ProgressBar.
  - Mensagem de suporte ao expirar o QR Code.

- [ ] **P5.6** **Export UX** — botões de download com ícones (`FileJson`, `FileSpreadsheet`, `Map`) e feedback de toast "Arquivo baixado".

- [ ] **P5.7** **Acessibilidade mínima**:
  - Todos os ícones SVG com `aria-label` ou `aria-hidden`.
  - Modais com `role="dialog"` e `aria-labelledby` (garantido pelo Radix Dialog).
  - Controles de mapa com `aria-label` descritivo.
  - Foco visível global já implementado (FE5) — verificar regressão.

- [ ] **P5.8** Rodar Lighthouse no browser com `--headless`:
  - Performance ≥ 70
  - Accessibility ≥ 80
  - Documentar resultado como referência.

### 10.2 Checklist de Validação da Fase 5

| Gate | Critério | Status |
|---|---|---|
| **GATE-A** | `npm run lint && npm run typecheck` verde | ⬜ |
| **GATE-B** | Testes `@testing-library` para estados loading/erro/vazio em `ZonesPanel` e `ListingsPanel` | ⬜ |
| **GATE-B** | Teste: countdown do PIX exibe e decrementa | ⬜ |
| **GATE-C** | Nenhuma regressão em contratos de API | ⬜ |
| **GATE-D** | Fluxo completo funciona no mobile (viewport 375px) sem elementos sobrepostos | ⬜ |
| **GATE-D** | Lighthouse Accessibility ≥ 80 | ⬜ |
| **OUTRO** | `apiActionHint()` exibido no UI em caso de erro recuperável | ⬜ |

---

## 11. Fase 6 — Geração de PDF e Entrega do Relatório

**Objetivo:** produto entrega um relatório PDF como artefato de valor após pagamento. Backend gera PDF com Python-native (sem Puppeteer/Node adicional).  
**Arquivos criados:** `app/services/pdf_service.py` · `app/templates/report.html` · `app/templates/report_base.css` · `tests/test_pdf_service.py`  
**Arquivos alterados:** [app/main.py](app/main.py) · [docker/api.Dockerfile](docker/api.Dockerfile) · [pyproject.toml](pyproject.toml)

### 11.1 Passos de Execução

#### Bloco A — Dependências

- [ ] **P6.1** Adicionar ao [pyproject.toml](pyproject.toml) e [requirements.txt](requirements.txt):
  ```
  WeasyPrint>=62.0
  Jinja2>=3.1
  ```

- [ ] **P6.2** Atualizar [docker/api.Dockerfile](docker/api.Dockerfile) com dependências do sistema para WeasyPrint:
  ```dockerfile
  RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0 \
      libffi-dev shared-mime-info \
      && rm -rf /var/lib/apt/lists/*
  ```

#### Bloco B — Template HTML

- [ ] **P6.3** Criar `app/templates/report.html` (Jinja2):
  ```html
  <!DOCTYPE html>
  <html lang="pt-BR">
  <!-- Estrutura do relatório:
    - Capa: título "Relatório de Imóveis", ref points, data
    - Seção 1: Resumo das zonas selecionadas (nome, verde %, alagamento %, score transporte)
    - Seção 2: Top 10 imóveis rankeados (endereço, preço, área, score, zona, distância ao transporte)
    - Seção 3: Mapa estático (PNG via Mapbox Static API centrado no bbox das zonas)
    - Rodapé: gerado em <data> · Imóvel Ideal
  -->
  ```

- [ ] **P6.4** Criar `app/templates/report_base.css` — estilos para impressão/PDF (A4, margens, fontes sans-serif, tabelas com borders).

#### Bloco C — Serviço PDF

- [ ] **P6.5** Criar `app/services/pdf_service.py`:
  ```python
  from weasyprint import HTML
  from jinja2 import Environment, FileSystemLoader
  from pathlib import Path
  from app.utils.json_io import load_json
  from app.config import settings

  def _fetch_static_map(lon: float, lat: float, bbox) -> bytes:
      """Chama Mapbox Static API para gerar PNG de 600×400px. Retorna bytes."""
      ...

  def generate_report_pdf(run_id: str) -> Path:
      """
      Lê listings_final.json + zones_final.geojson + input.json.
      Renderiza template HTML → converte para PDF via WeasyPrint.
      Salva em runs/<run_id>/final/report.pdf.
      Retorna path do PDF.
      """
      run_dir = Path(settings.runs_dir) / run_id
      listings = load_json(run_dir / "final" / "listings_final.json")
      zones = load_json(run_dir / "zones" / "consolidated" / "zones_consolidated.geojson")
      input_data = load_json(run_dir / "input.json")

      env = Environment(loader=FileSystemLoader("app/templates"))
      template = env.get_template("report.html")
      html_str = template.render(
          run_id=run_id,
          reference_points=input_data.get("reference_points", []),
          zones=zones.get("features", [])[:5],
          listings=listings[:10],
          generated_at=datetime.now(timezone.utc).isoformat(),
      )
      pdf_path = run_dir / "final" / "report.pdf"
      HTML(string=html_str, base_url="app/templates/").write_pdf(str(pdf_path))
      return pdf_path
  ```

- [ ] **P6.6** Invocar `generate_report_pdf(run_id)` ao final do pipeline em [app/runner.py](app/runner.py), após `zones_consolidate` com sucesso. Falha no PDF é não-fatal (loga warning, não falha o run).

#### Bloco D — Endpoint de Download

- [ ] **P6.7** Ativar endpoint `GET /reports/{report_id}/download` em [app/main.py](app/main.py):
  ```python
  @app.get("/reports/{report_id}/download")
  async def download_report(report_id: str, db: AsyncSession = Depends(get_db)):
      report = await report_service.get_report(db, report_id)
      if report is None or report.state != ReportState.done:
          raise HTTPException(status_code=404, detail="report not ready")
      pdf_path = Path(settings.runs_dir) / report.run_id / "final" / "report.pdf"
      if not pdf_path.exists():
          raise HTTPException(status_code=404, detail="pdf not generated yet")
      return Response(
          content=pdf_path.read_bytes(),
          media_type="application/pdf",
          headers={"Content-Disposition": f'attachment; filename="relatorio_{report_id[:8]}.pdf"'}
      )
  ```

#### Bloco E — Frontend

- [ ] **P6.8** No `ui/src/features/payment/ReportStatus.tsx`, após `state=done`, exibir:
  - Botão **"Baixar Relatório PDF"** → chama `GET /reports/{report_id}/download`
  - Links de export JSON/CSV/GeoJSON (já existiam)

#### Bloco F — Testes

- [ ] **P6.9** Criar `tests/test_pdf_service.py`:
  ```python
  # Usa run_id do baseline A (fixtures já gerado na Fase 0)
  # test_generate_report_pdf: arquivo gerado existe, tamanho > 5KB
  # test_pdf_contains_listings: verifica que o HTML intermediário contém endereços do top 10
  # test_download_endpoint_not_ready: report.state=processing → 404
  # test_download_endpoint_ready: report.state=done, pdf existe → 200, content-type=application/pdf
  ```

### 11.2 Checklist de Validação da Fase 6

| Gate | Critério | Status |
|---|---|---|
| **GATE-A** | `pytest tests/` verde | ⬜ |
| **GATE-A** | `test_pdf_service.py` todos passam | ⬜ |
| **GATE-B** | PDF gerado com dataset A baseline — arquivo existe, size > 5KB | ⬜ |
| **GATE-B** | PDF abre em Chrome e Firefox sem erro | ⬜ |
| **GATE-D** | Pipeline E2E Dataset A conclui, PDF em `runs/<id>/final/report.pdf` | ⬜ |
| **GATE-D** | `GET /reports/{id}/download` retorna 200 com content-type `application/pdf` | ⬜ |
| **OUTRO** | `MAPBOX_ACCESS_TOKEN` não exposto no PDF ou runtime logs | ⬜ |

---

## 12. Fase 7 — Observabilidade, Deploy e Hardening Final

**Objetivo:** produto pronto para exposição a usuários reais. Rate limiting, healthcheck completo, runbook, Docker production-ready.  
**Arquivos alterados:** [app/main.py](app/main.py) · [docker-compose.yml](docker-compose.yml) · [docker/api.Dockerfile](docker/api.Dockerfile) · [README.md](README.md)  
**Arquivos criados:** `docs/runbook.md`

### 12.1 Passos de Execução

#### Bloco A — Middleware de Observabilidade

- [ ] **P7.1** Adicionar `slowapi>=0.1` ao [pyproject.toml](pyproject.toml).

- [ ] **P7.2** Adicionar middleware de `request_id` em [app/main.py](app/main.py):
  ```python
  import uuid
  from starlette.middleware.base import BaseHTTPMiddleware

  class RequestIdMiddleware(BaseHTTPMiddleware):
      async def dispatch(self, request, call_next):
          request_id = str(uuid.uuid4())[:8]
          response = await call_next(request)
          response.headers["X-Request-Id"] = request_id
          return response
  ```

- [ ] **P7.3** Adicionar log estruturado de requests em `events.jsonl` (se o request pertencer a um `run_id`).

- [ ] **P7.4** Adicionar rate limiting:
  ```python
  from slowapi import Limiter
  from slowapi.util import get_remote_address

  limiter = Limiter(key_func=get_remote_address)
  app.state.limiter = limiter

  @app.post("/reports")
  @limiter.limit("5/minute")
  async def create_report_endpoint(...):
      ...
  ```
  Endpoints excluídos: `POST /webhooks/stripe`, `GET /health`, `GET /health/ready`.

#### Bloco B — Healthcheck Completo

- [ ] **P7.5** Expandir `GET /health/ready` em [app/main.py](app/main.py):
  ```python
  @app.get("/health/ready")
  async def ready() -> dict:
      checks = {}
      # SQLite
      try:
          async with AsyncSessionLocal() as db:
              await db.execute(text("SELECT 1"))
          checks["db"] = "ok"
      except Exception as e:
          checks["db"] = f"error: {e}"
      # Caminhos críticos
      gtfs_ok = Path(settings.data_cache_dir, "gtfs").exists()
      geo_ok = Path(settings.data_cache_dir, "geosampa").exists()
      checks["data_gtfs"] = "ok" if gtfs_ok else "missing"
      checks["data_geosampa"] = "ok" if geo_ok else "missing"
      all_ok = all(v == "ok" for v in checks.values())
      return {"status": "ready" if all_ok else "degraded", "checks": checks}
  ```

#### Bloco C — Docker

- [ ] **P7.6** Atualizar [docker-compose.yml](docker-compose.yml):
  ```yaml
  services:
    api:
      volumes:
        - ./data_cache:/app/data_cache:ro
        - ./runs:/app/runs
        - ./cache:/app/cache
        - ./profiles:/app/profiles
        - ./data:/app/data         # NEW: SQLite
      environment:
        - STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
        - STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
        - STRIPE_DEV_MODE=${STRIPE_DEV_MODE:-false}
        - MAPBOX_ACCESS_TOKEN=${MAPBOX_ACCESS_TOKEN}
        - CORS_ALLOW_ORIGINS=${CORS_ALLOW_ORIGINS:-http://localhost:5173}
  ```

- [ ] **P7.7** Verificar que [docker/api.Dockerfile](docker/api.Dockerfile) inclui:
  - `requirements.txt` instalado com `pip install --no-cache-dir`
  - WeasyPrint system deps (Fase 6)
  - `COPY app/ core/ adapters/ cods_ok/ platforms.yaml .` (sem `data_cache/`, `runs/`, `data/`)

- [ ] **P7.8** Confirmar que `docker compose -p onde_morar_mvp up --build` em ambiente limpo (sem cache de imagens) passa sem error em menos de 10 minutos.

#### Bloco D — Runbook

- [ ] **P7.9** Criar `docs/runbook.md` com seções:
  - **Configuração inicial** (`.env` setup, Stripe keys, Mapbox token)
  - **Inicialização** — comandos `docker compose up`, portas, verificação de health
  - **Troubleshooting por sintoma:**
    - `state=failed` no runner → como ler `events.jsonl`
    - Subprocess timeout em `zones_by_ref` → verificar `data_cache/gtfs/`
    - Playwright timeout em `listings` → verificar `profiles/`, tentar com `headless=false`
    - PIX não confirmado → verificar logs do webhook Stripe
    - PDF não gerado → verificar WeasyPrint deps no container
  - **Rollback** — `docker compose down`, reverter commit, rebuild, validação com smoke A
  - **Escalação** — critérios para abrir issue vs rollback imediato

#### Bloco E — README

- [ ] **P7.10** Atualizar [README.md](README.md):
  - Setup local: clonar, configurar `.env` a partir de `.env.example`, `docker compose up`
  - Variáveis de ambiente com descrição
  - Fluxo de pagamento em dev (`STRIPE_DEV_MODE=true`) vs produção
  - Comandos de smoke E2E
  - Estrutura de `runs/` para debug

### 12.2 Checklist de Validação da Fase 7

| Gate | Critério | Status |
|---|---|---|
| **GATE-A** | `pytest tests/` verde | ⬜ |
| **GATE-A** | `npm run lint && npm run typecheck && npm run build` verde | ⬜ |
| **GATE-B** | Rate limiting bloqueia >5 req/min em `POST /reports` | ⬜ |
| **GATE-B** | `GET /health/ready` retorna `degraded` se `data_cache/gtfs/` ausente | ⬜ |
| **GATE-D** | `docker compose -p onde_morar_mvp up --build` em ambiente limpo — sem erro | ⬜ |
| **GATE-D** | Smoke E2E Dataset A completo com `STRIPE_DEV_MODE=true` | ⬜ |
| **GATE-D** | `test_invariants.py` passa | ⬜ |
| **OUTRO** | `docs/runbook.md` criado com seções de troubleshooting | ⬜ |
| **OUTRO** | `README.md` atualizado | ⬜ |

---

## 13. Fase 8 — Suíte E2E e Automação de Non-Regression

**Objetivo:** garantia formal de equivalência pré-migração/pós-migração e base para CI futuro.  
**Arquivos criados:** `tests/e2e/test_full_flow.spec.ts` · `tests/test_api_contract.py` · `scripts/validate_invariants.ps1`  
**Arquivos alterados:** [TEST_PLAN.md](TEST_PLAN.md)

### 13.1 Passos de Execução

#### Bloco A — Contract Tests

- [ ] **P8.1** Criar `tests/test_api_contract.py` — carrega snapshots de response de [tests/fixtures/](tests/fixtures/) e compara campo a campo:
  ```python
  # Para cada endpoint crítico:
  # - campos obrigatórios presentes
  # - tipos corretos (str, int, float, list, dict)
  # - sem campo inesperado adicionado (breaking)
  # Endpoints: POST /runs, GET /status, GET /zones, POST /detail, GET /final/listings.json
  ```

- [ ] **P8.2** Gerar snapshots iniciais contra o baseline da Fase 0 e commitá-los em `tests/fixtures/api_contract_snapshots/`.

#### Bloco B — Playwright E2E Frontend

- [ ] **P8.3** Criar `tests/e2e/test_full_flow.spec.ts` com Playwright:

  **Dataset A (smoke, obrigatório em cada PR):**
  ```typescript
  test('dataset A — fluxo completo', async ({ page }) => {
    // 1. Navegar para http://localhost:5173
    // 2. Clicar no mapa para definir ponto principal (Av. Paulista)
    // 3. Clicar "Gerar Zonas Candidatas" — aguardar QR Code (STRIPE_DEV_MODE=true → skip automático)
    // 4. Aguardar transição para Step 2 (polled via ReportStatus)
    // 5. Verificar que pelo menos 1 zona aparece na tabela
    // 6. Selecionar primeira zona, clicar "Detalhar zona"
    // 7. Aguardar Step 3 aparecer com listings
    // 8. Verificar que lista de imóveis não está vazia
    // 9. Clicar "Baixar JSON" — verificar download
    // 10. Clicar "Baixar Relatório PDF" — verificar download (content-type=application/pdf)
  });
  ```

  **Dataset B (deduplicação):**
  ```typescript
  test('dataset B — 2 refs com sobreposição → zone_uid únicos', async ({ page }) => {
    // Repetir fluxo com 2 ref points próximos
    // Verificar que zonas exibidas têm UIDs únicos (comparar com API /runs/{id}/zones)
    // Verificar que zones_consolidated tem menos featues que a soma de zones by ref (deduplication ativa)
  });
  ```

  **Dataset C (stress, apenas em release branches):**
  ```typescript
  test.skip('dataset C — 3 refs, volume máximo', async ({ page }) => {
    // 3 ref points, max_streets_per_zone=5
    // Pipeline não deve exceder 20% de degradação de tempo vs baseline_A
    // listings_final.count >= baseline_A count (ou justificativa documentada)
  });
  ```

#### Bloco C — Scripts de Automação

- [ ] **P8.4** Criar `scripts/validate_invariants.ps1`:
  ```powershell
  param([string]$RunId)
  # Recebe run_id como argumento
  # Roda: pytest tests/test_invariants.py --run-id=$RunId
  # Exibe PASS/FAIL por invariante
  ```

- [ ] **P8.5** Criar `scripts/run_contract_tests.ps1`:
  ```powershell
  # Sobe compose, aguarda /health/ready, roda test_api_contract.py
  # Exibe diff se algum campo mudou
  ```

#### Bloco D — Atualização TEST_PLAN.md

- [ ] **P8.6** Atualizar [TEST_PLAN.md](TEST_PLAN.md) com:
  - Referência aos 3 datasets (A/B/C) e seus inputs em `tests/fixtures/`
  - Matriz de testes por tipo de alteração (da seção 7 do BEST_PRACTICES_REMEDIATION_PLAN.md)
  - Gates A/B/C/D por fase
  - Critérios de aceitação de performance (degradação máxima 20%)

### 13.2 Checklist de Validação da Fase 8

| Gate | Critério | Status |
|---|---|---|
| **GATE-A** | `pytest tests/` verde (incluindo `test_api_contract.py`) | ⬜ |
| **GATE-B** | `test_api_contract.py` todos snapshots validam sem diff | ⬜ |
| **GATE-D** | Playwright E2E Dataset A verde | ⬜ |
| **GATE-D** | Playwright E2E Dataset B verde (zone_uid únicos) | ⬜ |
| **GATE-D** | `test_invariants.py` verde para run gerado pelo E2E | ⬜ |
| **OUTRO** | `TEST_PLAN.md` atualizado com datasets A/B/C e gates | ⬜ |
| **OUTRO** | Script `validate_invariants.ps1` executável e documentado | ⬜ |

---

## 14. Invariantes de Dados

> As invariantes que se seguem **nunca podem ser violadas** após nenhuma fase de migração. `test_invariants.py` as valida automaticamente.

| ID | Invariante | Como Validar |
|---|---|---|
| **INV-1** | `zones_consolidated.geojson` tem `features` não-vazia quando o baseline também tiver | `len(geojson["features"]) > 0` |
| **INV-2** | Todos os `zone_uid` são únicos no GeoJSON de zonas | `len(uids) == len(set(uids))` |
| **INV-3** | `listings_final.json` contém apenas itens com `address` que inclui logradouro válido | `all(_address_has_valid_street_type(item["address"]) for item in listings)` |
| **INV-4** | `listings_final.geojson` não contém itens com `lat=0` ou `lon=0` | `all(abs(f["geometry"]["coordinates"][0]) > 0.001 and abs(f["geometry"]["coordinates"][1]) > 0.001 for f in features)` |
| **INV-5** | Campo `state` (estado do imóvel: SP, RJ etc.) preenchido em todos os listings finais | `all(item.get("state") for item in listings)` |
| **INV-6** | `listings_final.csv`, `listings_final.json` e `listings_final.geojson` são parseáveis e cardinalidade é consistente | CSV rows == JSON items == GeoJSON features (somente os que têm coords) |

---

## 15. Critérios de Rollback

### 15.1 Condições de Rollback Obrigatório

Rollback **imediato** de um lote (fase ou bloco) se qualquer item:

1. Falha crítica em endpoint principal: `POST /reports`, `GET /reports/{id}/status`, `POST /finalize`.
2. Quebra de contrato API→UI sem versionamento: campo removido ou tipo alterado.
3. Artifacts finais ausentes ou não-parseáveis (`listings_final.json`, `zones_consolidated.geojson`).
4. `test_invariants.py` falha em qualquer invariante.
5. Degradação de tempo total do pipeline > 20% no mesmo dataset sem mitigação documentada.
6. Segredo detectado em código, log ou artifact (`MAPBOX_ACCESS_TOKEN`, `STRIPE_SECRET_KEY`).
7. `listings_final.json` count < `BASELINE_A_FINAL_COUNT * 0.95` sem justificativa de nova regra de filtro.

### 15.2 Procedimento de Rollback

```
1. git revert <commit> --no-edit   (ou git reset --hard <commit_anterior>)
2. docker compose -p onde_morar_mvp down
3. docker compose -p onde_morar_mvp up -d --build
4. Aguardar /health/ready
5. Executar scripts/e2e_smoke_dataset_a.ps1
6. Confirmar state=success e counts ≥ baseline
7. Abrir issue com causa-raiz antes de nova tentativa da fase
```

---

## 16. Glossário de Artefatos

| Artefato | Caminho | Gerado por | Imutável após |
|---|---|---|---|
| `input.json` | `runs/<id>/input.json` | `RunStore.create_run` | Criação do run |
| `status.json` | `runs/<id>/status.json` | `RunStore.*` | Nunca (atualizado em cada stage) |
| `events.jsonl` | `runs/<id>/logs/events.jsonl` | `RunStore.append_log` | Nunca (append-only) |
| `zones.geojson` | `runs/<id>/zones/by_ref/ref_<i>/raw/outputs/zones.geojson` | `candidate_zones_adapter` | Stage `zones_by_ref` |
| `zones_enriched.geojson` | `runs/<id>/zones/by_ref/ref_<i>/enriched/zones_enriched.geojson` | `zone_enrich_adapter` | Stage `zones_enrich` |
| `zones_consolidated.geojson` | `runs/<id>/zones/consolidated/zones_consolidated.geojson` | `core/consolidate.py` | Stage `zones_consolidate` |
| `streets.json` | `runs/<id>/zones/detail/<uid>/streets.json` | `streets_adapter` | `POST /detail` |
| `pois.json` | `runs/<id>/zones/detail/<uid>/pois.json` | `pois_adapter` | `POST /detail` |
| `transport.json` | `runs/<id>/zones/detail/<uid>/transport.json` | `core/zone_ops.py` | `POST /detail` |
| `compiled_listings.json` | `runs/<id>/zones/detail/<uid>/streets/<slug>/listings/compiled_listings.json` | `listings_adapter` | `POST /listings` |
| `listings_final.json` | `runs/<id>/final/listings_final.json` | `core/listings_ops.finalize_run` | `POST /finalize` |
| `listings_final.geojson` | `runs/<id>/final/listings_final.geojson` | `core/listings_ops.finalize_run` | `POST /finalize` |
| `report.pdf` | `runs/<id>/final/report.pdf` | `app/services/pdf_service.py` | Pipeline concluído |
| `selected_zones.json` | `runs/<id>/selected_zones.json` | `POST /zones/select` | `POST /zones/select` |
| `public_safety.json` | `runs/<id>/security/public_safety.json` | `core/public_safety_ops` | Stage `public_safety` |
| `db.sqlite` | `data/db.sqlite` | SQLAlchemy startup | Nunca (estado de produto) |

---

## Progress Tracker — Histórico de Execução

> Atualizar a cada fase concluída, com data e run_id de validação.

| Data | Fase | Status | Run ID de Validação | Observações |
|---|---|---|---|---|
| — | 0 — Baseline | ⬜ | — | — |
| — | 1 — Hardening Backend | ⬜ | — | — |
| — | 2 — SQLite | ⬜ | — | — |
| — | 3 — Stripe Pix | ⬜ | — | — |
| — | 4 — Frontend Decomp | ⬜ | — | — |
| — | 5 — UX/UI | ⬜ | — | — |
| — | 6 — PDF | ⬜ | — | — |
| — | 7 — Observabilidade | ⬜ | — | — |
| — | 8 — E2E Automação | ⬜ | — | — |

---

*Fim do documento. Versão 1.0 — 2026-03-04.*
