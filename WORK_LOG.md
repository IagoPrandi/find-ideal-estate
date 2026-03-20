# Work Log

## 2026-03-16 - Fase 0 (M0.1-M0.4)

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/release-config-management/SKILL.md`
- Scope executed:
  - Monorepo base structure (`apps/`, `packages/contracts/`, `infra/migrations/`)
  - Docker stack with `postgres` (PostGIS), `redis`, `api`
  - Base API in `apps/api/src` with `core/config.py`, JSON logging, request ID middleware, `/health`
  - Alembic base config + initial migration with `users`, `journeys`, `jobs`, `job_events`
  - CI workflow (`ruff`, `mypy --strict apps/api/src/core`, `pytest`)
  - `.env.example`, `.editorconfig`, `.gitignore` updates

- Milestone policy note:
  - Milestones were implemented but not marked as complete in `PRD.md` pending user confirmation.

- Verification status update:
  - `cd apps/api && python -c "from contracts import __version__"` passes (`0.1.0`).
  - `ruff`, `mypy --strict apps/api/src/core`, and `pytest -q apps/api/tests` pass.
  - Compose project padronizado para `onde_morar` (`name: onde_morar` no `docker-compose.yml`).
  - `docker compose -p onde_morar up -d --build api postgres redis` sobe com `postgres` e `redis` healthy.
  - `alembic upgrade head` aplica com sucesso em `find_ideal_estate`.
  - `GET /health` retorna `{"status":"ok","db":"ok","redis":"ok"}`.

## 2026-03-16 - Fase 1 (M1.1-M1.4) em progresso

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/security-threat-checklist/SKILL.md`
- Threat model snapshot:
  - Protected assets: integridade de jornadas/jobs, disponibilidade da API, isolamento de sessão anônima.
  - Entrypoints: `POST/GET/PATCH/DELETE /journeys`, `POST/GET /jobs`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/events`.
  - Top threats: input inválido em payloads, enum/state injection, vazamento de eventos entre jobs; mitigação via schemas Pydantic, filtros por `job_id`, stream por canal Redis dedicado.
- Scope executed:
  - Contratos compartilhados para `JourneyState`, `JobType`, `JobState` e DTOs de jornada/job.
  - Helpers de acesso a DB e Redis para uso além do health check.
  - Serviços mínimos de persistência para jornadas, jobs e `job_events`.
  - Rotas `/journeys` e `/jobs`, incluindo cookie `anonymous_session_id` e SSE com replay por `Last-Event-ID`.
  - Migration `20260316_0002_phase1_domain.py` completando colunas base de `journeys` e criando `transport_points` e `zones`.
  - Testes de rotas e lógica de SSE.

- Milestone policy note:
  - Fase 1 segue em progresso; nenhum marco foi marcado como concluído no `PRD.md` sem confirmação do usuário.

- Validation status update:
  - `docker compose exec api alembic upgrade head` aplicou `20260316_0002` com sucesso no Postgres da stack `onde_morar`.
  - Verificação SQL no banco real confirmou as tabelas `journeys`, `jobs`, `job_events`, `transport_points` e `zones`, além das colunas novas de `journeys`.
  - Smoke literal M1.4 concluído com API real em `localhost:8000` + Redis real em `localhost:6379`:
    - `POST /journeys` e `POST /jobs` funcionaram no stack após reinício da API.
    - Evento publicado por `publish_job_event()` chegou ao SSE em `87.93ms` (`job.stage.progress`).
    - Reconexão com `Last-Event-ID` recebeu corretamente o evento persistido posterior (`job.stage.completed`).
  - Ajustes de runtime descobertos e corrigidos durante a validação literal:
    - shim de `contracts` em `apps/api/contracts/__init__.py` para reexportar DTOs compartilhados fora do pytest;
    - compatibilidade Python 3.10 no container da API (`StrEnum` -> enum string compatível, `datetime.UTC` -> `timezone.utc`);
    - insert de `journeys` sem `CASE` ambíguo para ponto secundário opcional nulo.

- Governança de milestone:
  - Com confirmação explícita do usuário, o `PRD.md` foi atualizado para marcar M1.1, M1.2, M1.3, M1.4 e a Fase 1 como concluídos.

## 2026-03-17 - Fase 2 (M2.1-M2.5) em progresso

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/ops-observability-runbook/SKILL.md`
- Scope executed:
  - Auditoria de aceite de Fase 0 e Fase 1 antes de iniciar Fase 2.
  - Correção no shim de contratos em `apps/api/contracts/__init__.py` para restabelecer o check de verificação M0.1 (`cd apps/api && python -c "from contracts import __version__"`).
  - Estrutura base de workers criada em `apps/api/src/workers/` com:
    - `queue.py` (StubBroker, RedisBroker, filas canônicas e prioridades USER_REQUEST/PREWARM),
    - `retry_policy.py` (JobRetryPolicy por tipo de job),
    - `middleware.py` (transições de estado + heartbeat Redis + progresso de estágio),
    - `cancellation.py` (cancelamento cooperativo via `JobCancelledException`),
    - `runtime.py` (execução com retry/backoff),
    - `watchdog.py` (varredura periódica de jobs `running` sem heartbeat),
    - `bootstrap.py` (inicialização de broker/handlers/watchdog no lifecycle).
  - Handler stub de `TRANSPORT_SEARCH` criado (`workers/handlers/transport.py`) com progresso incremental a cada 500ms.
  - Integração com API:
    - `main.py` inicializa/desliga runtime de workers no lifespan.
    - `modules/jobs/service.py` ganhou `enqueue_job()` e helper `update_job_execution_state()`.
    - `core/config.py` recebeu `dramatiq_broker` (default `stub`).
  - Contrato atualizado com `JobState.CANCELLED_PARTIAL` para suportar cancelamento parcial.
  - Dependências adicionadas: `dramatiq`, `apscheduler`.
  - Testes de Fase 2 adicionados em `apps/api/tests/test_phase2_workers.py`.

