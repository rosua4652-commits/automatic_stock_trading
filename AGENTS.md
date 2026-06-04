# AGENTS.md

Guidance for AI agents working in this repository.

## Project status

This repository is a **greenfield** project named `automatic_stock_trading`. It currently contains only `README.md` (title line). There is no application source, dependency manifests, CI config, or Docker setup yet.

## Cursor Cloud specific instructions

### Services

There are **no runnable services** in this repository yet. Do not expect API servers, workers, databases, or broker integrations until they are added to the tree.

### Dependencies

There is nothing to install from the repo today (no `package.json`, `requirements.txt`, `pyproject.toml`, etc.). The VM update script is a no-op until manifests exist.

### Lint / test / build / run

No project-specific commands exist yet. When you add a stack, document the canonical commands here and in `README.md`, for example:

| Task | Command (placeholder — add when implemented) |
|------|-----------------------------------------------|
| Lint | TBD |
| Test | TBD |
| Build | TBD |
| Dev server | TBD |

### VM toolchain (observed during environment setup)

- Git 2.43
- Node.js v22.x and npm 10.x
- Python 3.12
- Docker is **not** installed on the default Cloud Agent VM; install only if the project later requires it.

### Git

Default branch: `main`. Remote: `origin` (`rosua4652-commits/automatic_stock_trading`).
