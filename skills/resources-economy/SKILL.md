---
name: resources-economy
description: Apply internal Resources rules (earn/redeem/get) with authorization, max supply caps, minimum redeem thresholds, and deterministic validation. Use when touching token economy or redemption logic.
---

# Resources Economy (Internal Token)

## When to use
- Editing `earnResources`, `redeemResources`, supply caps, or UI that shows balances/redemption.

## Goal (Definition of Done)
- ✅ Only authorized roles/modules can mint/earn.
- ✅ Redeem enforces minimum + quota rules.
- ✅ Events emitted for indexer/UI.

## Earn rules
- `earnResources(player, amount)`:
  - require authorized (owner/game module)
  - require `totalSupply + amount <= MAX_SUPPLY`
  - credit balance
  - emit `ResourcesEarned(player, amount, reason)`

## Redeem rules
- `redeemResources(amount)`:
  - require amount >= 1000
  - require amount % 1000 == 0
  - require balance >= amount
  - debit balance and record redemption
  - emit `ResourcesRedeemed(player, amount)`

## Read rule
- `getResources(player)` returns current balance (view).

## Testing checklist
- Earn: basic, multiple, cap exceeded, unauthorized.
- Redeem: basic, below minimum, not multiple, insufficient balance.
- Events indexed and balances consistent after replay.