- Milestone policy note:
  - Fase 2 segue em progresso; nenhum marco foi marcado como concluído no `PRD.md` sem confirmação do usuário.

- Validation status update:
  - Verificação de Fase 0/Fase 1 antes de iniciar Fase 2:
    - `cd apps/api && python -c "from contracts import __version__; print(__version__)"` -> `0.1.0`.
    - `python -m pytest -q apps/api/tests/test_phase0_health.py apps/api/tests/test_phase1_journeys_jobs_routes.py apps/api/tests/test_phase1_sse.py` -> `9 passed`.
  - Verificação após implementação de Fase 2:
    - `python -m ruff check apps/api/contracts/__init__.py apps/api/src/workers apps/api/src/modules/jobs/service.py apps/api/tests/test_phase2_workers.py` -> `All checks passed!`.
    - `python -m pytest -q apps/api/tests/test_phase2_workers.py apps/api/tests/test_phase1_sse.py apps/api/tests/test_phase1_journeys_jobs_routes.py apps/api/tests/test_phase0_health.py` -> `14 passed`.

## 2026-03-17 - Fase 2 (M2.x) continuidade

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/ops-observability-runbook/SKILL.md`
- Scope executed (delta):
  - `workers/runtime.py` atualizado para heartbeat periódico a cada 30s durante execução do job (`job_heartbeat:{id}` com TTL 120s).
  - `workers/middleware.py` atualizado para:
    - setar `started_at` no início de execução (`mark_running`),
    - emitir evento explícito de transição para pendente (`job.pending`).
  - `modules/jobs/service.py` atualizado com suporte a `mark_started` em `update_job_execution_state`.
  - `workers/queue.py` recebeu mapeamento explícito de concorrência por fila (`QUEUE_CONCURRENCY`) alinhado ao PRD.
  - `apps/api/tests/test_phase2_workers.py` ampliado com:
    - cobertura de retry policy para todos os `JobType`,
    - verificação de sequência `failed -> retrying -> pending` no retry,
    - verificação de cadência/progresso do stub `TRANSPORT_SEARCH` (6 ticks de 500ms, 3s total),
    - verificação de metadados de fila/concorrência.

- Milestone policy note:
  - Fase 2 permanece em progresso; sem marcação de milestone no `PRD.md` até confirmação explícita do usuário.

- Validation status update:
  - `python -m ruff check apps/api/src/workers apps/api/src/modules/jobs/service.py apps/api/tests/test_phase2_workers.py` -> `All checks passed!`.
  - `python -m pytest -q apps/api/tests/test_phase2_workers.py apps/api/tests/test_phase1_sse.py apps/api/tests/test_phase1_journeys_jobs_routes.py apps/api/tests/test_phase0_health.py` -> `16 passed`.

## 2026-03-17 - Fase 2 (M2.5 smoke StubBroker)

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/ops-observability-runbook/SKILL.md`
- Scope executed (delta):
  - Novo smoke test de fila + SSE para M2.5 em `apps/api/tests/test_phase2_smoke_stubbroker.py`.
  - O teste valida o fluxo local com `StubBroker`:
    - enfileira `transport_search_actor`,
    - processa com `dramatiq.worker.Worker`,
    - abre stream `job_events_stream(...)`,
    - aguarda evento SSE `job.completed` em < 10s.
  - Ajustes de isolamento no smoke para tornar execução determinística em ambiente de teste:
    - actor explicitamente vinculado ao `StubBroker` do teste,
    - stubs de heartbeat/state update/cancel check,
    - Redis/pubsub fake para o stream SSE.

