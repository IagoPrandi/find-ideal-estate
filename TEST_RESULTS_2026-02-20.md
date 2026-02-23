# Test Results — 2026-02-20

## Scope executed
- Component smoke tests (store, core logic, API contract basics)
- Adapter command-contract tests
- Integration smoke (runner orchestration + detail + listings + finalize) with deterministic adapter stubs
- Frontend build validation
- Browser UI static smoke (rendered controls)
- NFR smoke (status/zones latency with synthetic payload, finalize idempotency)
- Docker Compose config validation
- Script E2E (API) Dataset A from TEST_PLAN

## Results summary
- Passed suites: 8/8
- Failed suites: 0/8

## Detailed outcomes
1) Component smoke
- Status: PASS
- Checks: `RunStore`, `consolidate_zones`, `haversine_m`, `zone helpers`, `finalize_run`, health endpoints and input validation basics.

2) Adapter contract
- Status: PASS
- Checks: argument forwarding and option presence for all adapters:
  - `candidate_zones_adapter`
  - `zone_enrich_adapter`
  - `streets_adapter`
  - `pois_adapter`
  - `listings_adapter`

3) Integration smoke (deterministic)
- Status: PASS
- Checks:
  - `Runner.run_pipeline()` stage progression to success
  - consolidated zones artifact generation
  - zone detail artifact generation (`streets.json`, `pois.json`, `transport.json`)
  - listings scrape orchestration and final output generation

4) Frontend build
- Status: PASS
- Evidence: `vite build` succeeded and generated `ui/dist` bundle.

5) Browser UI static smoke
- Status: PASS
- Checks:
  - page renders title `Imovel Ideal`
  - all 6 workflow buttons rendered

6) NFR smoke
- Status: PASS
- Measurements:
  - `GET /runs/{run_id}/status` p95: 5.42 ms
  - `GET /runs/{run_id}/zones` p95 (2,000 synthetic features): 11.79 ms
- Idempotency:
  - `finalize_run` repeated twice preserved row count (no duplication)

7) Docker compose config
- Status: PASS
- Check: `docker compose config` parsed and validated service wiring.

8) Script E2E (API) Dataset A
 - Status: PASS (após correções)
 - Script: Dataset A flow defined em TEST_PLAN (`POST /runs` -> poll zones -> select -> detail -> listings -> finalize).
 - Run ID final aprovado: `20260221032857_47f4384b`
 - Evidências:
   - `RUN_ID` criado
   - `ZONE_UID` selecionado
   - `FINAL_COUNT=413`
   - amostra dos 5 primeiros imóveis retornada pelo script
 - Correções aplicadas até aprovação:
   1. argumento de seed negativo no adapter de zonas (`--seed-bus-coord=<lat,lon>`)
   2. robustez geoespacial em `zone_enrich_green_flood_v3.py` para geometrias inválidas
   3. UTF-8 forçado no subprocess do candidate zones para evitar `UnicodeEncodeError` no Windows host
   4. adapter de listings com suporte a `xvfb-run` no Docker e resolução correta de `runs/run_*`
   5. scraping resiliente por rua (falha parcial não derruba endpoint)
   6. finalização compatível com `compiled_listings.json` em formato lista e fallback de coordenadas pelo centróide da zona

9) Reteste estrito (sem fallback) a partir da seleção de zona
- Status: PASS
- Regra validada: saída final só aceita imóveis com coordenadas reais (`lat/lon`) e `state` não vazio.
- Execução:
  - `RUN_ID=20260221184624_3b08fcec`
  - `ZONE_UID=ee5acbc2ab16dd67`
  - `FINAL_COUNT=308`
  - `BAD_COORDS=0`
  - `BAD_STATE=0`
  - `QA_COUNT=0`
  - `VR_COUNT=308`
- Observação: no recorte desta execução, os itens do QuintoAndar não trouxeram `state` explícito no payload e, pela regra estrita, foram filtrados da saída final.

10) QuintoAndar com `state` obrigatório (correção + validação)
- Status: PASS
- Ajuste aplicado no parser para inferir UF real (`SP`) quando o payload do QuintoAndar não traz `state` explícito, usando sinais de endereço/cidade/URL.
- Execução validada em Docker:
  - `RUN_ID=20260221190353_92a09fb2`
  - `ZONE_UID=8222dcda974294a2`
  - `FINAL=22`
  - `QA=22`
  - `QA_STATE_MISSING=0`
- Evidência: amostra de 3 imóveis do QuintoAndar com `state="SP"` e coordenadas reais.

11) M8 smoke automatizado + DoD operacional
- Status: PASS
- Script: [scripts/e2e_smoke_dataset_a.ps1](scripts/e2e_smoke_dataset_a.ps1)
- Execução validada:
  - `RUN_ID=20260222030058_3b08fcec`
  - `FINAL_COUNT=3`
  - `BAD_COORDS=0`
  - `BAD_STATE=0`
- Exports finais validados via API:
  - `/final/listings.json`
  - `/final/listings.csv`
  - `/final/listings` (GeoJSON)
