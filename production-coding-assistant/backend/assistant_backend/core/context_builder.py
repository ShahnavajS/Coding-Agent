"""context_builder.py

Builds a ContextSnapshot that is injected into every agent prompt so the model
understands the current state of the project before generating or editing code.

This is the key piece that makes the agent codebase-aware — similar to how
Cursor/Claude Code read the open file and related files before responding.
"""
from __future__ import annotations

import logging
from typing import Any

from assistant_backend.core.models import ContextSnapshot
from assistant_backend.storage.database import get_messages
from assistant_backend.tools.filesystem_tool import read_text_file

logger = logging.getLogger(__name__)

# Max chars to include per file snippet
_MAX_FILE_CHARS = 2_000
# Max chars for the active (open) file
_MAX_ACTIVE_FILE_CHARS = 3_000
# Number of recent messages to include in history
_HISTORY_MESSAGES = 8


def _safe_read(path: str, max_chars: int) -> str:
    """Read a workspace file, returning a truncated string on any error."""
    try:
        content = read_text_file(path)
        if len(content) > max_chars:
            return content[:max_chars] + "\n… (truncated)"
        return content
    except Exception as exc:
        logger.debug("context_builder: could not read %r: %s", path, exc)
        return ""


def _load_history(session_id: str | None) -> list[dict[str, str]]:
    """Return the last N messages for the session, formatted as {role, content}."""
    if not session_id:
        return []
    try:
        messages = get_messages(session_id)
        recent = messages[-_HISTORY_MESSAGES:]
        return [
            {"role": m["role"], "content": str(m.get("content", ""))}
            for m in recent
        ]
    except Exception as exc:
        logger.warning("context_builder: failed to load history for %s: %s", session_id, exc)
        return []


def build_context_snapshot(
    session_id: str | None,
    files_of_interest: list[str],
    context: dict[str, Any],
) -> ContextSnapshot:
    """Build a ContextSnapshot from session history and workspace files.

    Args:
        session_id: Active session to load history from.
        files_of_interest: Paths (relative to workspace) identified by the planner.
        context: Raw context dict from the frontend (activeFilePath, selectedText…).

    Returns:
        A ContextSnapshot ready to call .to_prompt_block() on.
    """
    active_file_path: str = context.get("activeFilePath") or ""
    selected_text: str = context.get("selectedText") or ""

    # 1. Active file content
    active_file_content = ""
    if active_file_path:
        active_file_content = _safe_read(active_file_path, _MAX_ACTIVE_FILE_CHARS)

    # 2. Other files of interest (skip the active file — already captured above)
    file_snippets: dict[str, str] = {}
    for path in files_of_interest:
        if path == active_file_path:
            continue
        if len(file_snippets) >= 5:
            break
        snippet = _safe_read(path, _MAX_FILE_CHARS)
        if snippet:
            file_snippets[path] = snippet

    # 3. Recent conversation history
    recent_messages = _load_history(session_id)

    logger.debug(
        "context_builder: snapshot built — active=%r snippets=%d history=%d",
        active_file_path,
        len(file_snippets),
        len(recent_messages),
    )

    return ContextSnapshot(
        active_file_path=active_file_path,
        active_file_content=active_file_content,
        file_snippets=file_snippets,
        recent_messages=recent_messages,
        selected_text=selected_text,
    )
