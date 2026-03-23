from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from assistant_backend.core.checkpoints import create_file_checkpoint
from assistant_backend.storage.database import (
    delete_pending_diff,
    get_pending_diff,
    store_pending_diff,
)
from assistant_backend.tools.filesystem_tool import read_text_file, safe_resolve
from assistant_backend.validation.parser_checks import validate_content


def preview_file_update(path: str, modified_content: str) -> dict[str, Any]:
    target = safe_resolve(path)
    original_content = read_text_file(path) if target.exists() else ""
    validation = validate_content(path, modified_content).to_dict()
    return store_pending_diff(path, original_content, modified_content, validation)


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, encoding="utf-8", dir=str(target.parent)
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    os.replace(temp_path, target)


def apply_pending_diff(diff_id: str) -> dict[str, Any]:
    pending = get_pending_diff(diff_id)
    if pending is None:
        raise ValueError("Diff not found")

    validation = pending["validation"]
    if not validation.get("ok"):
        raise ValueError("Refusing to apply invalid content")

    target = safe_resolve(pending["path"])
    checkpoint = create_file_checkpoint(pending["path"], "Pre-apply checkpoint")
    _atomic_write(target, pending["modifiedContent"])
    delete_pending_diff(diff_id)
    return {
        "path": pending["path"],
        "checkpoint": checkpoint,
        "validation": validation,
    }
