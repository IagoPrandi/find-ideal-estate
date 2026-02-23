# Skills Catalog

Este arquivo indexa todas as skills disponíveis em `\skills`.

## Como escolher uma skill

1. Identifique o tipo de tarefa (auth, indexer, batch ops, observability, etc.).
2. Leia a seção **When to use** (quando existir) da skill candidata.
3. Use **apenas uma** skill como primária; use outra apenas como apoio se estiver explicitamente indicado.

## Índice

- [a2-key-aggregation](#a2-key-aggregation) — Implement/review the A2 scalable winner model using canonical playerKey per WinMode + O(1) aggregated counters & winner counts (no loops over players) for daily/monthly commit→reveal→draw→claim.
- [automation-upkeep](#automation-upkeep) — Implement deterministic, idempotent phase automation using Chainlink-style checkUpkeep/performUpkeep for updatePhase/requestDraw/openDay/closeDay, with safe retries and manual fallback.
- [checkout-batch-flow](#checkout-batch-flow) — Implement/review one-transaction checkout() batching (feed → commit → buyRelics → applyRelics → monthly action) with deterministic validation, canonical ordering, and exact payment reconciliation (refund extra).
- [daily-turn-flow](#daily-turn-flow) — Enforce the canonical daily flow (OPEN/SHOP → COMMIT → REVEAL → DRAW → CLAIM → CLOSE) with strict phase checks, commit/reveal invariants, VRF lifecycle, and event expectations for indexer/UI.
- [develop-frontend](#develop-frontend) — Review, debug and elevate AI-generated web frontends: layout stability, responsiveness, accessibility, visual consistency (tokens), UI states, and baseline performance/SEO.
- [develop-web-game](#develop-web-game) — Build games in small steps and validate every change. Treat each iteration as: implement → act → pause → observe → adjust.
- [frontend-contract-sim](#frontend-contract-sim) — Standardize frontend transaction flows with viem/wagmi using simulation-first, deterministic error mapping, and safe logging. Use for checkout, commit/reveal, buy/apply relics, draws, and claims.
- [indexer-reorg-idempotent](#indexer-reorg-idempotent) — Enforce reorg-aware, idempotent indexing with stable event identity keys, replay safety, and clear optimistic vs confirmed consistency tiers. Use when touching DB writes or replay logic.
- [ops-observability-runbook](#ops-observability-runbook) — Standardize operational observability (logs/metrics/health) and incident runbooks for app+indexer+RPC+VRF, including stuck phases, indexer lag, and DB outages. Use when touching infra, runtime config, indexer loops, workers/automation, or production readiness.
- [playwright](#playwright) — Drive a real browser from the terminal using `playwright-cli`. Prefer the bundled wrapper script so the CLI works even when it is not globally installed. Treat this skill as CLI-first automation. Do not pivot to `@playwright/test` unless the user explicitly asks for test files.
- [ponder-indexer-events](#ponder-indexer-events) — Maintain Ponder event coverage + Postgres projections for the game. Use when adding/modifying on-chain events, handler logic, schema migrations, or API alignment.
- [release-config-management](#release-config-management) — Standardize release & configuration management across chains/environments: deployments/<chainId>.json, env/runtime secrets, ABI/schema versioning, idempotent migrations, and reproducible scripts. Use when touching deploy scripts, env vars, DB migrations, ABI/events, or production setup.
- [relics-batch-ops](#relics-batch-ops) — Standardize buy/apply relic operations with deterministic ordering, stock & fee accounting, inventory decrements, slot compatibility rules, and soldout handling. Use in Shop/Relic managers and checkout steps.
- [resources-economy](#resources-economy) — Apply internal Resources rules (earn/redeem/get) with authorization, max supply caps, minimum redeem thresholds, and deterministic validation. Use when touching token economy or redemption logic.
- [security-threat-checklist](#security-threat-checklist) — Apply project security requirements (threat model + Web2/Web3 checklists + mandatory scans/tests) whenever surface area changes: auth, contracts, indexer, API, infra, or admin ops.
- [upgradeability-governance](#upgradeability-governance) — Enforce safe upgrade patterns (ERC-7201 namespaced storage, initializer discipline, authorizeUpgrade governance, and upgrade tests). Use when touching proxy/upgradeable contracts, storage layout, admin roles, or deploy scripts.
- [web2-wallet-auth](#web2-wallet-auth) — Implement or review Web2 wallet-based auth (SIWE/EIP-712) with nonce+expiry+anti-replay, ERC-1271 support, rate limiting, and safe logging. Use when touching login/session/authz endpoints or any signature verification off-chain.

## a2-key-aggregation

**Título:** A2 Key Aggregation (O(1) Winners)

**Descrição:** Implement/review the A2 scalable winner model using canonical playerKey per WinMode + O(1) aggregated counters & winner counts (no loops over players) for daily/monthly commit→reveal→draw→claim.

**Arquivo:** `skills/a2-key-aggregation/SKILL.md`

**Quando usar (gatilhos):**
- Touching **reveal**, **draw/VRF callback**, **claim**, **win modes**, or anything that might reintroduce loops over players.
- Adding new win conditions, “order ignored” variants, or changing how pot splits/winner counts are computed.

## automation-upkeep

**Título:** Automation Upkeep (Deterministic + Idempotent)

**Descrição:** Implement deterministic, idempotent phase automation using Chainlink-style checkUpkeep/performUpkeep for updatePhase/requestDraw/openDay/closeDay, with safe retries and manual fallback.

**Arquivo:** `skills/automation-upkeep/SKILL.md`

**Quando usar (gatilhos):**
- Adding/adjusting automated phase transitions, VRF request triggers, or scheduled open/close logic.
- Any time you touch `checkUpkeep`, `performUpkeep`, or “keeper/cron” responsibilities.

## checkout-batch-flow

**Título:** Checkout Batch Flow (1 Tx, Canonical Order)

**Descrição:** Implement/review one-transaction checkout() batching (feed → commit → buyRelics → applyRelics → monthly action) with deterministic validation, canonical ordering, and exact payment reconciliation (refund extra).

**Arquivo:** `skills/checkout-batch-flow/SKILL.md`

**Quando usar (gatilhos):**
- Editing `checkout(CheckoutParams)` in contracts or the UI that builds the cart.
- Touching pricing, fees, stock, slots, or monthly action constraints.

## daily-turn-flow

**Título:** Daily Turn Flow (Canonical Phases)

**Descrição:** Enforce the canonical daily flow (OPEN/SHOP → COMMIT → REVEAL → DRAW → CLAIM → CLOSE) with strict phase checks, commit/reveal invariants, VRF lifecycle, and event expectations for indexer/UI.

**Arquivo:** `skills/daily-turn-flow/SKILL.md`

**Quando usar (gatilhos):**
- Any change to daily phases, deadlines, commit/reveal/draw/claim functions, or UI/Indexer logic that depends on phases.

**Invariantes / regras centrais:**
- Feed payment required before “active” participation that day.
- Commit required before reveal.
- Reveal required before being counted for winners (A2 counters update on reveal).
- Draw must complete before any claim.
- Claim is per mode (if multiple win modes are enabled), and each mode has its own claimed flag.

## develop-frontend

**Título:** Develop Frontend (Qualidade de UI para código gerado por IA)

**Descrição:** Revisar, depurar e elevar a qualidade de frontends (web) gerados por IA, garantindo layout estável (sem overflow), responsividade, acessibilidade, consistência visual via tokens, estados de UI completos e baseline de performance/SEO.

**Arquivo:** `skills/develop-frontend/SKILL.md`

**Quando usar (gatilhos):**
- Quando receber UI/landing/dashboard gerada por IA e precisar torná-la consistente e pronta para produção.
- Quando houver bugs de layout/spacing/alinhamento, responsividade, contraste/a11y, ou inconsistência entre componentes.
- Antes de “fechar” um design system (tokens) e padronizar estados (hover/focus/disabled/loading/empty/error).

## develop-web-game

**Título:** Develop Web Game

**Descrição:** Build games in small steps and validate every change. Treat each iteration as: implement → act → pause → observe → adjust.

**Arquivo:** `skills/develop-web-game/SKILL.md`

**Quando usar:** consulte a SKILL.md (não há seção explícita de *When to use*).

## frontend-contract-sim

**Título:** Frontend Contract Simulation (viem/wagmi)

**Descrição:** Standardize frontend transaction flows with viem/wagmi using simulation-first, deterministic error mapping, and safe logging. Use for checkout, commit/reveal, buy/apply relics, draws, and claims.

**Arquivo:** `skills/frontend-contract-sim/SKILL.md`

**Quando usar (gatilhos):**
- Any UI flow that sends transactions or estimates costs.
- Error handling or user messaging around reverts.

## indexer-reorg-idempotent

**Título:** Indexer Reorg + Idempotency

**Descrição:** Enforce reorg-aware, idempotent indexing with stable event identity keys, replay safety, and clear optimistic vs confirmed consistency tiers. Use when touching DB writes or replay logic.

**Arquivo:** `skills/indexer-reorg-idempotent/SKILL.md`

**Quando usar (gatilhos):**
- Adding/changing event handlers, DB schema, or replay/re-sync behavior.
- Any modification to how you store logs, claims, or day/month aggregates.

## ops-observability-runbook

**Título:** Ops, Observability & Runbook

**Descrição:** Standardize operational observability (logs/metrics/health) and incident runbooks for app+indexer+RPC+VRF, including stuck phases, indexer lag, and DB outages. Use when touching infra, runtime config, indexer loops, workers/automation, or production readiness.

**Arquivo:** `skills/ops-observability-runbook/SKILL.md`

**Quando usar (gatilhos):**
- Any change to:
- indexer behavior or RPC/WS usage
- automation/worker that advances phases or requests draw
- production deployment config (env, containers, restart policies)
- logging/monitoring/health endpoints

## playwright

**Título:** Playwright CLI Skill

**Descrição:** Drive a real browser from the terminal using `playwright-cli`. Prefer the bundled wrapper script so the CLI works even when it is not globally installed. Treat this skill as CLI-first automation. Do not pivot to `@playwright/test` unless the user explicitly asks for test files.

**Arquivo:** `skills/playwright/SKILL.md`

**Quando usar:** consulte a SKILL.md (não há seção explícita de *When to use*).

## ponder-indexer-events

**Título:** Ponder Indexer Events (Coverage + Projections)

**Descrição:** Maintain Ponder event coverage + Postgres projections for the game. Use when adding/modifying on-chain events, handler logic, schema migrations, or API alignment.

**Arquivo:** `skills/ponder-indexer-events/SKILL.md`

**Quando usar (gatilhos):**
- Contracts changed events/fields.
- You add new game mechanics requiring new projections or endpoints.

## release-config-management

**Título:** Release & Config Management (Multi-chain + Multi-env)

**Descrição:** Standardize release & configuration management across chains/environments: deployments/<chainId>.json, env/runtime secrets, ABI/schema versioning, idempotent migrations, and reproducible scripts. Use when touching deploy scripts, env vars, DB migrations, ABI/events, or production setup.

**Arquivo:** `skills/release-config-management/SKILL.md`

**Quando usar (gatilhos):**
- Any PR touching:
- deploy scripts or addresses
- env vars or runtime config
- ABI/events/schema
- dbmate migrations / Kysely types
- production or testnet rollout

## relics-batch-ops

**Título:** Relics Batch Operations (Buy + Apply)

**Descrição:** Standardize buy/apply relic operations with deterministic ordering, stock & fee accounting, inventory decrements, slot compatibility rules, and soldout handling. Use in Shop/Relic managers and checkout steps.

**Arquivo:** `skills/relics-batch-ops/SKILL.md`

**Quando usar (gatilhos):**
- Editing `buyRelics`, `applyRelics`, shop stock generation, fees, inventory/slots, or soldout-triggered relic behavior.

## resources-economy

**Título:** Resources Economy (Internal Token)

**Descrição:** Apply internal Resources rules (earn/redeem/get) with authorization, max supply caps, minimum redeem thresholds, and deterministic validation. Use when touching token economy or redemption logic.

**Arquivo:** `skills/resources-economy/SKILL.md`

**Quando usar (gatilhos):**
- Editing `earnResources`, `redeemResources`, supply caps, or UI that shows balances/redemption.

## security-threat-checklist

**Título:** Security Threat Checklist (DoD Requirement)

**Descrição:** Apply project security requirements (threat model + Web2/Web3 checklists + mandatory scans/tests) whenever surface area changes: auth, contracts, indexer, API, infra, or admin ops.

**Arquivo:** `skills/security-threat-checklist/SKILL.md`

**Quando usar (gatilhos):**
- Any PR that changes:
- external/public endpoints (HTTP or on-chain functions)
- auth/signatures/login
- payout/claim/withdraw
- upgradeability/storage
- indexer/DB writes or replay logic
- infra/secrets/config

## upgradeability-governance

**Título:** Upgradeability + Governance (ERC-7201)

**Descrição:** Enforce safe upgrade patterns (ERC-7201 namespaced storage, initializer discipline, authorizeUpgrade governance, and upgrade tests). Use when touching proxy/upgradeable contracts, storage layout, admin roles, or deploy scripts.

**Arquivo:** `skills/upgradeability-governance/SKILL.md`

**Quando usar (gatilhos):**
- Any contract is upgradeable (proxy) OR any PR touches:
- storage layout
- initializer/reinitializer
- upgrade authorization / admin roles
- deploy/upgrade scripts
- contract ownership/governance configuration

## web2-wallet-auth

**Título:** Web2 Wallet Auth (SIWE/EIP-712 + ERC-1271)

**Descrição:** Implement or review Web2 wallet-based auth (SIWE/EIP-712) with nonce+expiry+anti-replay, ERC-1271 support, rate limiting, and safe logging. Use when touching login/session/authz endpoints or any signature verification off-chain.

**Arquivo:** `skills/web2-wallet-auth/SKILL.md`

**Quando usar (gatilhos):**
- Any change to: login routes, session issuance, signature verification, nonce storage, auth middleware, or endpoints that accept wallet identities.
- Any addition of privileged Web2 roles (admin/ops/keeper) or routes that accept IDs from the client.
