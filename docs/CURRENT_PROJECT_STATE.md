# Current Project State

## Current Phase

Phase 1 — market-data foundation (Task 005B complete and reviewed).

## Current Objective

Provide reproducible local snapshots of reviewed historical acquisition results.

## Scope

BTC/USDT spot research on hourly bars from one public venue, long or flat, no leverage, and historical validation only.

## Implemented

The reviewed market-data pipeline plus a local Streamlit and Plotly research terminal. The terminal provides explicit UTC range and `as_of` controls, closed-candle status, OHLCV candlestick and volume views, normalized data tables, sequence issues, requested-range coverage, and read-only system boundaries. AI copilot space is visibly reserved but not implemented.

Task 005B implements versioned JSON snapshots through explicit offline save/load and byte serialization APIs. Exact Decimal representations and observation order are preserved; quality reports are recomputed, forged metadata is rejected, and atomic hard-link publication refuses existing destinations. Persistence is separate from the terminal. See the [Task 005 specification](TASK_005_PERSISTENCE.md).

## Validated

Task 005B: 283 tests pass, including 175 snapshot cases covering strict schema/domain validation, Decimal context independence, exact roundtrips, I/O and cleanup failures, short writes, interrupted operations, and competing publishers. With optional UI imports blocked, 270 tests pass and one module skips. Independent disk roundtrip, source compilation, dependency checks, diff review, and visual inspection of the unchanged terminal's initial state passed. No new network fetch or backtest was needed.

Task 004.5 validation evidence remains valid: the complete offline suite passed 108 tests with Streamlit 1.63.0 and Plotly 7.0.0 installed, including the 95 pipeline and presentation tests plus 13 Streamlit AppTest cases. Acquisition was faked and network access was blocked in the UI tests; no external service was used.

Compile checks for `src`, `apps`, and `tests`, dependency checks, and whitespace diff checks passed. Simulating Streamlit and Plotly absence separately yielded 95 passed and one skipped integration module in each case. Browser validation confirmed the initial state, explicit live-source fetch, balanced status layout, complete UTC boundaries, candlestick and volume chart, exact normalized table, and wrapped lower panels.

## Task 004.5 Review Corrections

Zero returned bars now distinguish no eligible hours from absent source observations using the existing expected-bar count. Cap explanations reference the explicit `as_of` hour. Retained results identify their original fetch boundaries, supported `width="stretch"` replaces deprecated width arguments after installed-signature inspection, and long system/copilot panel text wraps while preserving terminal formatting. Core data semantics and the original Task 004.5 work are preserved; no persistence or later-phase functionality was added.

## Experiments Run

None.

## Decisions Made

Initial decisions and the Task 002 through Task 005B market-data, interface, and snapshot decisions are recorded in `DECISIONS.md`.

## Known Risks / Open Questions

- Cost and execution assumptions are not yet specified.
- Formal benchmark and evaluation protocols remain to be designed.
- Data licensing, retention, and quality requirements remain open.
- Historical acquisition currently targets only the fixed public Binance Spot BTCUSDT 1h contract; data licensing remains open.
- No retries or backoff, strategies, indicators, backtesting, agents, LLM integration, execution, paper trading, or live trading exists.
- Snapshot persistence requires local POSIX hard links; directory-entry durability across power loss is not guaranteed. SHA-256 is not proof of authenticity. Incomplete snapshots are preserved for inspection, not certified for future backtesting.

## Next Actions

Define the next bounded milestone: offline snapshot inspection in the research terminal. Its controls and error behavior need a separate specification before implementation. Task 005B itself is complete; no later milestone has started.

Task 005A verification: reviewed the specification against the existing data contracts, corrected publication-failure semantics, and reran the unchanged suite (108 passed). Only documentation changed; no new browser session or backtest was run. The Task 004.5 visual evidence above applies to the unchanged app.