- Milestone policy note:
  - Fase 2 permanece em progresso; sem marcação de milestone no `PRD.md` até confirmação explícita do usuário.

- Validation status update:
  - `python -m ruff check apps/api/tests/test_phase2_smoke_stubbroker.py apps/api/tests/test_phase2_workers.py apps/api/src/workers apps/api/src/modules/jobs/service.py` -> `All checks passed!`.
  - `python -m pytest -q apps/api/tests/test_phase2_smoke_stubbroker.py` -> `1 passed`.
  - `python -m pytest -q apps/api/tests/test_phase2_smoke_stubbroker.py apps/api/tests/test_phase2_workers.py apps/api/tests/test_phase1_sse.py apps/api/tests/test_phase1_journeys_jobs_routes.py apps/api/tests/test_phase0_health.py` -> `17 passed`.

## 2026-03-17 - Fase 2 (M2.3 cancel E2E)

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/ops-observability-runbook/SKILL.md`
- Scope executed (delta):
  - `apps/api/tests/test_phase2_smoke_stubbroker.py` expandido com cenário E2E de cancelamento cooperativo:
    - inicia worker com `StubBroker` e actor `TRANSPORT_SEARCH`,
    - detecta primeiro `job.stage.progress`,
    - chama `POST /jobs/{id}/cancel`, valida `202`,
    - aguarda SSE `job.cancelled` e valida latência `< 2s`.
  - Mantido isolamento determinístico de teste com stubs de heartbeat/state/cancel check e pubsub fake.

- Milestone policy note:
  - Fase 2 permanece em progresso; sem marcação de milestone no `PRD.md` até confirmação explícita do usuário.

- Validation status update:
  - `python -m ruff check apps/api/tests/test_phase2_smoke_stubbroker.py` -> `All checks passed!`.
  - `python -m pytest -q apps/api/tests/test_phase2_smoke_stubbroker.py` -> `2 passed`.
  - `python -m pytest -q apps/api/tests/test_phase2_smoke_stubbroker.py apps/api/tests/test_phase2_workers.py apps/api/tests/test_phase1_sse.py apps/api/tests/test_phase1_journeys_jobs_routes.py apps/api/tests/test_phase0_health.py` -> `18 passed`.

## 2026-03-17 - Fase 2 (cobertura complementar M2.2/M2.4)

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/ops-observability-runbook/SKILL.md`
- Scope executed (delta):
  - `apps/api/tests/test_phase2_workers.py` expandido com cobertura adicional:
    - falha após `max_retries` para `TRANSPORT_SEARCH` validando sequência e backoff (`retrying` duas vezes, `pending` duas vezes, final `failed`, sleeps `[5, 30]`),
    - watchdog não altera jobs `running` quando heartbeat existe (caso não-stale).

