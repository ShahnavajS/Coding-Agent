from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

from assistant_backend.core.models import ValidationResult

logger = logging.getLogger(__name__)

# Map file extensions to language names used throughout the backend.
_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".json": "json",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".md": "markdown",
    ".css": "css",
    ".html": "html",
}


def detect_language(path: str) -> str:
    """Return the language identifier for a given file path based on its extension."""
    ext = Path(path).suffix.lower()
    return _EXT_TO_LANGUAGE.get(ext, "text")


def validate_content(path: str, content: str) -> ValidationResult:
    """Parse and validate file content for the language inferred from path.

    Currently performs AST-level checks for Python and JSON.
    All other languages pass through with an informational message.
    """
    language = detect_language(path)
    messages: list[str] = []
    parser = "basic"
    ok = True

    if not content.strip():
        return ValidationResult(
            ok=False,
            language=language,
            parser=parser,
            messages=["Content is empty."],
        )

    if language == "python":
        parser = "ast"
        try:
            ast.parse(content)
            messages.append("Python syntax is valid.")
            logger.debug("Python validation passed for %s", path)
        except SyntaxError as exc:
            ok = False
            messages.append(f"SyntaxError: {exc.msg} (line {exc.lineno})")
            logger.info("Python validation failed for %s: %s", path, exc)

    elif language == "json":
        parser = "json"
        try:
            json.loads(content)
            messages.append("JSON is valid.")
            logger.debug("JSON validation passed for %s", path)
        except json.JSONDecodeError as exc:
            ok = False
            messages.append(f"JSONDecodeError: {exc.msg} (line {exc.lineno})")
            logger.info("JSON validation failed for %s: %s", path, exc)

    else:
        # No structural parser available — accept the content but note it.
        messages.append(f"No syntax parser configured for {language}; accepted as-is.")
        logger.debug("No parser for language %r (%s), accepting content", language, path)

    return ValidationResult(ok=ok, language=language, parser=parser, messages=messages)
