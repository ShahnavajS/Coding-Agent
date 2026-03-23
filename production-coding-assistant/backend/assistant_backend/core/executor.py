from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from assistant_backend.tools.structured_editor import preview_file_update

logger = logging.getLogger(__name__)

CODE_REQUEST_TOKENS = (
    "make", "create", "build", "write", "implement",
    "generate", "add", "fix", "update",
)

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"

# Patterns that indicate the provider returned a skeleton instead of real code.
SKELETON_PATTERNS = (
    r"#\s*implementation",
    r"#\s*TODO",
    r"#\s*your code here",
    r"#\s*add your",
    r"pass\s*$",
    r"\.\.\.\s*$",
    r"raise\s+NotImplementedError",
)


def should_execute(message: str) -> bool:
    """Return True if the message looks like a code generation request."""
    return any(token in message.lower() for token in CODE_REQUEST_TOKENS)


def infer_target_path(message: str, context: dict[str, Any]) -> str | None:
    """Try to extract a target file path from the message or context."""
    # Longer extensions first — tsx before ts, jsx before js
    explicit = re.search(
        r"([a-zA-Z0-9_\-./]+?\.(?:py|tsx|jsx|ts|js|json|md|html|css))",
        message,
    )
    if explicit:
        return explicit.group(1).lstrip("./")

    active_file = str(context.get("activeFilePath") or "").strip()
    if active_file and any(t in message.lower() for t in ("edit", "update", "fix")):
        return active_file

    return None


def extract_code_block(text: str) -> str | None:
    """Extract the LAST fenced code block from a provider response.

    We use the last block because providers often show an outline first and
    then the complete implementation at the end.
    """
    matches = list(re.finditer(r"```(?:[\w+-]+)?\n(.*?)```", text, re.DOTALL))
    if not matches:
        return None

    # Prefer the longest block — most likely to be the complete implementation.
    best = max(matches, key=lambda m: len(m.group(1)))
    code = best.group(1).strip() + "\n"
    return code if len(code.strip()) > 20 else None


def is_skeleton(code: str) -> bool:
    """Return True if the code looks like a placeholder/skeleton rather than real code."""
    for pattern in SKELETON_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
            return True
    # Also flag if the code is very short (< 5 meaningful lines)
    meaningful = [l for l in code.splitlines() if l.strip() and not l.strip().startswith("#")]
    return len(meaningful) < 4


def load_template(target_path: str) -> str | None:
    """Load a built-in template for the given target file, if one exists."""
    stem = Path(target_path).name
    template_path = TEMPLATES_DIR / f"{stem}.template"
    if template_path.exists():
        logger.debug("Loading template: %s", template_path)
        return template_path.read_text(encoding="utf-8")
    return None


def build_execution_preview(
    message: str,
    provider_message: str,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a diff preview for a code change, or return None if not applicable."""
    if not should_execute(message):
        return None

    target_path = infer_target_path(message, context)
    if not target_path:
        logger.debug("Could not infer target path — skipping execution preview")
        return None

    # Extract code from provider response
    code = extract_code_block(provider_message)

    # Reject skeletons — they look syntactically valid but are useless
    if code and is_skeleton(code):
        logger.info("Provider returned a skeleton for %s — discarding", target_path)
        code = None

    # Fall back to a built-in template if provider code is missing or skeletal
    content = code or load_template(target_path)
    if not content:
        logger.debug("No usable content for %s — skipping execution preview", target_path)
        return None

    preview = preview_file_update(target_path, content)
    validation = preview.get("validation", {})

    if not validation.get("ok"):
        template = load_template(target_path)
        if template and template != content:
            logger.info("Validation failed for %s — trying template fallback", target_path)
            preview = preview_file_update(target_path, template)
            validation = preview.get("validation", {})
        if not validation.get("ok"):
            logger.warning("Execution preview validation failed for %s", target_path)
            return None

    preview["path"] = target_path
    preview["summary"] = f"Prepared changes for {target_path}"
    logger.info("Execution preview ready for %s", target_path)
    return preview
