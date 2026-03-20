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
- [cloudflare-deploy](#cloudflare-deploy) — Deploy applications and infrastructure to Cloudflare using Workers, Pages, and related platform services (KV, D1, R2, Durable Objects, Queues, etc.).
- [develop-frontend](#develop-frontend) — Review, debug and elevate AI-generated web frontends: layout stability, responsiveness, accessibility, visual consistency (tokens), UI states, and baseline performance/SEO.
- [develop-web-game](#develop-web-game) — Build games in small steps and validate every change. Treat each iteration as: implement → act → pause → observe → adjust.
- [indexer-reorg-idempotent](#indexer-reorg-idempotent) — Enforce reorg-aware, idempotent indexing with stable event identity keys, replay safety, and clear optimistic vs confirmed consistency tiers. Use when touching DB writes or replay logic.
- [linear](#linear) — Manage issues, projects & team workflows in Linear via the Linear MCP server. Use when the user wants to read, create, or update tickets in Linear.
- [pdf](#pdf) — Read, create, or review PDF files using `reportlab`, `pdfplumber`, and `pypdf`. Prefer visual checks by rendering pages with Poppler.
- [playwright](#playwright) — Drive a real browser from the terminal using `playwright-cli`. Prefer the bundled wrapper script so the CLI works even when it is not globally installed. Treat this skill as CLI-first automation. Do not pivot to `@playwright/test` unless the user explicitly asks for test files.
- [playwright-interactive](#playwright-interactive) — Persistent browser and Electron interaction through `js_repl` for fast iterative UI debugging. Keep Playwright handles alive across iterations for functional and visual QA.
- [ponder-indexer-events](#ponder-indexer-events) — Maintain Ponder event coverage + Postgres projections for the game. Use when adding/modifying on-chain events, handler logic, schema migrations, or API alignment.
- [release-config-management](#release-config-management) — Standardize release & configuration management across chains/environments: deployments/<chainId>.json, env/runtime secrets, ABI/schema versioning, idempotent migrations, and reproducible scripts. Use when touching deploy scripts, env vars, DB migrations, ABI/events, or production setup.
- [render-deploy](#render-deploy) — Deploy applications to Render by analyzing codebases, generating render.yaml Blueprints, and creating services via MCP tools.
- [security-threat-checklist](#security-threat-checklist) — Apply project security requirements (threat model + Web2/Web3 checklists + mandatory scans/tests) whenever surface area changes: auth, contracts, indexer, API, infra, or admin ops.
- [upgradeability-governance](#upgradeability-governance) — Enforce safe upgrade patterns (ERC-7201 namespaced storage, initializer discipline, authorizeUpgrade governance, and upgrade tests). Use when touching proxy/upgradeable contracts, storage layout, admin roles, or deploy scripts.
- [vercel-deploy](#vercel-deploy) — Deploy applications and websites to Vercel. Always deploys as preview unless production is explicitly requested. Handles CLI auth and fallback deploy script.
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

## cloudflare-deploy

**Título:** Cloudflare Deploy (Workers, Pages & Platform)

**Descrição:** Deploy applications and infrastructure to Cloudflare using Workers, Pages, and related platform services (KV, D1, R2, Durable Objects, Queues, etc.). Use when deploying, hosting, or publishing a project on Cloudflare.

**Arquivo:** `skills/cloudflare-deploy/SKILL.md`

**Quando usar (gatilhos):**
- User wants to deploy, host, publish, or set up a project on Cloudflare.
- Choosing between Workers, Pages, D1, R2, KV, Durable Objects, or other Cloudflare products.
- Setting up `wrangler` authentication or CI/CD with `CLOUDFLARE_API_TOKEN`.


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

## indexer-reorg-idempotent

**Título:** Indexer Reorg + Idempotency

**Descrição:** Enforce reorg-aware, idempotent indexing with stable event identity keys, replay safety, and clear optimistic vs confirmed consistency tiers. Use when touching DB writes or replay logic.

**Arquivo:** `skills/indexer-reorg-idempotent/SKILL.md`

**Quando usar (gatilhos):**
- Adding/changing event handlers, DB schema, or replay/re-sync behavior.
- Any modification to how you store logs, claims, or day/month aggregates.

## linear

**Título:** Linear (Issue & Project Management)

**Descrição:** Manage issues, projects & team workflows in Linear via the Linear MCP server. Use when the user wants to read, create, or update tickets in Linear.

**Arquivo:** `skills/linear/SKILL.md`

**Quando usar (gatilhos):**
- User wants to create, update, search, or triage Linear issues/projects.
- Sprint planning, workload balancing, or documentation audits in Linear.
- Setting up or troubleshooting the Linear MCP connection.

## pdf

**Título:** PDF (Read, Generate & Validate)

**Descrição:** Use when tasks involve reading, creating, or reviewing PDF files where rendering and layout matter. Prefer visual checks by rendering pages (Poppler) and use Python tools such as `reportlab`, `pdfplumber`, and `pypdf` for generation and extraction.

**Arquivo:** `skills/pdf/SKILL.md`

**Quando usar (gatilhos):**
- Reading or reviewing PDF content where layout and visuals matter.
- Creating PDFs programmatically with reliable formatting.
- Validating final rendering before delivery.

## playwright

**Título:** Playwright CLI Skill

**Descrição:** Drive a real browser from the terminal using `playwright-cli`. Prefer the bundled wrapper script so the CLI works even when it is not globally installed. Treat this skill as CLI-first automation. Do not pivot to `@playwright/test` unless the user explicitly asks for test files.

**Arquivo:** `skills/playwright/SKILL.md`

**Quando usar:** consulte a SKILL.md (não há seção explícita de *When to use*).

## playwright-interactive

**Título:** Playwright Interactive (Persistent Browser via js_repl)

**Descrição:** Persistent browser and Electron interaction through `js_repl` for fast iterative UI debugging. Keep Playwright handles alive across iterations and run functional plus visual QA without restarting the toolchain.

**Arquivo:** `skills/playwright-interactive/SKILL.md`

**Quando usar (gatilhos):**
- Debugging local web or Electron apps interactively with a persistent browser session.
- Running iterative functional and visual QA without restarting Playwright each time.
- When `js_repl` is available and the user needs fast feedback loops on UI changes.

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

## render-deploy

**Título:** Render Deploy (Git-backed & Blueprint)

**Descrição:** Deploy applications to Render by analyzing codebases, generating render.yaml Blueprints, and creating services via MCP tools. Use when the user wants to deploy, host, or publish their application on Render's cloud platform.

**Arquivo:** `skills/render-deploy/SKILL.md`

**Quando usar (gatilhos):**
- User wants to deploy, host, publish, or set up their application on Render.
- Creating a render.yaml Blueprint for multi-service or IaC deployments.
- Setting up databases, cron jobs, or other Render resources.

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

## vercel-deploy

**Título:** Vercel Deploy (Preview & Production)

**Descrição:** Deploy applications and websites to Vercel. Always deploy as preview unless the user explicitly asks for production. Handles CLI auth, fallback deploy script, and returns the preview URL.

**Arquivo:** `skills/vercel-deploy/SKILL.md`

**Quando usar (gatilhos):**
- User requests deployment actions like "deploy my app", "push this live", or "create a preview deployment".
- Setting up or using the Vercel CLI; falling back to the deploy script when auth is missing.

## web2-wallet-auth

**Título:** Web2 Wallet Auth (SIWE/EIP-712 + ERC-1271)

**Descrição:** Implement or review Web2 wallet-based auth (SIWE/EIP-712) with nonce+expiry+anti-replay, ERC-1271 support, rate limiting, and safe logging. Use when touching login/session/authz endpoints or any signature verification off-chain.

**Arquivo:** `skills/web2-wallet-auth/SKILL.md`

**Quando usar (gatilhos):**
- Any change to: login routes, session issuance, signature verification, nonce storage, auth middleware, or endpoints that accept wallet identities.
- Any addition of privileged Web2 roles (admin/ops/keeper) or routes that accept IDs from the client.
