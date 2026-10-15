# CLAUDE.md

Take-home assignment: a web app for an employee training register (MUNI, full-stack developer position).
Data export date: 2026-10-01. HR questions deadline: 2026-10-19. Submission deadline: 2026-10-26.

## How we work

- Start with a notebook only. No app, modules or tests until the notebook is approved.
- Every step must be approvable: propose it, explain it in chat, wait for approval, then implement.
- Do not over-engineer. Simple, clean, readable code. No classes or abstractions until there is a real second use.
- Do not over-comment. Code should explain itself; explanations belong in the chat.
- Keep notebook cells small, one idea per cell.
- All code, comments and docstrings in English.
- Do not commit or push unless asked.

## Approach

1. Repo setup: git, `data/` (gitignored), `notebooks/`, `requirements.txt`, `AI_LOG.md`.
2. Notebook A - loading and cleaning: read everything as `str` with explicit encoding and separator, small helpers for dates, numbers and department names, drop `rodne_cislo` right after loading, print how many rows each cleaning rule touched.
3. Notebook B - compliance: parse `povinne_pro`, compute required trainings per active employee, status (valid / expiring / expired / missing) relative to the export date.
4. Notebook C - scheduling: usable future terms with free seats, greedy assignment per training by priority, report the capacity shortfall.
5. Notebook D - findings, assumptions and questions for HR.
6. After approval: move logic into a small module with pytest tests, then the app, deployment, README and AI log.
