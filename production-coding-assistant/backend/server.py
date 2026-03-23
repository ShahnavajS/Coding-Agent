"""Thin Flask entrypoint for the modular coding assistant backend."""

from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from assistant_backend.api.app import create_app
from assistant_backend.config import load_app_settings
from assistant_backend.storage.database import init_db
from assistant_backend.tools.filesystem_tool import workspace_root


def configure_logging() -> None:
    """Set up structured logging for the application."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


configure_logging()
logger = logging.getLogger(__name__)

settings = load_app_settings()
init_db()
app = create_app()


if __name__ == "__main__":
    # Read debug flag from environment — never hardcode debug=True in production.
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    logger.info("Starting AI Coding Assistant Backend Server...")
    logger.info("Workspace: %s", workspace_root())
    logger.info(
        "Server running at http://%s:%d (debug=%s)",
        settings.backend_host,
        settings.backend_port,
        debug_mode,
    )
    logger.info("Architecture: planner + diff preview + checkpoints + provider settings")

    app.run(
        host=settings.backend_host,
        port=settings.backend_port,
        debug=debug_mode,
        use_reloader=debug_mode,
    )
