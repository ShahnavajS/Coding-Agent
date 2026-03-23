from __future__ import annotations

import logging
from pathlib import Path
from time import time_ns

from assistant_backend.config import APP_DIR
from assistant_backend.storage.database import get_checkpoint, store_checkpoint
from assistant_backend.tools.filesystem_tool import safe_resolve, write_text_file

logger = logging.getLogger(__name__)


def create_file_checkpoint(path: str, summary: str) -> dict[str, str]:
    """Snapshot the current content of a file before a write operation.

    Snapshots are stored in .assistant/checkpoints/ with nanosecond timestamps
    to avoid collisions. Empty string is stored if the file does not yet exist.
    """
    snapshot_dir = APP_DIR / "checkpoints"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"{Path(path).name}.{time_ns()}.bak"
    source = safe_resolve(path)
    existing_content = source.read_text(encoding="utf-8") if source.exists() else ""
    snapshot_path.write_text(existing_content, encoding="utf-8")
    checkpoint = store_checkpoint(path, str(snapshot_path), summary)
    logger.info("Checkpoint created for %s -> %s", path, snapshot_path.name)
    return checkpoint


def rollback_checkpoint(checkpoint_id: str) -> dict[str, str]:
    """Restore a file to its snapshot state.

    Raises ValueError if the checkpoint or its snapshot file cannot be found.
    """
    checkpoint = get_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise ValueError(f"Checkpoint not found: {checkpoint_id}")
    snapshot_path = Path(checkpoint["snapshotPath"])
    if not snapshot_path.exists():
        raise ValueError(f"Checkpoint snapshot is missing: {snapshot_path}")
    content = snapshot_path.read_text(encoding="utf-8")
    write_text_file(checkpoint["path"], content)
    logger.info("Rolled back %s to checkpoint %s", checkpoint["path"], checkpoint_id)
    return checkpoint
