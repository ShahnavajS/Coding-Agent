from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from assistant_backend.config import get_cached_settings

logger = logging.getLogger(__name__)


@dataclass
class SandboxCommandResult:
    ok: bool
    skipped: bool
    command: list[str]
    image: str
    exit_code: int | None
    stdout: str
    stderr: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _docker_executable() -> str | None:
    return shutil.which("docker")


def docker_available() -> tuple[bool, str]:
    docker = _docker_executable()
    if docker is None:
        return False, "Docker CLI was not found on PATH."

    try:
        result = subprocess.run(
            [docker, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Docker CLI timed out while checking daemon status."
    except OSError as exc:
        return False, f"Docker CLI could not be started: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return False, detail or "Docker daemon is not reachable."
    return True, result.stdout.strip() or "Docker daemon is reachable."


def run_in_sandbox(
    workspace_path: str | Path,
    image: str,
    command: list[str],
    *,
    workdir: str = "/workspace",
    timeout_seconds: int | None = None,
    network: str | None = None,
) -> SandboxCommandResult:
    settings = get_cached_settings().docker_sandbox
    docker = _docker_executable()
    if docker is None:
        return SandboxCommandResult(
            ok=False,
            skipped=True,
            command=command,
            image=image,
            exit_code=None,
            stdout="",
            stderr="",
            error="Docker CLI was not found on PATH.",
        )

    host_workspace = Path(workspace_path).resolve()
    if not host_workspace.exists() or not host_workspace.is_dir():
        return SandboxCommandResult(
            ok=False,
            skipped=True,
            command=command,
            image=image,
            exit_code=None,
            stdout="",
            stderr="",
            error=f"Sandbox workspace does not exist: {host_workspace}",
        )

    timeout = timeout_seconds or settings.timeout_seconds
    sandbox_network = network if network is not None else settings.network
    docker_command = [
        docker,
        "run",
        "--rm",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--network",
        sandbox_network,
        "--cpus",
        settings.cpus,
        "--memory",
        settings.memory,
        "--pids-limit",
        str(settings.pids_limit),
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=128m",
        "--mount",
        f"type=bind,source={host_workspace},target=/workspace",
        "-w",
        workdir,
        image,
        *command,
    ]

    logger.info("Running Docker sandbox command: image=%s command=%s", image, command)
    try:
        result = subprocess.run(
            docker_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return SandboxCommandResult(
            ok=False,
            skipped=False,
            command=command,
            image=image,
            exit_code=None,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
            error=f"Docker sandbox timed out after {timeout} seconds.",
        )
    except OSError as exc:
        return SandboxCommandResult(
            ok=False,
            skipped=True,
            command=command,
            image=image,
            exit_code=None,
            stdout="",
            stderr="",
            error=f"Docker sandbox could not start: {exc}",
        )

    stdout = (result.stdout or "")[-8000:]
    stderr = (result.stderr or "")[-8000:]
    return SandboxCommandResult(
        ok=result.returncode == 0,
        skipped=False,
        command=command,
        image=image,
        exit_code=result.returncode,
        stdout=stdout,
        stderr=stderr,
        error="" if result.returncode == 0 else f"Command exited with {result.returncode}.",
    )