- Milestone policy note:
  - Fase 2 permanece em progresso; sem marcação de milestone no `PRD.md` até confirmação explícita do usuário.

- Validation status update:
  - `python -m ruff check apps/api/tests/test_phase2_workers.py apps/api/tests/test_phase2_smoke_stubbroker.py apps/api/src/workers apps/api/src/modules/jobs/service.py` -> `All checks passed!`.
  - `python -m pytest -q apps/api/tests/test_phase2_smoke_stubbroker.py apps/api/tests/test_phase2_workers.py apps/api/tests/test_phase1_sse.py apps/api/tests/test_phase1_journeys_jobs_routes.py apps/api/tests/test_phase0_health.py` -> `20 passed`.

## 2026-03-17 - Fase 2 (residuais de execução)

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/ops-observability-runbook/SKILL.md`
- Scope executed (delta):
  - Worker runner com concorrência por fila implementado em `apps/api/src/workers/runner.py`:
    - parse de filas por argumento/env (`WORKER_QUEUES`),
    - plano `queue -> worker_threads` via `QUEUE_CONCURRENCY`,
    - startup de workers por fila com `dramatiq.worker.Worker(..., queues={queue}, worker_threads=...)`.
  - Script de verificação manual do watchdog criado em `scripts/phase2_watchdog_manual_check.ps1`:
    - inicia worker da fila `transport`,
    - cria jornada/job via API,
    - mata worker,
    - faz polling do job até `cancelled_partial` e reporta tempo.
  - Cobertura de testes complementar:
    - `apps/api/tests/test_phase2_runner.py` para parse/plano de concorrência do runner,
    - `apps/api/tests/test_phase2_workers.py` expandido com:
      - sucesso de `run_job_with_retry` para todos os `JobType`,
      - exaustão de retries (`failed` após backoff esperado),
      - watchdog ignora job quando heartbeat existe.

- Milestone policy note:
  - Fase 2 permanece em progresso; sem marcação de milestone no `PRD.md` até confirmação explícita do usuário.

- Validation status update:
  - `python -m ruff check apps/api/src/workers/runner.py apps/api/tests/test_phase2_runner.py apps/api/tests/test_phase2_workers.py apps/api/tests/test_phase2_smoke_stubbroker.py apps/api/src/workers apps/api/src/modules/jobs/service.py` -> `All checks passed!`.
  - `python -m pytest -q apps/api/tests/test_phase2_runner.py apps/api/tests/test_phase2_smoke_stubbroker.py apps/api/tests/test_phase2_workers.py apps/api/tests/test_phase1_sse.py apps/api/tests/test_phase1_journeys_jobs_routes.py apps/api/tests/test_phase0_health.py` -> `24 passed`.

## 2026-03-18 - Fase 3 (M3.1) em progresso

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/develop-frontend/SKILL.md`
- Scope executed:
  - Criação do novo app `apps/web` em Next.js 14 + App Router + TypeScript.
  - Layout inicial da Etapa 1 com mapa como plano principal, painel auxiliar e responsividade desktop/mobile.
  - Integração MapLibre + MapTiler em `apps/web/components/map-shell.tsx`, com seleção de ponto principal/secundário por clique no mapa e fallback manual por coordenadas quando a chave pública não está definida.
  - Port da configuração inicial da jornada em `apps/web/components/journey-studio.tsx` com parâmetros de aluguel/compra, modal, raio, tempo máximo, distância até seed e toggles de análises urbanas.
  - Proxy server-side em `apps/web/app/api/journeys/route.ts` para persistir a Etapa 1 no backend atual via `POST /journeys`, preservando `set-cookie` da sessão anônima sem depender de CORS.
  - `package-lock.json` gerado para reprodutibilidade do app novo e `.gitignore` atualizado para ignorar `*.tsbuildinfo`.

