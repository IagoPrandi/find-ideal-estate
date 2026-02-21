---
name: security-threat-checklist
description: Apply project security requirements (threat model + Web2/Web3 checklists + mandatory scans/tests) whenever surface area changes: auth, contracts, indexer, API, infra, or admin ops.
---

# Security Threat Checklist (DoD Requirement)

## When to use
- Any PR that changes:
  - external/public endpoints (HTTP or on-chain functions)
  - auth/signatures/login
  - payout/claim/withdraw
  - upgradeability/storage
  - indexer/DB writes or replay logic
  - infra/secrets/config

## Goal (Definition of Done)
- ✅ Threat model filled (or explicitly “no surface change”).
- ✅ No secrets in code/logs; errors don’t leak sensitive details.
- ✅ Web3 checks (reentrancy, randomness, tx.origin, upgrade safety).
- ✅ Required scans + tests are green.

## Threat model (required when surface changes)
Document:
1) Protected assets (funds, game integrity, PII, availability)
2) Entrypoints (routes, public/external funcs, upgrades)
3) Actors (user, bot, attacker, admin, keeper)
4) Trust boundaries (client→API, API→DB, API→RPC, contract→external)
5) Top threats (≥3) + mitigations
6) Assumptions (oracle/VRF, admin, chain, upgrade process)

## Web2 checklist
- Input validation (schema)
- Rate limiting on expensive endpoints
- Object-level authorization (anti-IDOR)
- Wallet login: nonce + expiry + anti-replay; support ERC-1271
- CORS restrictive; no secrets in logs

## Web3 checklist
- No `tx.origin`
- CEI + reentrancy guard where needed; prefer pull-payments
- Randomness: VRF only; no timestamp/blockhash
- Upgradeability: namespaced storage (ERC-7201), initializer safety, authorizeUpgrade protected
- Avoid unbounded loops / gas-DoS

## Required checks (minimum)
- Secrets scan (gitleaks)
- SCA (osv-scanner)
- SAST (semgrep)
- Solidity analysis (slither + aderyn)
- Tests:
  - `forge test -vvv`
  - Web2 auth tests when applicable
