# Production Coding Assistant

Standalone source project for the desktop AI coding assistant.

The following repositories are reference-only and were not modified:

- `../deepagents-main`
- `../everything-claude-code-main`

## Structure

```text
production-coding-assistant/
|-- backend/
|   |-- assistant_backend/
|   `-- server.py
|-- config/
|   |-- .env.example
|   |-- app.example.json
|   `-- models.example.json
|-- desktop/
|   |-- electron/
|   |-- electron.d.ts
|   |-- vite.main.config.ts
|   `-- vite.preload.config.ts
|-- docs/
|   `-- ARCHITECTURE.md
|-- frontend/
|-- scripts/
|-- workspace/
|   `-- .gitkeep
|-- .gitignore
|-- forge.config.ts
|-- package.json
|-- package-lock.json
|-- pyproject.toml
`-- requirements.txt
```

## Cleanup Status

- Runtime state, caches, demo files, smoke-test files, and build outputs are removed.
- `workspace/` is intentionally empty and tracked only with `.gitkeep`.
- Generated folders such as `.assistant/`, `node_modules/`, `frontend/dist/`, `out/`, and `__pycache__/` are not part of the clean source tree.

## Install

```powershell
cd "C:\Users\sanus\Desktop\Coding agent\production-coding-assistant"
npm install
npm --prefix frontend install
```

## Run

```powershell
cd "C:\Users\sanus\Desktop\Coding agent\production-coding-assistant"
.\scripts\run_backend.ps1
```

```powershell
cd "C:\Users\sanus\Desktop\Coding agent\production-coding-assistant"
.\scripts\run_frontend.ps1
```

## Package

```powershell
cd "C:\Users\sanus\Desktop\Coding agent\production-coding-assistant"
.\scripts\run_electron_package.ps1
.\scripts\run_electron_make.ps1
```

## Notes

- Runtime state is recreated automatically under `.assistant/` when the app runs.
- See [ARCHITECTURE.md](/C:/Users/sanus/Desktop/Coding%20agent/production-coding-assistant/docs/ARCHITECTURE.md) for the layout summary.
- Web search can be configured with `BRAVE_SEARCH_API_KEY`, `SERPAPI_API_KEY`, or `BING_SEARCH_API_KEY` plus the `WEB_SEARCH_*` settings in [config/.env.example](/C:/Users/sanus/Desktop/Coding%20agent/production-coding-assistant/config/.env.example).
- Backend-only search verification is available at `POST /api/agent/search-test`.