- Milestone policy note:
  - Fase 3 permanece em progresso; nenhum marco foi marcado como concluído no `PRD.md` sem confirmação explícita do usuário.

- Validation status update:
  - `cd apps/web && npm run typecheck` -> `tsc --noEmit` sem erros.
  - `cd apps/web && npm run build` -> `next build` concluído com sucesso (`/` estático e `/api/journeys` dinâmico).

## 2026-03-18 - Fase 3 (M3.2) continuidade e verificação final

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/release-config-management/SKILL.md`
- Scope executed (delta):
  - Correção de runtime em `apps/api/src/modules/transport/gtfs_ingestion.py`:
    - sufixo de tabelas temporarias passou a usar prefixo alfabetico (`s{uuid}`) para satisfazer validacao de identificador SQL seguro.
  - Revalidacao completa do milestone M3.2 no banco real.

- Milestone policy note:
  - M3.2 continua sem marcacao no `PRD.md` ate confirmacao explicita do usuario.

- Validation status update:
  - `python -m pytest apps/api/tests/test_phase3_gtfs_ingestion.py -q` -> `1 passed`.
  - Primeira ingestao real:
    - `python scripts/ingest_gtfs_postgis.py --dataset-type gtfs_sptrans --gtfs-dir data_cache/gtfs`
    - resultado: `skipped=false`, `gtfs_stops=22093`, `elapsed_seconds=25.151`.
  - Re-ingestao do mesmo arquivo:
    - mesmo comando acima
    - resultado: `skipped=true`, `elapsed_seconds=0.618` (< 2s conforme PRD).
  - Verificacoes SQL finais:
    - `SELECT count(*) FROM gtfs_stops` -> `22093` (aprox. 22.094 esperado no PRD).
    - `SELECT count(*) FROM dataset_versions WHERE dataset_type='gtfs_sptrans' AND is_current=true` -> `1`.
    - `SELECT ... FROM pg_indexes ... '%USING gist%'` em `gtfs_stops` -> `1` indice GIST.

## 2026-03-18 - Marcacao de milestone M3.2

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/release-config-management/SKILL.md`
- Scope executed:
  - Com confirmacao explicita do usuario, o `PRD.md` foi atualizado para marcar M3.2 como concluido.
  - Progress Tracker da Fase 3 atualizado para refletir `M3.1-M3.2 concluidos`.
  - `cd apps/web && npm install --package-lock-only` -> lockfile gerado com sucesso.
  - Observação de segurança operacional: `npm` reportou `1 high severity vulnerability` na árvore instalada atual; nenhuma correção automática foi aplicada nesta etapa para evitar mexer em dependências além do escopo do marco M3.1.

## 2026-03-18 - Fase 3 (M3.1) verificação de aceite PRD

- Required docs opened:
  - `PRD.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/develop-frontend/SKILL.md`
- Scope executed:
  - Revalidação objetiva dos critérios de verificação do M3.1 no PRD.
  - Execução de build de produção do Next.js em `apps/web`.
  - Teste E2E real do caminho do formulário (via proxy Next): `POST /api/journeys` com payload da Etapa 1.
  - Confirmação de persistência no backend por leitura direta em `GET /journeys/{id}` após criação via Next.

