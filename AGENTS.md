# Repository Instructions

This repository is a research system. Future Codex work must follow these rules:

- Work in small, reviewable milestones and never jump ahead of the current task.
- Preserve deterministic behavior wherever possible. Do not introduce AI or agents where ordinary software is sufficient.
- Use type hints and docstrings for meaningful Python code.
- Keep configuration outside business logic; do not scatter magic numbers.
- Add tests for critical behavior when functionality is introduced.
- Preserve reproducibility of data, configuration, code, and results.
- Use structured logging when logging is implemented.
- Never commit API keys, secrets, credentials, or private data. `.env.example` may contain placeholder variable names only.
- Never automatically enable real-money trading.
- Do not silently alter research assumptions. Record meaningful architecture and research decisions in `docs/DECISIONS.md`.
- Preserve failed or rejected strategies as research evidence; they must not simply disappear.

Repository software-development subagents are development tooling. They are not the analytical or trading agents that may eventually be researched inside the application.
