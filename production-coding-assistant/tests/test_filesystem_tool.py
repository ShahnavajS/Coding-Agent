"""Tests for assistant_backend.tools.filesystem_tool — safe_resolve() path security."""
from __future__ import annotations

import gc
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def make_mock_settings(tmp_path: Path):
    """Return a mock AppSettings pointing at tmp_path as the workspace."""
    settings = MagicMock()
    settings.workspace_path = str(tmp_path)
    return settings


def _patch_settings(tmp_path: Path):
    """Patch get_cached_settings in the filesystem_tool module."""
    return patch(
        "assistant_backend.tools.filesystem_tool.get_cached_settings",
        return_value=make_mock_settings(tmp_path),
    )


class TestSafeResolve:
    def test_relative_path_inside_workspace_is_allowed(self, tmp_path):
        with _patch_settings(tmp_path):
            from assistant_backend.tools import filesystem_tool
            result = filesystem_tool.safe_resolve("subdir/file.py")
            assert str(result).startswith(str(tmp_path))

    def test_absolute_path_outside_workspace_is_denied(self, tmp_path):
        with _patch_settings(tmp_path):
            from assistant_backend.tools import filesystem_tool
            with pytest.raises(ValueError, match="Access denied"):
                filesystem_tool.safe_resolve("/etc/passwd")
            # Force GC to close any SQLite connections opened during the test.
            gc.collect()

    def test_path_traversal_is_denied(self, tmp_path):
        with _patch_settings(tmp_path):
            from assistant_backend.tools import filesystem_tool
            with pytest.raises(ValueError, match="Access denied"):
                filesystem_tool.safe_resolve("../../etc/passwd")

    def test_prefix_bypass_is_denied(self, tmp_path):
        """Ensure /workspace-evil is not allowed just because /workspace is the root."""
        evil_path = tmp_path.parent / (tmp_path.name + "-evil") / "secret.txt"
        with _patch_settings(tmp_path):
            from assistant_backend.tools import filesystem_tool
            with pytest.raises(ValueError, match="Access denied"):
                filesystem_tool.safe_resolve(str(evil_path))