- Milestone policy note:
  - M3.1 não foi marcado como concluído no `PRD.md`; segue aguardando confirmação explícita do usuário.

- Validation status update:
  - `cd apps/web && npm run build` -> `next build` verde.
  - `Invoke-WebRequest http://localhost:8000/health` -> `{"status":"ok","db":"ok","redis":"ok"}`.
  - `POST http://localhost:3000/api/journeys` -> `201` com `id` de jornada e `Set-Cookie: anonymous_session_id=...`.
  - `GET http://localhost:8000/journeys/{id}` para jornada criada via Next -> `200` com `state: draft`.

## 2026-03-18 - Fase 3 (M3.1) confirmado e marcado

- Required docs opened:
  - `PRD.md`
- Skill used:
  - `skills/develop-frontend/SKILL.md`
- Governança de milestone:
  - Com confirmação explícita do usuário, o marco `M3.1` foi marcado como concluído no `PRD.md`.
  - O `Progress Tracker` foi atualizado para refletir a Fase 3 como `🔄 Em progresso`.

## 2026-03-18 - Fase 3 (M3.2) implementado e validado

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/release-config-management/SKILL.md`
- Scope executed:
  - Migration Alembic criada: `infra/migrations/versions/20260318_0003_gtfs_ingestion_schema.py` com:
    - `dataset_versions` + constraints de unicidade (`dataset_type, version_hash`) e current único por tipo.
    - tabelas `gtfs_stops`, `gtfs_routes`, `gtfs_trips`, `gtfs_stop_times`, `gtfs_shapes`.
    - índice espacial GIST em `gtfs_stops.location`.
  - Novo módulo de ingestão GTFS em `apps/api/src/modules/transport/gtfs_ingestion.py` com pipeline:
    - hash check (SHA-256) por ZIP ou diretório GTFS;
    - carga em tabelas de staging;
    - swap atômico por rename;
    - upsert em `dataset_versions` com `is_current=true` apenas para versão vigente.
  - Export público do módulo em `apps/api/src/modules/transport/__init__.py`.
  - Script operacional criado: `scripts/ingest_gtfs_postgis.py`.
  - Teste focado criado: `apps/api/tests/test_phase3_gtfs_ingestion.py` cobrindo ingestão inicial + skip por hash + verificação de `dataset_versions` e GIST.

- Milestone policy note:
  - O marco `M3.2` foi implementado e validado tecnicamente, mas **não foi marcado como concluído no `PRD.md`** sem confirmação explícita do usuário.

- Validation status update:
  - `python -m alembic upgrade head` aplicado com sucesso até `20260318_0003`.
  - `cd apps/api && pytest tests/test_phase3_gtfs_ingestion.py` -> `1 passed`.
  - Ingestão real #1 (`scripts/ingest_gtfs_postgis.py --gtfs-dir data_cache/gtfs`):
    - `skipped=false`
    - `row_counts.gtfs_stops=22093`
    - `elapsed_seconds=19.786`
  - Ingestão real #2 (mesma fonte):
    - `skipped=true`
    - `elapsed_seconds=0.131` (hash check no-op < 2s)
  - Query PostGIS:
    - `SELECT count(*) FROM gtfs_stops` -> `22093` (ordem de grandeza esperada ~22k no PRD).
    - `SELECT count(*) FROM dataset_versions WHERE dataset_type='gtfs_sptrans' AND is_current=true` -> `1`.

## 2026-03-18 - Fase 3 (M3.3) implementado e validado

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/release-config-management/SKILL.md`
- Scope executed:
  - Nova migration Alembic `infra/migrations/versions/20260318_0004_geosampa_ingestion_schema.py` com tabelas:
    - `geosampa_metro_stations`
    - `geosampa_trem_stations`
    - `geosampa_bus_stops`
    - `geosampa_bus_terminals`
    - `geosampa_bus_corridors`
    - e indices GIST de geometria para todas.
  - Novo modulo `apps/api/src/modules/transport/geosampa_ingestion.py` com pipeline de ingestao:
    - tentativa primaria via `ogr2ogr` para cada dataset GeoSampa de transporte;
    - fallback de compatibilidade para leitura direta de GeoPackage quando `ogr2ogr` nao estiver disponivel/compativel no ambiente;
    - validacao obrigatoria `ST_IsValid` em todas as geometrias de staging antes do swap;
    - swap atomico de staging para tabelas de producao;
    - registro em `dataset_versions` com `is_current=true` apenas para versao vigente.
  - Script operacional criado: `scripts/ingest_geosampa_postgis.py`.
  - Export do modulo atualizado em `apps/api/src/modules/transport/__init__.py`.
  - Testes focados adicionados em `apps/api/tests/test_phase3_geosampa_ingestion.py` cobrindo:
    - ingestao + registro em `dataset_versions` + hash skip;
    - falha quando `ST_IsValid` detecta geometria invalida.

