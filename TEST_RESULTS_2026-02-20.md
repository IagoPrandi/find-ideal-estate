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
