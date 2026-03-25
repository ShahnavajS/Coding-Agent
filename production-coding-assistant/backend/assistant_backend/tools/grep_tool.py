"""Grep / Search tool — recursive text search inside the workspace.

Provides regex and literal search across files, with context lines,
file-type filtering, and result limits to prevent memory blowup.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from assistant_backend.tools.filesystem_tool import workspace_root

logger = logging.getLogger(__name__)

# Hard caps to keep search results manageable.
MAX_RESULTS = 200
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB — skip binaries / huge files
CONTEXT_LINES_DEFAULT = 2

# Binary/generated directories that should always be skipped.
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "out", ".assistant",
})


@dataclass
class SearchMatch:
    """A single search match inside a file."""
    file: str
    line: int
    column: int
    text: str
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "text": self.text,
            "contextBefore": self.context_before,
            "contextAfter": self.context_after,
        }


def _should_skip_dir(dirname: str) -> bool:
    return dirname in _SKIP_DIRS or dirname.startswith(".")


def _matches_globs(filename: str, include_globs: list[str]) -> bool:
    if not include_globs:
        return True
    return any(fnmatch.fnmatch(filename, g) for g in include_globs)


def grep_workspace(
    query: str,
    *,
    is_regex: bool = False,
    case_sensitive: bool = True,
    include_globs: list[str] | None = None,
    context_lines: int = CONTEXT_LINES_DEFAULT,
    max_results: int = MAX_RESULTS,
) -> dict[str, Any]:
    """Search the workspace for a pattern and return structured results.

    Parameters
    ----------
    query : str
        The search term — literal string or regex pattern.
    is_regex : bool
        If True, treat *query* as a Python regex.
    case_sensitive : bool
        Whether the search is case-sensitive.
    include_globs : list[str] | None
        Optional glob patterns to filter files (e.g. ``["*.py", "*.ts"]``).
    context_lines : int
        Number of surrounding lines to include with each match.
    max_results : int
        Maximum number of matches to return.

    Returns
    -------
    dict
        ``{"matches": [...], "totalMatches": int, "truncated": bool, "query": str}``
    """
    if not query:
        return {"matches": [], "totalMatches": 0, "truncated": False, "query": query}

    root = workspace_root()
    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        pattern = re.compile(query, flags) if is_regex else re.compile(re.escape(query), flags)
    except re.error as exc:
        return {"matches": [], "totalMatches": 0, "truncated": False,
                "query": query, "error": f"Invalid regex: {exc}"}

    include = include_globs or []
    matches: list[SearchMatch] = []
    total = 0
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place so os.walk skips them.
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for filename in filenames:
            if not _matches_globs(filename, include):
                continue
            full_path = Path(dirpath) / filename
            if full_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue

            try:
                lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except (OSError, UnicodeDecodeError):
                continue

            rel_path = str(full_path.relative_to(root)).replace("\\", "/")

            for idx, line in enumerate(lines):
                for m in pattern.finditer(line):
                    total += 1
                    if len(matches) < max_results:
                        before_start = max(0, idx - context_lines)
                        after_end = min(len(lines), idx + context_lines + 1)
                        matches.append(SearchMatch(
                            file=rel_path,
                            line=idx + 1,
                            column=m.start() + 1,
                            text=line,
                            context_before=lines[before_start:idx],
                            context_after=lines[idx + 1:after_end],
                        ))
                    else:
                        truncated = True

    logger.info("grep_workspace: %d matches for %r (truncated=%s)", total, query, truncated)
    return {
        "matches": [m.to_dict() for m in matches],
        "totalMatches": total,
        "truncated": truncated,
        "query": query,
    }


def find_and_replace(
    path: str,
    search: str,
    replace: str,
    *,
    is_regex: bool = False,
    case_sensitive: bool = True,
    preview_only: bool = True,
) -> dict[str, Any]:
    """Find and replace text inside a single file.

    When *preview_only* is True (default), returns a preview diff
    without writing changes. Set to False to write changes atomically.

    Parameters
    ----------
    path : str
        Workspace-relative file path.
    search : str
        The text or regex pattern to find.
    replace : str
        The replacement string. Supports regex backreferences when *is_regex* is True.
    is_regex : bool
        Treat *search* as a regex pattern.
    case_sensitive : bool
        Whether the match is case-sensitive.
    preview_only : bool
        If True, return the diff preview without modifying the file.

    Returns
    -------
    dict
        ``{"path": str, "replacements": int, "preview": str, "applied": bool}``
    """
    from assistant_backend.tools.filesystem_tool import safe_resolve, read_text_file, write_text_file

    target = safe_resolve(path)
    if not target.exists():
        raise ValueError(f"File not found: {path}")

    original = read_text_file(path)
    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        pattern = re.compile(search, flags) if is_regex else re.compile(re.escape(search), flags)
    except re.error as exc:
        raise ValueError(f"Invalid regex: {exc}")

    modified, count = pattern.subn(replace, original)

    if count == 0:
        return {"path": path, "replacements": 0, "preview": "", "applied": False}

    # Build a simple unified-diff-style preview
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    import difflib
    diff = "".join(difflib.unified_diff(
        orig_lines, mod_lines,
        fromfile=f"a/{path}", tofile=f"b/{path}",
    ))

    applied = False
    if not preview_only:
        write_text_file(path, modified)
        applied = True
        logger.info("find_and_replace: %d replacements applied to %s", count, path)

    return {
        "path": path,
        "replacements": count,
        "preview": diff,
        "applied": applied,
    }
