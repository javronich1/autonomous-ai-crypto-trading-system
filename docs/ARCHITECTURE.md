# Conceptual Architecture

This document defines future boundaries; it does not claim that the components are implemented.

## Component boundaries

- **Configuration:** validated research and runtime settings, separate from business logic.
- **Market data:** acquisition, normalization, quality checks, and timestamp-aware access to observations.
- **Features:** reproducible transformations derived only from information available at the relevant timestamp.
- **Strategies:** deterministic decision rules and models that propose actions without controlling risk or execution.
- **Analytical/trading agents:** optional future components that analyze information or propose decisions when evidence supports their use.
- **Deterministic backtesting:** chronological simulation with explicit execution timing and costs.
- **Deterministic risk controls:** independent constraints that approve, modify, or veto proposed decisions.
- **Portfolio state:** authoritative positions, balances, and state transitions.
- **Execution:** accepts approved decisions only and translates them into venue actions in future, explicitly authorized phases.
- **Audit and logging:** structured, immutable-enough records of inputs, proposals, approvals, state transitions, and outcomes.
- **Research terminal:** a local, read-only visualization and inspection surface for historical market data, validation results, experiment metadata, and later research outputs. It must consume reviewed domain/application interfaces rather than reimplement data, strategy, risk, portfolio, or execution logic.

Conceptually, timestamp-bounded data flows into features and decision systems. Proposed decisions then pass through deterministic risk controls before they may affect portfolio or execution state. Audit records span every boundary.

## Architectural rules

- Information supplied to a decision must be bounded by what existed at that timestamp.
- Risk controls remain deterministic and capable of vetoing any decision.
- Analytical agents cannot bypass risk controls or call execution directly.
- Execution accepts approved decisions only.
- Decisions, inputs, assumptions, and outcomes should eventually be explainable and auditable.
- Deterministic infrastructure is preferred wherever agents add no justified value.
- Research simulation, paper trading, and any later live concerns must remain explicitly separated.
- The research terminal is observational by default: it may request and visualize historical research data but must not place orders, mutate portfolio state, bypass validation, or create a second source of trading logic.
- Any future AI-assisted terminal features must remain advisory and auditable; they may summarize or explain reviewed research outputs but cannot bypass deterministic risk or execution boundaries.

## Two meanings of “agent”

Codex/software-development subagents are tools used by maintainers to build or review this repository. They are not runtime system components and have no trading authority.

Trading/analytical agents are hypothetical future application components that may analyze data or propose actions. If introduced, they remain constrained by timestamp-bounded inputs, deterministic risk controls, approved execution boundaries, and audit requirements. The existence of the `agents` package does not imply their implementation or necessity.
