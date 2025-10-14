This folder contains deprecated/legacy supervisor implementations kept for reference during the migration to the hierarchical supervisor architecture.

Files:

- supervisor_classic_backup.py — Original monolithic supervisor (deprecated)
- supervisor_delegation.py — Delegation pattern prototype (deprecated)

Status:

- These files are not used by the runtime. They may be removed after validation.

If you need to run them temporarily, update imports accordingly, but prefer the new graph in `multiagent/graph/supervisor.py`.
