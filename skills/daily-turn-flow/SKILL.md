---
name: daily-turn-flow
description: Enforce the canonical daily flow (OPEN/SHOP → COMMIT → REVEAL → DRAW → CLAIM → CLOSE) with strict phase checks, commit/reveal invariants, VRF lifecycle, and event expectations for indexer/UI.
---

# Daily Turn Flow (Canonical Phases)

## When to use
- Any change to daily phases, deadlines, commit/reveal/draw/claim functions, or UI/Indexer logic that depends on phases.

## Goal (Definition of Done)
- ✅ Phase machine cannot be bypassed.
- ✅ Each action emits canonical events for indexing and UX.
- ✅ No double-claim; payouts are pull-based / credited.

## Phase model (canonical)
1) `OPEN/SHOP`
2) `COMMIT`
3) `REVEAL`
4) `DRAW` (VRF request + callback)
5) `CLAIM`
6) `CLOSE`

## Core invariants
- Feed payment required before “active” participation that day.
- Commit required before reveal.
- Reveal required before being counted for winners (A2 counters update on reveal).
- Draw must complete before any claim.
- Claim is per mode (if multiple win modes are enabled), and each mode has its own claimed flag.

## VRF lifecycle (must be complete)
- `requestDraw(dayId)` emits `DrawRequested(...)`
- VRF callback stores result and emits `DrawResult(...)`
- Draw result computation stores:
  - `winningKeyByMode`, `winnersCountByMode`, `amountPerWinner` (or derivable)

## Close/Open transitions
- Close locks the day and prevents further state changes.
- Open creates the next day shop snapshot and resets daily-only data.

## Events (minimum expectations)
- `DayOpened`, `ShopDailyItem`/`DailyShopOpened`
- `FeedPaid`
- `DailyCommitted`
- `DailyRevealed`
- `DrawRequested`, `DrawResult`
- `Claimed` (and rollover events when no winners)

## Anti-patterns
- ❌ Allowing commit/reveal in wrong phase.
- ❌ Draw without a committed/revealed set consistent with rules.
- ❌ “Push payouts” inside claim without pull-based safeguards.

## Testing checklist
- Happy path end-to-end (pay → commit → reveal → draw → claim).
- Negative tests for wrong phase/order and duplicates.
- Multi-winner split correctness.
- No-winner rollover correctness.
- “Claim can’t pay twice” property test/invariant.
