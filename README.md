# Find Ideal Estate (MVP local)

![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)

## Estado atual (2026-04-24)

| Componente | Status |
|---|---|
| Fases 0–5 (backend) | ✅ Concluídas |
| Fase 6 — Dashboard | 🔄 Em progresso (M6.1–M6.2 ✅; M6.7–M6.8 ✅; M6.3–M6.6 pendentes) |
| Fase 7 — Prewarm noturno | ⬜ Não iniciada |
| Fase 8 — Auth + Créditos + Stripe | 🔄 Em progresso (M8.1 ✅; demais pendentes) |
| Frontend FE0–FE7 | ✅ Concluídas |
| Frontend FE8 — Auth/Favoritos | 🔄 Em progresso |

## Funcionalidades implementadas

- Jornada guiada: configuração → busca de transporte → geração de zonas → comparação → imóveis → dashboard
- Geração de isócronas via Valhalla (transporte público, a pé, carro)
- Enriquecimento de zonas: segurança, área verde, alagamento, POIs (Mapbox)
- Scraping de imóveis: QuintoAndar, ZapImóveis, VivaReal
- Deduplicação de imóveis entre plataformas
- Dashboard de preços com histórico e distribuição por faixas
- Heatmap de segurança pública
- **Auth** — registro e login por e-mail/senha, sessões por cookie HTTP-only
- **Favoritos de imóveis** — salvar/listar/remover; criação manual por URL
- **Favoritos de zonas** — salvar/listar/remover; analytics citywide integrado
- Trace de rota do ponto de transporte selecionado

## Pré-requisitos

- Docker Desktop
- `data_cache/` preenchido
- `.env` baseado em `.env.example`

## Subir API/UI

```bash
docker compose up -d api ui
```

Após mudança de código no backend:

```bash
docker compose up -d --build api
```

- Health API: `GET http://localhost:8000/health`
- UI: http://localhost:5173

## Migrations

```bash
alembic upgrade head
```

Migrations relevantes recentes:
- `20260412_0022` — `listing_usage_type` por anúncio
- `20260412_0023` — auth: `user_sessions`, `password_hash` em `users`
- `20260413_0024` — `user_listing_favorites`
- `20260422_0025` — `user_zone_favorites`

## Enriquecimento verde (v8 tiled)

O adapter de enriquecimento usa `green_tiles_v3/tile_index.csv`.
Se o `tile_index.csv` não existir, o pipeline tenta gerar automaticamente a partir de:
- `data_cache/geosampa/SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg`

## Smoke E2E (M8)

Regra: qualquer fluxo com Playwright roda no container `api`.

```powershell
pwsh ./scripts/e2e_smoke_dataset_a.ps1
```

Esse smoke valida:
- criação de `run_id`
- geração e seleção de zona
- detalhe de zona
- scraping de listings
- finalização
- exports finais (`json/csv/geojson`)
- qualidade mínima: `FINAL_COUNT > 0`, `BAD_COORDS = 0`, `BAD_STATE = 0`

## Logs por run

- `runs/<run_id>/status.json`
- `runs/<run_id>/logs/events.jsonl` — eventos estruturados por `stage`; em erro: `error_type` + mensagem

## Recuperação de falhas

1. Consultar status: `GET /runs/{run_id}/status`
2. Inspecionar logs: `runs/<run_id>/logs/events.jsonl`
3. Reexecutar smoke: `pwsh ./scripts/e2e_smoke_dataset_a.ps1`

## Estrutura do monorepo

```
find-ideal-estate/
  apps/
    web/          ← Vite + React (MapLibre, TanStack Query, Zustand, shadcn/ui)
    api/          ← FastAPI + Dramatiq + Alembic
  packages/
    contracts/    ← DTOs compartilhados (nunca modelos internos)
  infra/
    docker/
    migrations/   ← Alembic
    seeds/
  skills/         ← Skills de agente (develop-frontend, playwright, etc.)
```
