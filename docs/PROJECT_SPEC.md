# Project Specification

## Problem statement

Trading research is vulnerable to leakage, overfitting, unrealistic cost assumptions, and unjustified complexity. This project will provide a trustworthy experimental framework for determining whether a decision system has durable value rather than assuming that AI or trading is profitable.

## Primary research objective

Measure whether increasingly sophisticated methods add robust risk-adjusted value over simple, deterministic baselines after realistic costs. Profitability is an empirical hypothesis, not a premise.

## Initial scope

- One crypto spot venue
- BTC/USDT first, with ETH as a possible later addition
- Approximately one-hour, medium-frequency bars
- Long or flat positions only
- Offline research and validation

The long/flat constraint means the system may hold the spot asset or hold no position. Short exposure is outside the initial scope.

## Explicit exclusions

The initial scope excludes leverage, futures, options, multiple venues, real-money trading, and near-term paper trading. Task 001 additionally excludes data acquisition, exchange integrations, features, strategies, backtesting, portfolio and risk calculations, execution, databases, optimization, machine learning, LLM calls, and autonomous trading agents.

## Evaluation requirements

Every candidate must be compared with simple benchmarks and evaluated both gross and net of explicit, documented costs, including fees, spread, and slippage. Research conclusions must account for risk, robustness, and out-of-sample evidence rather than headline return alone.

Development progresses from deterministic baselines to more sophisticated statistical, machine-learning, or agentic methods only when a clear hypothesis and evidence justify the added complexity.
