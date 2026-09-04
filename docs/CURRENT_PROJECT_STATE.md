# Current Project State

## Current Phase

Phase 1 — market-data foundation (Task 002 complete and reviewed).

## Current Objective

The deterministic, strongly validated internal contract for historical hourly OHLCV bars is complete.

## Scope

BTC/USDT spot research on approximately hourly bars, one venue, long or flat, no leverage, and offline validation only.

## Implemented

Repository foundations plus an immutable OHLCV market-data contract using exact decimal values, explicit UTC timestamp semantics, and structured deterministic hourly sequence validation.

## Validated

The complete test suite currently passes 32 tests. Validation covers the top-level package import, individual OHLCV invariants, UTC normalization and naive-timestamp rejection, hourly boundary alignment, strict chronology, duplicate detection, and explicit gap reporting without data filling.

## Experiments Run

None.

## Decisions Made

Initial decisions and the Task 002 market-data contract decisions are recorded in `DECISIONS.md`.

## Known Risks / Open Questions

- Venue and authoritative data source are not selected.
- Cost and execution assumptions are not yet specified.
- Formal benchmark and evaluation protocols remain to be designed.
- Data licensing, retention, and quality requirements remain open.
- Market-data acquisition, source-specific normalization, and persistence are not implemented.
- No ingestion, network integration, persistence, strategies, backtesting, agents, or trading functionality exists.

## Next Actions

Define the next bounded market-data ingestion milestone.
