# Architecture

## Layers

- `backend/assistant_backend`
  - API, orchestration, storage, tools, validation, provider routing
- `frontend`
  - React, Monaco, Tailwind, Zustand UI
- `desktop`
  - Electron main/preload and Forge packaging
- `config`
  - Example runtime and provider configuration
- `scripts`
  - Local run/package helper scripts
- `workspace`
  - Empty editable workspace root for user projects

## Runtime Model

- Backend owns provider keys and file/tool execution.
- Frontend talks only to backend HTTP APIs.
- Desktop shell launches backend + renderer.
- Runtime state is recreated under `.assistant/` on first run and is intentionally not committed.
