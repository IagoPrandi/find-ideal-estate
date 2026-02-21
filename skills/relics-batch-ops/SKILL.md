---
name: relics-batch-ops
description: Standardize buy/apply relic operations with deterministic ordering, stock & fee accounting, inventory decrements, slot compatibility rules, and soldout handling. Use in Shop/Relic managers and checkout steps.
---

# Relics Batch Operations (Buy + Apply)

## When to use
- Editing `buyRelics`, `applyRelics`, shop stock generation, fees, inventory/slots, or soldout-triggered relic behavior.

## Goal (Definition of Done)
- ✅ Batch behaves identically to sequential single ops.
- ✅ Stock never goes negative; soldout transitions fire exactly once.
- ✅ Slot compatibility rules are enforced (daily vs monthly).
- ✅ Inventory is validated and decremented exactly once.

## Buy flow (deterministic)
- Validate each `relicId/qty`:
  - qty > 0
  - price exists for scope/day/month
  - remainingStock >= qty
- Compute total cost + merchant fee (if applicable).
- Apply decrements:
  - `remainingStock -= qty`
  - Update `taxFeePool` (if used)
- Emit:
  - `RelicBought(scope, id, player, relicId, qty, totalCost)`
  - `SoldoutReached` when remaining hits 0 (only on transition)

## Apply flow (deterministic)
- Validate:
  - player inventory has qty available
  - targetKind/targetValue valid
  - slots available and compatible:
    - daily temp slots cannot hold monthly effects
    - daily relic applied to monthly occupies fixed/monthly slot until month end
- Apply effects in canonical stable order:
  - sort actions by (scope, relicId, targetKind, targetValue) before applying
- Decrement inventory upon successful apply.
- Emit `RelicApplied(scope, id, player, relicId, targetKind, targetValue)`.

## Soldout rules
- Detect soldout transitions and emit events exactly once.
- Do not alter soldout-dependent relics through unrelated effects (e.g., stock cuts).

## Anti-patterns
- ❌ Applying without pre-validating all constraints (partial mutation).
- ❌ Non-deterministic ordering (different clients → different outcomes).
- ❌ Slot rule ambiguity between daily and monthly.

## Testing checklist
- Batch buy/apply happy path.
- Insufficient stock/slots/inventory reverts.
- Soldout transition event fires once.
- Slot compatibility: daily temp slots cannot “support” monthly application.
