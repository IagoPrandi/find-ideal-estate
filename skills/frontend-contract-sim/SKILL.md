---
name: frontend-contract-sim
description: Standardize frontend transaction flows with viem/wagmi using simulation-first, deterministic error mapping, and safe logging. Use for checkout, commit/reveal, buy/apply relics, draws, and claims.
---

# Frontend Contract Simulation (viem/wagmi)

## When to use
- Any UI flow that sends transactions or estimates costs.
- Error handling or user messaging around reverts.

## Goal (Definition of Done)
- ✅ Every write path simulates before submitting.
- ✅ Revert reasons map to user-friendly messages (no raw leakage).
- ✅ ABI/types remain in sync with contracts.

## Simulation-first pattern
For each action:
1) `simulateContract(...)` (or backend `/api/simulate/*` for server-side)
2) If simulate fails → block submission + show mapped message
3) `writeContract(...)`
4) `waitForTransactionReceipt(...)`
5) Update UI state optimistically, then confirm via indexer/API.

## Error mapping (deterministic)
Map known failures to stable UI codes:
- `NOT_IN_PHASE` → “A fase atual não permite essa ação.”
- `INSUFFICIENT_PAYMENT` → “Saldo insuficiente para concluir o carrinho.”
- `INSUFFICIENT_STOCK` → “Estoque acabou. Atualize a loja.”
- `INSUFFICIENT_SLOTS` → “Sem slots disponíveis para equipar.”
- `ALREADY_CLAIMED` → “Prêmio já resgatado.”
- `NOT_WINNER` → “Sua aposta não venceu neste modo.”

## ABI & types
- Use typed clients and shared enums (WinMode, Phase, TargetKind).
- Keep ABI generated from build artifacts; never hand-edit event signatures.

## UX requirements
- Show cost breakdown before signature when possible.
- Handle chain mismatch (prompt network switch).
- Handle replacement/queued txs; show “pending” state and allow user to retry safely.

## Logging & privacy
- Do not log full signatures, nonces, tokens, or PII.
- Client logs should be minimal; detailed diagnostics go server-side with redaction.

## Testing checklist
- Unit tests for error mapping.
- Integration tests for simulate→send happy path (mock clients).
- E2E: cart build → simulate → submit → receipt → UI updates.
