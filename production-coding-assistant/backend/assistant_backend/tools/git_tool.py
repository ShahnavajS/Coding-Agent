"""Git integration tool — safe Git operations inside the workspace.

Supports status, diff, log, branch management, staging, committing,
and stashing — all scoped to the workspace root.
"""
from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Any

from assistant_backend.config import get_cached_settings
from assistant_backend.tools.filesystem_tool import workspace_root

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # seconds — git ops should be fast


class GitNotAvailableError(RuntimeError):
    """Raised when the workspace is not a git repository."""


def _run_git(*args: str, timeout: int = _TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a git command in the workspace root and return the result.

    Raises GitNotAvailableError if the workspace is not a repo.
    """
    cmd = ["git"] + list(args)
    root = workspace_root()
    logger.debug("Running: %s (cwd=%s)", " ".join(cmd), root)
    try:
        result = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError:
        raise GitNotAvailableError("Git is not installed or not on PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Git command timed out after {timeout}s: {' '.join(cmd)}")

    if result.returncode != 0 and "not a git repository" in result.stderr.lower():
        raise GitNotAvailableError(f"Workspace is not a git repository: {root}")

    return result


def _ok(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "exitCode": result.returncode,
    }


# ── Read operations ─────────────────────────────────────────────────

def git_status() -> dict[str, Any]:
    """Return `git status --porcelain=v1` parsed into structured data."""
    result = _run_git("status", "--porcelain=v1")
    if result.returncode != 0:
        return _ok(result)

    files: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        index_status = line[0]
        worktree_status = line[1]
        path = line[3:]
        files.append({
            "path": path,
            "indexStatus": index_status.strip(),
            "worktreeStatus": worktree_status.strip(),
        })

    return {
        "success": True,
        "files": files,
        "clean": len(files) == 0,
        "branch": git_current_branch().get("branch", "unknown"),
    }


def git_diff(staged: bool = False, path: str | None = None) -> dict[str, Any]:
    """Return the output of `git diff` (or `git diff --cached`)."""
    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        args.extend(["--", path])
    result = _run_git(*args)
    return _ok(result)


def git_log(max_count: int = 20, oneline: bool = True) -> dict[str, Any]:
    """Return recent git log entries."""
    args = ["log", f"--max-count={max_count}"]
    if oneline:
        args.append("--oneline")
    else:
        args.extend(["--format=%H%n%an%n%ae%n%s%n%aI%n---"])
    result = _run_git(*args)
    if not oneline and result.returncode == 0:
        entries = []
        for block in result.stdout.strip().split("\n---\n"):
            parts = block.strip().split("\n")
            if len(parts) >= 4:
                entries.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "email": parts[2],
                    "subject": parts[3],
                    "date": parts[4] if len(parts) > 4 else "",
                })
        return {"success": True, "entries": entries}
    return _ok(result)


def git_current_branch() -> dict[str, Any]:
    """Return the current branch name."""
    result = _run_git("branch", "--show-current")
    return {
        "success": result.returncode == 0,
        "branch": result.stdout.strip(),
    }


def git_branches() -> dict[str, Any]:
    """List all local branches."""
    result = _run_git("branch", "--list", "--no-color")
    if result.returncode != 0:
        return _ok(result)
    branches = []
    for line in result.stdout.splitlines():
        is_current = line.startswith("*")
        name = line.lstrip("* ").strip()
        if name:
            branches.append({"name": name, "current": is_current})
    return {"success": True, "branches": branches}


# ── Write operations ────────────────────────────────────────────────

def git_add(paths: list[str] | None = None) -> dict[str, Any]:
    """Stage files. If paths is None, stages everything (`git add -A`)."""
    args = ["add"]
    if paths:
        args.extend(paths)
    else:
        args.append("-A")
    return _ok(_run_git(*args))


def git_commit(message: str) -> dict[str, Any]:
    """Create a commit with the given message."""
    if not message.strip():
        return {"success": False, "error": "Commit message cannot be empty"}
    result = _run_git("commit", "-m", message)
    return _ok(result)


def git_create_branch(name: str, checkout: bool = True) -> dict[str, Any]:
    """Create a new branch and optionally check it out."""
    if checkout:
        return _ok(_run_git("checkout", "-b", name))
    return _ok(_run_git("branch", name))


def git_checkout(ref: str) -> dict[str, Any]:
    """Switch to a branch or commit."""
    return _ok(_run_git("checkout", ref))


def git_stash(message: str = "") -> dict[str, Any]:
    """Stash uncommitted changes."""
    args = ["stash", "push"]
    if message:
        args.extend(["-m", message])
    return _ok(_run_git(*args))


def git_stash_pop() -> dict[str, Any]:
    """Pop the most recent stash."""
    return _ok(_run_git("stash", "pop"))


def git_show_file(ref: str, path: str) -> dict[str, Any]:
    """Show the content of a file at a specific ref (commit/branch)."""
    result = _run_git("show", f"{ref}:{path}")
    return _ok(result)