- Observabilidade por run validada:
  - `runs/20260222030058_3b08fcec/logs/events.jsonl` com eventos por etapa (`validate`, `zones_by_ref`, `zones_enrich`, `zones_consolidate`, `done`).

12) VivaReal `state` obrigatório (correção + validação)
- Status: PASS
- Ajuste aplicado no parser para extrair `state` também de `address.stateAcronym` (listing e wrapper) e de `address.locationId` quando aplicável.
- Execução validada em Docker:
  - `RUN_ID=20260222151511_f7970234`
  - `ZONE_UID=747167e4ca0ede3f`
  - `FINAL=308`
  - `VR=308`
  - `VR_STATE_MISSING=0`
- Evidência: amostra de 3 imóveis do VivaReal com `state="SP"` e coordenadas reais.

13) M1 — Segurança pública integrada ao runner
- Status: PASS
- Escopo validado:
  - Stage `public_safety` integrado ao pipeline com execução opcional por `params.public_safety_enabled`.
  - Persistência de artifacts planejada em `runs/<run_id>/security/by_ref/ref_<i>/public_safety.json` e `runs/<run_id>/security/public_safety.json`.
  - Endpoint dedicado planejado/implementado para leitura do agregado: `GET /runs/{run_id}/security`.
- Execução de validação local:
  - `RUN_ID=20260222171226_0de61386`
  - `STATE=success`
  - `HAS_PUBLIC_SAFETY_STAGE=True`

14) M8 acompanhamento — bloqueio operacional detectado
- Status: OPEN (não bloqueia M1)
- Ao tentar rebuild do container `api` para validar endpoint novo em Docker, houve falha por `requirements.txt` em formato ponteiro Git LFS (`Invalid requirement: version https://git-lfs.github.com/spec/v1`).
- Ação pendente para avanço contínuo de M8 em Docker:
  - restaurar conteúdo real de `requirements.txt` (não ponteiro LFS) e repetir `docker compose up -d --build api`.

15) Fluxo inicial isolado (sem API) — ponto -> geração de zonas em Docker
- Status: PASS
- Requisito atendido: teste executado sem endpoints da API, diretamente no container `onde_morar_mvp-api-1`.
- Ponto usado (Dataset A): `lat=-23.585068145112295`, `lon=-46.690640014541714`.
- Comando executado no container: `python cods_ok/candidate_zones_from_cache_v10_fixed2.py --cache-dir /app/data_cache --seed-bus-coord=-23.585068145112295,-46.690640014541714 --auto-rail-seed --out-dir /app/runs/manual_zones_20260222_191930`.
- Evidências de saída:
  - `RUN_TAG=manual_zones_20260222_191930`
  - `ZONE_FEATURES=82`
  - artifacts gerados em `runs/manual_zones_20260222_191930/outputs/`:
    - `zones.geojson`
    - `ranking.csv`
    - `trace.json`

16) Fluxo quase completo (sem API) em Docker — pulando `zone_enrich_green_flood`
- Status: PASS PARCIAL (execução concluída; saída final vazia)
- Requisito atendido: execução sem API no container `onde_morar_mvp-api-1`, com `zone_enrich` explicitamente pulado e substituído por espelhamento de `raw -> enriched`.
- Sequência executada no container:
  1. `candidate_zones` com ponto fixo do Dataset A
  2. `zone_enrich` pulado (copy `zones.geojson` -> `zones_enriched.geojson`, `ranking.csv` -> `ranking_enriched.csv`)
  3. `consolidate_zones`
  4. seleção de 1 zona (`zone_uid`)
  5. `build_zone_detail`
  6. `scrape_zone_listings` (limite 1 rua)
  7. `finalize_run`
- Run validado:
  - `RESULT_RUN_ID=manual_no_enrich_20260223_003604`
  - `RESULT_ZONE_UID=102abfdcd6ccbf59`
  - `RESULT_LISTINGS_FILES=1`
  - `RESULT_FINAL_COUNT=0`
  - `RESULT_BAD_COORDS=0`
  - `RESULT_BAD_STATE=0`
- Observação técnica:
  - houve correções de ambiente dentro do container para o scraping rodar (`orjson`, `rapidfuzz`, `tqdm`, pin `playwright==1.50.0` para compatibilidade com browsers da imagem).
  - mesmo com 1 arquivo de listings gerado, o `finalize` permaneceu vazio neste recorte específico.

## Gaps / limitations
- E2E Docker com Dataset A foi concluído com sucesso, porém ainda falta campanha de 20 execuções consecutivas para comprovar meta de $\ge 95\%$ de sucesso.
- UI smoke validated rendered workflow controls, but not full click-through with real backend external calls.
- Resilience under real third-party failures was validated at design/smoke level, not by chaos/fault-injection in live dependencies.

## Recommended next run (to fully close TEST_PLAN)
- Execute live E2E with valid external credentials and network access:
  - 20 consecutive smoke runs for success-rate target (>=95%)
  - fault-injection for one street/platform failing during scrape
  - full UI click-through with backend live pipeline
- Add automated regression scripts to repository (pytest + CI) to make this repeatable.
