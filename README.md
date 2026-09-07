# Autonomous AI Crypto Trading System

Autonomous AI Crypto Trading System is a long-term quantitative research project for testing whether increasingly sophisticated decision systems—including AI agents only where justified—add robust, risk-adjusted value over simple baselines after realistic costs.

It is **not** a guaranteed-profit trading bot. Profitability is an empirical hypothesis to test, and failed or rejected approaches are valuable research evidence.

## Current status

The repository is in **Phase 1: market-data foundation**. The reviewed pipeline provides an exact-decimal OHLCV contract, hourly sequence validation, a Binance Spot adapter, and historical acquisition with explicit UTC boundaries and requested-range coverage. Task 004.5 adds a reviewed local read-only research terminal. No persistence, strategy, backtest, risk engine, execution, paper-trading, or real-money functionality exists.

## Initial scope

- Crypto spot, on one venue initially
- BTC/USDT first; ETH may be considered later
- Approximately one-hour, medium-frequency bars
- Long or flat only
- No leverage, futures, or options
- Offline research only; paper trading comes much later after rigorous validation

## Conceptual architecture

The future system separates configuration, timestamp-bounded market data, features, strategies and analytical agents, deterministic backtesting, deterministic risk controls, portfolio state, approved execution, and audit logging. Risk controls will be able to veto every proposed action, and execution will accept approved decisions only. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository structure

```text
docs/                 Project, architecture, methodology, state, and decisions
src/crypto_trader/    Importable package and future component boundaries
tests/                Unit and integration tests
experiments/          Future experiment records
notebooks/            Exploration only
scripts/              Future repository utilities
```

## Research philosophy

Research proceeds from deterministic baselines toward complexity only when evidence justifies it. Evaluation must be chronological, leakage-resistant, reproducible, benchmarked, robust, and reported both gross and net of explicit fees, spread, and slippage. “No trade” is always a valid result, and preserving capital is more important than forcing activity.

## Local validation

After installing the optional development dependencies in an isolated environment, run:

```bash
python -m pytest
```

With the optional `ui` dependencies installed, the suite also exercises the terminal through Streamlit AppTest with fake acquisition and blocked network access. These integration tests skip when Streamlit or Plotly is absent; core tests remain available.

No real-money functionality currently exists, and none should be inferred from the future-facing directory names.

## Research Terminal

Install the optional local UI dependencies into the active environment:

```bash
python -m pip install -e ".[ui]"
```

Launch the read-only terminal from the repository root:

```bash
streamlit run apps/research_terminal.py
```

The terminal is for historical market-data research only. It has no account access, persistence, strategy, order, execution, paper-trading, or live-trading functionality.