- Milestone policy note:
  - M3.3 foi implementado e validado tecnicamente, mas nao foi marcado como concluido no `PRD.md` sem confirmacao explicita do usuario.

- Validation status update:
  - `python -m alembic upgrade head` aplicado ate `20260318_0004` com sucesso.
  - `python -m ruff check apps/api/src/modules/transport/geosampa_ingestion.py apps/api/tests/test_phase3_geosampa_ingestion.py scripts/ingest_geosampa_postgis.py` -> `All checks passed!`.
  - `python -m pytest -q apps/api/tests/test_phase3_geosampa_ingestion.py apps/api/tests/test_phase3_gtfs_ingestion.py` -> `3 passed`.
  - Ingestao real #1:
    - `python scripts/ingest_geosampa_postgis.py --dataset-type geosampa_transport --geosampa-dir data_cache/geosampa`
    - resultado: `skipped=false`, `elapsed_seconds=6.644`
    - contagens:
      - `geosampa_metro_stations=94`
      - `geosampa_trem_stations=109`
      - `geosampa_bus_stops=22380`
      - `geosampa_bus_terminals=50`
      - `geosampa_bus_corridors=45`
  - Ingestao real #2 (mesmos dados):
    - resultado: `skipped=true`, `elapsed_seconds=0.07`.
  - Verificacoes SQL finais:
    - `SELECT count(*) FROM geosampa_metro_stations` -> `94` (dado real SP, criterio PRD M3.3).
    - `SELECT count(*) FROM dataset_versions WHERE dataset_type='geosampa_transport' AND is_current=true` -> `1`.
    - `SELECT count(*) FROM geosampa_metro_stations WHERE NOT ST_IsValid(geometry)` -> `0`.

## 2026-03-18 - Marcacao de milestone M3.3

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/release-config-management/SKILL.md`
- Scope executed:
  - Com confirmacao explicita do usuario, o `PRD.md` foi atualizado para marcar o marco `M3.3` como concluido.
  - Progress Tracker da Fase 3 foi atualizado para refletir `M3.1-M3.3 concluidos`.

## 2026-03-18 - Fase 3 (M3.4) implementado e validado

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/release-config-management/SKILL.md`
- Scope executed:
  - Novo adapter `apps/api/src/modules/transport/valhalla_adapter.py` com:
    - `ValhallaAdapter.route(origin, dest, costing) -> RouteResult`;
    - `ValhallaAdapter.isochrone(origin, costing, contours_minutes) -> dict GeoJSON`;
    - cache Redis para `route` com chave canonica `valhalla:{costing}:{lat1}:{lon1}:{lat2}:{lon2}`;
    - TTL de cache de 24h (`86400` segundos);
    - timeout e mapeamento de `httpx.TimeoutException` para `ValhallaCommunicationError`.
  - Export publico do adapter em `apps/api/src/modules/transport/__init__.py`.
  - Testes focados adicionados em `apps/api/tests/test_phase3_valhalla_adapter.py` cobrindo:
    - cache hit na segunda chamada sem novo request HTTP;
    - formato da chave de cache e TTL de 24h;
    - mapeamento de timeout para erro de dominio;
    - retorno do payload GeoJSON em `isochrone`.
  - Dependencia adicionada em `requirements.txt`: `httpx>=0.27`.

