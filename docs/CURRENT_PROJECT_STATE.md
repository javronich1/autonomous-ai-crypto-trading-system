# Current Project State

## Current Phase

Phase 1 — market-data foundation (Task 003 complete and reviewed).

## Current Objective

The offline Binance Spot BTCUSDT 1h raw-kline adapter is implemented and validated.

## Scope

BTC/USDT spot research on approximately hourly bars, one venue, long or flat, no leverage, and offline validation only.

## Implemented

Repository foundations, the reviewed immutable OHLCV contract and hourly sequence validator, and an offline Binance Spot BTCUSDT 1h adapter. The adapter normalizes kline open time from integer Unix milliseconds to an aware UTC timestamp and converts OHLCV decimal strings into the trusted `OHLCVBar` contract.

## Validated

The complete test suite currently passes 54 tests. Validation covers the existing OHLCV and sequence contracts plus Binance raw-record shape, UTC Unix-millisecond conversion, exact decimal parsing, extra-field tolerance, domain-validation delegation, and input immutability.

## Experiments Run

None.

## Decisions Made

Initial decisions and the Task 002 and Task 003 market-data boundary decisions are recorded in `DECISIONS.md`.

## Known Risks / Open Questions

- Cost and execution assumptions are not yet specified.
- Formal benchmark and evaluation protocols remain to be designed.
- Data licensing, retention, and quality requirements remain open.
- Historical market-data acquisition, network transport, and persistence are not implemented.
- No network acquisition, persistence, strategies, backtesting, agents, execution, paper trading, or live trading exists.

## Next Actions

Define the next bounded historical market-data acquisition milestone.
