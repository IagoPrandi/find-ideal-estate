# AGENTS.md

## General (MUST FOLLOW)

- Always open **PRD.md** before working.
- Always confirm (in the work log / PR description) that you opened the required markdown documents.
- Always update the **Progress Tracker** when you finish a milestone.
- Always mark (tick) the corresponding milestone ONLY after user confirmation.
- Never create useless files that do not improve functionality, security, or project understanding.
- Always open **SKILLS_README.md** and use a skill to do and complete the task. You just can't use any available skill if there aren't one to task.

## Routing: pick skills by change scope

Always open **SKILLS_README.md** and find a skill to done the task. You just can't use a available skill if there aren't one to task.

## Cursor Cloud specific instructions

### Architecture overview

This is a monorepo for **Find Ideal Estate** (Imóvel Ideal), a map-driven real estate decision platform for São Paulo. Key components:

| Service | Tech | Port | Purpose |
|---|---|---|---|
| `apps/api` | FastAPI + Uvicorn | 8000 | Backend API (Python ≥ 3.11) |
| `apps/web` | Next.js 14 | 3000 | New frontend (TypeScript) |
| `ui/` | Vite + React | 5173 | Legacy frontend (TypeScript) |
| `postgres` | PostGIS 16 | 5432 | Database (via Docker) |
| `redis` | Redis 7 | 6379 | Cache/broker (via Docker) |

### Required infrastructure (Docker)

PostgreSQL (PostGIS) and Redis **must** run before the API. Start them with:

```bash
docker compose -p onde_morar up -d postgres redis
```

### Running the API natively (not in Docker)

The API runs best natively during development. The `.env` file must use `localhost` hostnames (not Docker-internal ones like `postgres` or `redis`). Key environment variables:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/find_ideal_estate
REDIS_URL=redis://localhost:6379/0
MAPBOX_ACCESS_TOKEN=<any-non-empty-value>
MAPTILER_API_KEY=<any-non-empty-value>
VALHALLA_URL=http://localhost:8002
OTP_URL=http://localhost:8080
```

The `PYTHONPATH` must include both `apps/api` and `apps/api/src` and `packages/contracts`:

```bash
export PYTHONPATH="/workspace/apps/api:/workspace/apps/api/src:/workspace/packages/contracts"
```

Start the API with:

```bash
cd /workspace/apps/api && uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### Database migrations

Run Alembic migrations after starting postgres:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/find_ideal_estate"
alembic upgrade head
```

### Running tests

- **Backend (pytest):** `cd apps/api && pytest tests/ -v --tb=short` (set env vars and PYTHONPATH as above). Three test files (`test_phase4_zone_reuse.py`, `test_phase5_scraper_health.py`, `test_phase5_scraping_lock.py`) have pre-existing Dramatiq actor registration collection errors — ignore them with `--ignore`.
- **Legacy UI (vitest):** `cd ui && npx vitest run --config vitest.config.ts`
- **Next.js (typecheck):** `cd apps/web && npx tsc --noEmit`

### Linting

- **Python:** `ruff check apps/api/src/ packages/contracts/` (existing lint warnings are pre-existing)
- **Legacy UI:** `cd ui && npx eslint . --ext ts,tsx --max-warnings 0` (existing errors are pre-existing)

### Non-obvious gotchas

- `requirements.txt` is stored in Git LFS — run `git lfs pull` if it shows an LFS pointer instead of actual dependencies.
- The `MAPBOX_ACCESS_TOKEN` and `MAPTILER_API_KEY` are required by Pydantic settings validation. Use any non-empty string if you don't have real keys — the API still starts and core CRUD endpoints work.
- Valhalla and OTP are optional external services. The API starts fine without them; routes that depend on them will fail gracefully.
- `~/.local/bin` must be on PATH for pip-installed CLI tools (`uvicorn`, `alembic`, `pytest`, `ruff`).