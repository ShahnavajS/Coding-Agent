# Docker Sandbox Validation

The Docker sandbox validates generated projects in an isolated container before the agent writes the final result to the workspace. It is designed to catch issues that static checks miss, such as invalid Python bytecode, broken manifests, and container-only environment mistakes.

## Why It Exists

Generated code should not run directly on the host machine. The sandbox creates a temporary copy of the generated files, bind-mounts that copy into Docker, runs validation commands, captures logs, and returns the result to the agent.

The current implementation runs lightweight, network-free checks by default:

- Python: `python -m compileall .`
- Node projects: parse each generated `package.json` with Node

Dependency installation is intentionally not automatic yet. That keeps the default sandbox deterministic, fast, and safe with `DOCKER_SANDBOX_NETWORK=none`.

## Requirements

On Windows, install Docker Desktop with the WSL 2 backend enabled.

Useful official references:

- Docker Desktop for Windows: https://docs.docker.com/desktop/setup/install/windows-install/
- Docker bind mounts: https://docs.docker.com/engine/storage/bind-mounts/
- Docker run reference: https://docs.docker.com/reference/cli/docker/container/run/

## Configuration

Add these values to `.env` or configure them through settings once UI controls exist:

```env
DOCKER_SANDBOX_ENABLED=true
DOCKER_SANDBOX_FAIL_ON_ERROR=false
DOCKER_SANDBOX_DEFAULT_TIMEOUT=90
DOCKER_SANDBOX_NETWORK=none
DOCKER_SANDBOX_PYTHON_IMAGE=python:3.12-slim
DOCKER_SANDBOX_NODE_IMAGE=node:22-alpine
DOCKER_SANDBOX_MEMORY=1g
DOCKER_SANDBOX_CPUS=1
DOCKER_SANDBOX_PIDS_LIMIT=128
```

Recommended rollout:

1. Start with `DOCKER_SANDBOX_ENABLED=true` and `DOCKER_SANDBOX_FAIL_ON_ERROR=false`.
2. Generate a few projects and inspect the `Docker Sandbox` step in the chat details.
3. After Docker Desktop is stable, switch to `DOCKER_SANDBOX_FAIL_ON_ERROR=true`.

## Safety Model

The sandbox uses:

- A temporary generated-file directory, not the real workspace.
- A Docker bind mount at `/workspace`.
- `--network none` by default.
- CPU, memory, and PID limits.
- Command timeouts.
- No Docker socket mount.

Do not mount broad host directories like `C:\Users` into generated-code containers.

## Manual Checks

Python syntax check:

```powershell
docker run --rm `
  --network none `
  --cpus 1 `
  --memory 1g `
  --pids-limit 128 `
  --tmpfs /tmp:rw,noexec,nosuid,size=128m `
  --mount type=bind,source="C:\path\to\workspace",target=/workspace `
  -w /workspace `
  python:3.12-slim `
  python -m compileall .
```

Node manifest check:

```powershell
docker run --rm `
  --network none `
  --cpus 1 `
  --memory 1g `
  --pids-limit 128 `
  --tmpfs /tmp:rw,noexec,nosuid,size=128m `
  --mount type=bind,source="C:\path\to\workspace",target=/workspace `
  -w /workspace/frontend `
  node:22-alpine `
  node -e "JSON.parse(require('fs').readFileSync('package.json','utf8')); console.log('package.json ok')"
```

## Current Limits

The sandbox does not yet run `pip install`, `pytest`, `npm install`, or `npm run build` automatically. Those require a more deliberate dependency policy because generated projects may need network access and package downloads.

Recommended next upgrade:

- Add a dependency-install mode that temporarily enables network access.
- Cache package manager downloads in a Docker volume.
- Run project-specific tests after dependency installation.
- Feed sandbox logs into the repair prompt as structured validation errors.
