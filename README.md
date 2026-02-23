# Imovel Ideal (MVP local)

Execução local do pipeline:
- pontos de referência -> zonas -> detalhe de zona -> scraping -> ranking -> exports finais.

## Pré-requisitos
- Docker Desktop
- `data_cache/` preenchido
- `.env` com `MAPBOX_ACCESS_TOKEN`

## Subir API/UI

- `docker compose up -d api ui`
- Health API: `GET http://localhost:8000/health`
- UI: http://localhost:5173

## Smoke E2E (M8)

Regra: qualquer fluxo com Playwright roda no container `api`.

Execute:

- `pwsh ./scripts/e2e_smoke_dataset_a.ps1`

Esse smoke valida:
- criação de `run_id`
- geração e seleção de zona
- detalhe de zona
- scraping de listings
- finalização
- exports finais (`json/csv/geojson`)
- qualidade mínima do output final:
  - `FINAL_COUNT > 0`
  - `BAD_COORDS = 0`
  - `BAD_STATE = 0`

## Logs por run

Cada run grava:
- `runs/<run_id>/status.json`
- `runs/<run_id>/logs/events.jsonl`

`events.jsonl` contém eventos estruturados por etapa (`stage`) e, em erro, `error_type` + mensagem.

## Recuperação de falhas

1. Consultar status:
- `GET /runs/{run_id}/status`

2. Inspecionar logs:
- `runs/<run_id>/logs/events.jsonl`

3. Reexecutar smoke:
- `pwsh ./scripts/e2e_smoke_dataset_a.ps1`
