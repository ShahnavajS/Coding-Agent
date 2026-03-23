from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from assistant_backend.config import get_cached_settings

logger = logging.getLogger(__name__)


def workspace_root() -> Path:
    """Return the resolved workspace root path, creating it if needed."""
    settings = get_cached_settings()
    root = Path(settings.workspace_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_resolve(path: str) -> Path:
    """Resolve a path and ensure it is inside the workspace root.

    Uses Path.is_relative_to() instead of startswith() to prevent
    path-prefix bypass attacks (e.g. /workspace-evil vs /workspace).
    """
    root = workspace_root()
    if Path(path).is_absolute():
        target = Path(path).resolve()
    else:
        target = (root / path).resolve()

    # is_relative_to is available in Python 3.9+; it correctly handles
    # cases where a path shares a prefix but is outside the root.
    try:
        target.relative_to(root)
    except ValueError:
        logger.warning("Path traversal attempt blocked: %r (root: %s)", path, root)
        raise ValueError(f"Access denied: path is outside workspace root")

    return target


def list_files_flat() -> list[dict[str, Any]]:
    """Return a flat list of all files and folders in the workspace."""
    root = workspace_root()
    items: list[dict[str, Any]] = []
    for current_root, dirs, files in os.walk(root):
        rel_root = os.path.relpath(current_root, root)
        rel_root = "" if rel_root == "." else rel_root.replace("\\", "/")
        for dirname in dirs:
            rel_path = f"{rel_root}/{dirname}".strip("/")
            items.append({"name": dirname, "path": rel_path, "type": "folder"})
        for filename in files:
            file_path = Path(current_root) / filename
            rel_path = f"{rel_root}/{filename}".strip("/")
            items.append(
                {
                    "name": filename,
                    "path": rel_path,
                    "type": "file",
                    "size": file_path.stat().st_size,
                }
            )
    return items


def read_text_file(path: str) -> str:
    target = safe_resolve(path)
    return target.read_text(encoding="utf-8")


def create_path(path: str, path_type: str, content: str = "") -> dict[str, Any]:
    target = safe_resolve(path)
    if target.exists():
        raise ValueError(f"Path already exists: {path}")

    if path_type == "folder":
        target.mkdir(parents=True, exist_ok=False)
        logger.info("Created folder: %s", path)
        return {"path": path, "type": "folder"}

    if path_type != "file":
        raise ValueError(f"Unsupported path type: {path_type!r}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info("Created file: %s (%d bytes)", path, len(content))
    return {"path": path, "type": "file", "size": len(content)}


def write_text_file(path: str, content: str) -> dict[str, Any]:
    target = safe_resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info("Wrote file: %s (%d bytes)", path, len(content))
    return {"path": path, "size": len(content)}


def delete_path(path: str) -> None:
    target = safe_resolve(path)
    if target.is_dir():
        for child in sorted(target.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        target.rmdir()
        logger.info("Deleted directory: %s", path)
    elif target.exists():
        target.unlink()
        logger.info("Deleted file: %s", path)
    else:
        logger.warning("delete_path called on non-existent path: %s", path)
