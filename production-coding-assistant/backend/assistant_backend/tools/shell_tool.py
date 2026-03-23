from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Any

from assistant_backend.config import get_cached_settings
from assistant_backend.tools.filesystem_tool import workspace_root

logger = logging.getLogger(__name__)

# Commands that require explicit user approval before running.
# Using a blocklist here; consider switching to an allowlist for stricter control.
DANGEROUS_COMMAND_TOKENS = {
    "rm",
    "del",
    "rmdir",
    "git",
    "npm",
    "pip",
    "pnpm",
    "yarn",
    "curl",
    "wget",
}


def classify_command(command: str) -> str:
    """Return 'review' if the command needs approval, 'safe' otherwise."""
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        logger.warning("Could not parse command for classification: %r", command)
        return "review"
    if not parts:
        return "safe"
    return "review" if parts[0].lower() in DANGEROUS_COMMAND_TOKENS else "safe"


def execute_command(command: str, approved: bool = False) -> dict[str, Any]:
    """Execute a shell command inside the workspace directory.

    Uses shell=False with shlex.split() to prevent shell injection.
    Commands classified as 'review' require explicit approval.
    """
    risk = classify_command(command)
    if risk == "review" and not approved:
        logger.info("Command requires approval, blocked: %r", command)
        return {
            "success": False,
            "requiresApproval": True,
            "risk": risk,
            "stdout": "",
            "stderr": f"Command '{command}' requires explicit approval.",
            "exitCode": None,
        }

    settings = get_cached_settings()

    try:
        # Split into a list and use shell=False to prevent shell injection attacks.
        args = shlex.split(command, posix=False)
    except ValueError as exc:
        logger.error("Failed to parse command %r: %s", command, exc)
        return {
            "success": False,
            "requiresApproval": False,
            "risk": risk,
            "stdout": "",
            "stderr": f"Invalid command syntax: {exc}",
            "exitCode": 1,
        }

    logger.info("Executing command: %r (approved=%s)", command, approved)
    try:
        result = subprocess.run(
            args,
            shell=False,  # Never use shell=True — prevents shell injection
            cwd=workspace_root(),
            capture_output=True,
            text=True,
            timeout=settings.shell_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ds: %r", settings.shell_timeout_seconds, command)
        return {
            "success": False,
            "requiresApproval": False,
            "risk": risk,
            "stdout": "",
            "stderr": f"Command timed out after {settings.shell_timeout_seconds}s.",
            "exitCode": -1,
        }

    logger.debug("Command exit code %d: %r", result.returncode, command)
    return {
        "success": result.returncode == 0,
        "requiresApproval": False,
        "risk": risk,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exitCode": result.returncode,
    }
