---
name: ops-observability-runbook
description: Standardize operational observability (logs/metrics/health) and incident runbooks for app+indexer+RPC+VRF, including stuck phases, indexer lag, and DB outages. Use when touching infra, runtime config, indexer loops, workers/automation, or production readiness.
---

# Ops, Observability & Runbook

## When to use
- Any change to:
  - indexer behavior or RPC/WS usage
  - automation/worker that advances phases or requests draw
  - production deployment config (env, containers, restart policies)
  - logging/monitoring/health endpoints

## Goal (Definition of Done)
- ✅ Health checks answer: "day opened?", "current phase?", "VRF responded?", "indexer lag?"
- ✅ Alerts exist for: stuck phase, indexer errors/lag, DB down, VRF pending too long.
- ✅ Logs are structured and redact secrets.
- ✅ Runbook has recovery steps for top incidents.

## Minimum telemetry

### Logs (structured JSON)
Include fields:
- `service` (app/indexer/worker)
- `chainId`
- `dayId` / `monthId` (when relevant)
- `txHash` (when sending tx)
- `blockNumber` (when indexing)
- `requestId` / `traceId`

### Metrics (minimum set)
- indexer:
  - head block, last indexed block, lag
  - reorg count, replay count
  - RPC errors (HTTP/WS), reconnects
- app/api:
  - request latency/error rate
  - auth failures / rate limit triggers
- game ops:
  - stuck phase duration
  - draw requests pending time
  - repeated critical reverts (NOT_IN_PHASE, INSUFFICIENT_*)

### Health endpoints
- `/health` basic liveness
- `/health/ready` readiness (DB reachable, indexer running)
- `/health/game` (derived state):
  - current dayId, phase, deadline
  - VRF pending? last draw result?

## Alerting (recommended)
Trigger alerts on:
- indexer lag > threshold for > N minutes
- stuck phase > threshold
- VRF pending > threshold
- DB unavailable
- repeated RPC disconnects/errors

## Runbook: incident playbooks (minimum)

### Indexer lag / inconsistent
1) Check RPC/WS stability
2) Restart indexer
3) If persistent: switch provider via env, restart
4) Re-sync strategy (as supported by indexer)
5) Validate DB projections

### VRF pending too long
1) Verify subscription funding
2) Verify consumer registration
3) Verify callbackGasLimit/keyHash/coordinator for chain
4) Re-queue draw request if contract supports retry
5) Escalate to manual progress/fallback

### Stuck phase
1) Confirm phase + deadline
2) Call public `updatePhase` / progress function
3) If automation exists, check worker/upkeep logs and keys/funding

## Security constraints
- Never log secrets, full signatures, full nonces, tokens, private keys.
- Env vars are runtime-only; do not bake secrets into builds.

## Testing checklist
- Smoke tests for health endpoints
- Chaos-ish tests (optional):
  - simulate RPC downtime (reconnect path)
  - DB unavailable (readiness fails)
  - replay/reorg safety (idempotent handlers)
