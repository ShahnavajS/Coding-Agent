"""Pytest configuration and shared fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the backend directory is on the path so tests can import assistant_backend.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
