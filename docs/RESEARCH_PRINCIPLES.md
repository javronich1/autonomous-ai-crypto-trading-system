# Research Principles

Future experiments must obey the following methodological rules:

1. **No look-ahead bias.** A decision may use only information that actually existed at its decision timestamp.
2. **Prevent data leakage.** Fit, transform, select, and tune without allowing validation or test information into training decisions.
3. **Respect chronology.** Use chronological train, validation, and test separation; use walk-forward evaluation where appropriate.
4. **Protect a final holdout.** Keep a final test period untouched until the method and evaluation protocol are fixed.
5. **Model costs explicitly.** State fees, spread, and slippage assumptions. Report gross and net performance separately.
6. **Test robustness.** Perform sensitivity analysis across plausible parameters, cost assumptions, regimes, and data windows.
7. **Avoid overfitting.** Prefer simpler explanations and treat fragile or highly tuned results skeptically.
8. **Account for selection bias.** Record the breadth of multiple testing and strategy searches; do not present the best survivor as an isolated trial.
9. **Use simple benchmarks.** Compare sophistication against relevant passive, no-trade, and simple deterministic baselines.
10. **Preserve evidence.** Retain configurations, results, and conclusions for failed and rejected experiments.
11. **Allow inactivity.** `NO TRADE` must always be a valid outcome. Capital preservation takes precedence over forcing activity.
12. **Make work reproducible.** Record data windows, assumptions, configuration, environment, and code/version references.

Any exception requires an explicit, documented research decision and must not be introduced silently.
