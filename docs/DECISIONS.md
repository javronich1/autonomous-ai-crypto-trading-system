# Decision Log

Decisions are append-only in spirit: later changes should add a superseding entry rather than erase prior reasoning.

## Initial decisions — 2026-09-04

| Decision | Rationale |
|---|---|
| Frame the project research-first, not profit-first | Profitability and added value must be tested empirically. |
| Begin with crypto spot on one venue | Constrains market structure and operational complexity. |
| Use BTC/USDT first | Provides a narrow initial research target; ETH may be evaluated later. |
| Target approximately hourly, medium-frequency bars | Avoids premature high-frequency infrastructure while retaining meaningful decision cadence. |
| Permit long or flat only | Excludes short exposure and simplifies the initial hypothesis space. |
| Use no leverage | Prioritizes capital preservation and limits risk complexity. |
| Build deterministic infrastructure before agentic complexity | Complexity must solve a demonstrated problem and provide measurable value. |
| Require realistic net-of-cost evaluation | Fees, spread, and slippage can invalidate apparent gross performance. |
| Prohibit live-money trading during research development | Offline rigor must precede paper trading, and paper validation must precede any separately authorized live phase. |

## Task 002 market-data contract — 2026-09-04

| Decision | Rationale |
|---|---|
| Require `Decimal` OHLCV values at the internal contract boundary | Exact decimal semantics avoid binary floating-point surprises and implicit conversion rules in financial-data validation. |
| Normalize timezone-aware timestamps to UTC and reject naive timestamps | Aware source timestamps can represent the same instant unambiguously; naive timestamps cannot, so assuming UTC would hide a data-quality problem. |
| Report sequence problems as immutable, machine-readable issues | Future ingestion can inspect duplicates, ordering errors, misalignment, and gaps without parsing logs or mutating the observations. |
| Treat gaps as observations, not repair instructions | Missing market data may be legitimate or source-specific; the contract must not invent candles through filling or interpolation. |

## Task 003 Binance Spot raw-kline boundary — 2026-09-04

| Decision | Rationale |
|---|---|
| Use Binance Spot BTCUSDT 1h as the initial venue-specific market-data source contract | This fixes the first raw input shape while keeping the research scope to one spot market and one hourly interval. |
| Use kline open time as the canonical bar timestamp | The bar is identified by the start of its observation interval and converted from Unix milliseconds directly to aware UTC. |
| Normalize venue-specific raw records before they enter the core domain | Binance field positions and decimal strings remain at the adapter boundary; downstream code receives the existing trusted `OHLCVBar`. |
| Keep ingestion and network transport separate from parsing and normalization | Offline deterministic parsing can be tested independently; acquisition remains explicitly deferred to a later bounded task. |

## Task 004 closed-candle historical acquisition — 2026-09-04

| Decision | Rationale |
|---|---|
| Define historical research ranges as half-open `[start, end)` intervals | Exclusive upper bounds make hourly membership unambiguous; Binance's inclusive `endTime` is derived as one millisecond before the effective end. |
| Admit only fully closed hourly candles | Capping the effective end at the UTC current-hour start prevents an incomplete observation from entering historical research data. |
| Require an explicit `as_of` datetime | The closed-candle boundary remains deterministic and reproducible rather than depending on a hidden system clock read. |
| Keep Binance REST transport separate from venue parsing and domain validation | Acquisition delegates every raw record to the reviewed adapter and returns the existing sequence-quality result. |
| Defer automatic retries and backoff | HTTP and rate-limit failures surface immediately; retry timing and policy require a separate reviewed milestone. |
| Report sequence quality and requested-range coverage separately | A returned sequence can be internally continuous while omitting leading or trailing expected hours, so acquisition coverage compares unique aligned observations with the effective requested grid without changing or repairing the bars. |
