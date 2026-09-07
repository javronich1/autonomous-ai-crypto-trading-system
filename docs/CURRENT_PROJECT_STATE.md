# Current Project State

## Current Phase

Phase 1 — market-data foundation (Task 004.5 complete and reviewed).

## Current Objective

Provide a polished local read-only research terminal for inspecting the reviewed market-data pipeline.

## Scope

BTC/USDT spot research on hourly bars from one public venue, long or flat, no leverage, and historical validation only.

## Implemented

The reviewed market-data pipeline plus a local Streamlit and Plotly research terminal. The terminal provides explicit UTC range and `as_of` controls, closed-candle status, OHLCV candlestick and volume views, normalized data tables, sequence issues, requested-range coverage, and read-only system boundaries. AI copilot space is visibly reserved but not implemented.

## Validated

The complete offline suite passes 108 tests with Streamlit 1.63.0 and Plotly 7.0.0 installed. This includes the existing 95 pipeline and presentation tests plus 13 Streamlit AppTest cases covering explicit fetch behavior, aware UTC arguments, candlestick and volume rendering, exact table values, coverage and sequence issues, distinct empty outcomes, historical `as_of` cap wording, failure recovery, and retained result boundaries after control edits. Acquisition is faked and network access is blocked in the UI tests; no external service is used.

Compile checks for `src`, `apps`, and `tests`, dependency checks, and whitespace diff checks pass. Simulating Streamlit and Plotly absence separately yields 95 passed and one skipped integration module in each case. Browser validation confirms the initial state, explicit live-source fetch, balanced status layout, complete UTC boundaries, candlestick and volume chart, exact normalized table, and wrapped lower panels.

## Task 004.5 Review Corrections

Zero returned bars now distinguish no eligible hours from absent source observations using the existing expected-bar count. Cap explanations reference the explicit `as_of` hour. Retained results identify their original fetch boundaries, supported `width="stretch"` replaces deprecated width arguments after installed-signature inspection, and long system/copilot panel text wraps while preserving terminal formatting. Core data semantics and the original Task 004.5 work are preserved; no persistence or later-phase functionality was added.

## Experiments Run

None.

## Decisions Made

Initial decisions and the Task 002 through Task 004.5 market-data and interface decisions are recorded in `DECISIONS.md`.

## Known Risks / Open Questions

- Cost and execution assumptions are not yet specified.
- Formal benchmark and evaluation protocols remain to be designed.
- Data licensing, retention, and quality requirements remain open.
- Historical acquisition currently targets only the fixed public Binance Spot BTCUSDT 1h contract; data licensing remains open.
- No persistence, retries or backoff, strategies, indicators, backtesting, agents, LLM integration, execution, paper trading, or live trading exists.

## Next Actions

Define Task 005 as the next bounded market-data milestone before implementing persistence.
