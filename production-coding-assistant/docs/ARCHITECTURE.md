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

## Backend Tool Inventory

### Core Tools (original)
- **Filesystem** — read, write, create, delete files in the workspace
- **Shell** — execute terminal commands with safety classification
- **Structured Editor** — preview and apply file changes with checkpoints
- **AST Editor** — modify Python assignments and merge JSON at the AST level
- **Validation** — syntax-check Python and JSON before applying writes

### New Tools (v2)
- **Grep / Search** — regex and literal search across all workspace files, with context lines, file-type filtering, and result limits
- **Find & Replace** — preview and apply text replacements in files (supports regex)
- **Git Integration** — status, diff, log, branch, commit, stash, checkout — all sandboxed to workspace root
- **Code Analysis** — AST-based symbol extraction, cyclomatic complexity metrics, code smell detection (unused imports, long functions, missing docstrings)
- **Dependency Analysis** — import graph construction, reverse-dependency maps, project structure tree

## API Endpoint Groups

| Group            | Prefix               | Purpose                                |
|------------------|-----------------------|----------------------------------------|
| Health           | `/api/health`         | Server liveness check                  |
| Files            | `/api/files/*`        | CRUD on workspace files                |
| Diffs            | `/api/diff/*`         | Preview and apply code changes         |
| Checkpoints      | `/api/checkpoints/*`  | Rollback to previous file state        |
| Sessions         | `/api/sessions/*`     | Chat session management                |
| Agent            | `/api/agent/*`        | Main LLM orchestration                 |
| Terminal         | `/api/terminal/*`     | Shell command execution                |
| Settings         | `/api/settings`       | Runtime configuration                  |
| **Search**       | `/api/search/*`       | Grep and find-and-replace              |
| **Git**          | `/api/git/*`          | Git operations                         |
| **Code Analysis**| `/api/analysis/*`     | Symbols, complexity, smells, deps      |

## Provider Priority

When a request is made, providers are tried in this order:
1. User's selected provider
2. Groq
3. OpenAI
4. Anthropic
5. Ollama (local)
6. Local model path