- Milestone policy note:
  - M3.4 foi implementado e validado tecnicamente, mas nao foi marcado como concluido no `PRD.md` sem confirmacao explicita do usuario.

- Validation status update:
  - `cd apps/api && python -m pytest -q tests/test_phase3_valhalla_adapter.py` -> `3 passed`.

## 2026-03-18 - Fase 3 (M3.4) verificacao de performance PRD (runtime real)

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/release-config-management/SKILL.md`
- Scope executed:
  - Ambiente de validacao local levantado para Valhalla em `http://localhost:8002` com Redis local ja ativo.
  - Execucao do script de verificacao `scripts/verify_m3_4_valhalla.py` contra instancia real do Valhalla.
  - Verificacao objetiva do criterio M3.4 no PRD: primeira chamada (rede) e segunda chamada (cache Redis).

- Validation status update:
  - Run aprovado (mesmo comando abaixo):
    - `cd apps/api && ..\\..\\.venv\\Scripts\\python.exe ..\\..\\scripts\\verify_m3_4_valhalla.py`
    - resultado:
      - `1st call = 40.8 ms` (`< 300 ms`) -> PASS
      - `2nd call (cache) = 3.4 ms` (`< 50 ms`) -> PASS
      - saida final: `M3.4 verification PASSED`
  - Observacao operacional:
    - Uma execucao imediatamente apos startup apresentou cold start (`1st call = 698.4 ms`), mas a execucao de verificacao subsequente (warm) passou integralmente com folga nos limites do PRD.

## 2026-03-18 - Fase 3 (M3.5) implementado e validado

- Required docs opened:
  - `PRD.md`
  - `BEST_PRACTICES.md`
  - `SKILLS_README.md`
- Skill used:
  - `skills/release-config-management/SKILL.md`
- Scope executed:
  - Novo adapter `apps/api/src/modules/transport/otp_adapter.py` com:
    - `OTPAdapter.plan(origin, dest, trip_datetime) -> TransitItinerary`;
    - parse de multiplos itinerarios de OTP e ordenacao por menor duracao;
    - parse de legs por itinerario com extracao de linhas (`routeShortName`, `routeLongName` ou `headsign`);
    - mapeamento de `leg.mode` para `modal_types` canonicos (`walk`, `bus`, `metro`, `train`, etc.);
    - timeout de 5s com mapeamento de `httpx.TimeoutException` para `OTPCommunicationError`.
  - Fallback de endpoint implementado para maior compatibilidade de ambiente:
    - tenta `GET /plan` e, em `404`, tenta `GET /otp/routers/default/plan`.
  - Export publico atualizado em `apps/api/src/modules/transport/__init__.py` para:
    - `OTPAdapter`, `OTPCommunicationError`, `TransitItinerary`, `TransitOption`, `TransitLeg`.
  - Testes focados criados em `apps/api/tests/test_phase3_otp_adapter.py` cobrindo:
    - retorno de multiplos itinerarios ordenados por duracao;
    - mapeamento de `leg.mode` para `modal_types` e extracao de linhas;
    - timeout mapeado para erro de dominio;
    - fallback de rota para `/otp/routers/default/plan` quando `/plan` responde `404`.

- Milestone policy note:
  - M3.5 foi implementado e validado tecnicamente, mas nao foi marcado como concluido no `PRD.md` sem confirmacao explicita do usuario.

- Validation status update:
  - `cd apps/api && python -m pytest -q tests/test_phase3_otp_adapter.py` -> `3 passed`.
