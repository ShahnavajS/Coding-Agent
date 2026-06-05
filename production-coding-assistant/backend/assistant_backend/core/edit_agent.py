"""edit_agent.py

Targeted Edit Mode — patches specific parts of existing files rather than
regenerating everything from scratch.

Triggered when the user's message is clearly a targeted modification:
  "fix the login bug in auth.py"
  "refactor the DatabaseService class in services/db.py"
  "add pagination to the /users route in routes.py"

This mode:
  1. Reads the target file(s) from the workspace
  2. Builds a surgical patch prompt with the full file content + instruction
  3. Validates the patched output
  4. Falls back to AGENT mode if the patch cannot be cleanly applied

Design goals (industrial standard):
- Zero data loss: checkpoint every file before overwriting
- Conservative: never silently discard failing patches — always surface errors
- Traceable: structured logs at each decision point
- Graceful degradation: falls back to agent mode on any failure
- Idempotent: running the same edit twice produces the same result
"""
from __future__ import annotations

import logging
import re
from typing import Any

from assistant_backend.core.checkpoints import create_file_checkpoint
from assistant_backend.core.context_builder import build_context_snapshot
from assistant_backend.core.models import AgentMode, Plan, PlanStep, StepStatus
from assistant_backend.core.planner import create_plan
from assistant_backend.providers.router import generate as generate_with_provider
from assistant_backend.storage.database import append_message
from assistant_backend.tools.filesystem_tool import (
    list_files_flat,
    read_text_file,
    write_text_file,
)
from assistant_backend.validation.parser_checks import validate_content

logger = logging.getLogger(__name__)

# ─── Heuristics ────────────────────────────────────────────────────────────────

_EDIT_TRIGGER_TOKENS = frozenset({
    "fix", "edit", "update", "change", "refactor", "rename", "move",
    "delete line", "remove line", "add method", "add function", "add class",
    "add field", "insert", "replace", "patch",
})

_FILE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])([A-Za-z0-9_./-]+?\.(?:py|tsx|jsx|ts|js|json|md|html|css|yml|yaml|txt))"
    r"(?![A-Za-z0-9_./-])"
)

_MAX_FILE_CHARS_FOR_EDIT = 8_000   # bytes sent to model for context
_MAX_EDIT_RETRIES = 2


# ─── Detection ─────────────────────────────────────────────────────────────────

def _is_edit_request(message: str) -> bool:
    """Return True if the message looks like a targeted single-file edit."""
    lowered = message.lower()
    has_trigger = any(tok in lowered for tok in _EDIT_TRIGGER_TOKENS)
    has_file = bool(_FILE_PATTERN.search(message))
    return has_trigger and has_file


def _extract_target_files(message: str, workspace_files: list[str]) -> list[str]:
    """Extract explicit file references from the message, validated against workspace."""
    workspace_set = set(workspace_files)
    found: list[str] = []
    for match in _FILE_PATTERN.finditer(message):
        candidate = match.group(1).strip().replace("\\", "/")
        while candidate.startswith("./"):
            candidate = candidate[2:]
        if candidate in workspace_set and candidate not in found:
            found.append(candidate)
    return found[:4]  # limit to 4 files per edit request


# ─── Prompt builder ────────────────────────────────────────────────────────────

def _build_edit_prompt(
    message: str,
    target_files: dict[str, str],
    context_block: str,
    retry_errors: list[str],
    attempt: int,
) -> str:
    file_blocks = "\n\n".join(
        f"FILE: {path}\n{content}" for path, content in target_files.items()
    )
    retry_section = ""
    if retry_errors:
        retry_section = (
            "\nPrevious attempt failed. Fix every issue below:\n"
            + "\n".join(f"- {e}" for e in retry_errors)
            + "\n"
        )

    return (
        "You are a surgical code editor. Your ONLY job is to apply the requested change.\n"
        "Rules:\n"
        "- Return ONLY the complete, modified file(s) using FILE: <path> headers.\n"
        "- No explanations outside FILE blocks.\n"
        "- No markdown fences.\n"
        "- Do NOT change logic unrelated to the requested edit.\n"
        "- Do NOT add unrelated imports, comments, or refactors.\n"
        "- Preserve the original code structure exactly except where the edit requires change.\n"
        "- Return ALL modified files in full — never return partial file content.\n"
        "- If the edit requires touching multiple files, return all of them.\n\n"
        f"{context_block}\n\n"
        "Current file(s) to edit:\n\n"
        f"{file_blocks}\n\n"
        f"Edit instruction: {message}\n"
        f"{retry_section}"
        f"\nAttempt: {attempt}/{_MAX_EDIT_RETRIES + 1}"
    )


# ─── Parse & validate ──────────────────────────────────────────────────────────

_FILE_HEADER_RE = re.compile(r"^FILE:\s+(.+?)\s*$")


def _parse_edited_files(raw: str) -> tuple[list[dict[str, str]], list[str]]:
    """Parse FILE: blocks from the model output."""
    files_by_path: dict[str, str] = {}
    errors: list[str] = []
    current_path: str | None = None
    current_lines: list[str] = []
    saw_header = False

    def _finalize(path: str | None, lines: list[str]) -> None:
        if path is None:
            return
        content = "\n".join(lines).strip("\n")
        if not content.strip():
            errors.append(f"{path}: edited content is empty")
            return
        files_by_path[path] = content + "\n"

    for line in raw.splitlines():
        header = _FILE_HEADER_RE.match(line)
        if header:
            saw_header = True
            _finalize(current_path, current_lines)
            raw_path = header.group(1).strip().replace("\\", "/")
            while raw_path.startswith("./"):
                raw_path = raw_path[2:]
            if raw_path.startswith("/") or ".." in raw_path.split("/"):
                errors.append(f"Invalid path in edit output: {raw_path}")
                current_path = None
            else:
                current_path = raw_path
            current_lines = []
            continue
        if current_path is not None:
            current_lines.append(line)

    _finalize(current_path, current_lines)

    if not saw_header:
        errors.append("Edit response did not contain any FILE: blocks.")

    for item_path, content in files_by_path.items():
        if "```" in content:
            errors.append(f"{item_path}: remove markdown fences from edit output")

    files = [{"path": p, "content": c} for p, c in files_by_path.items()]
    return files, errors


# ─── Main entry ────────────────────────────────────────────────────────────────

def run_edit_mode(
    message: str,
    session_id: str,
    context: dict[str, Any],
    provider_name: str | None,
) -> dict[str, Any]:
    """Run targeted edit mode: read → patch → validate → write.

    Falls back gracefully to a descriptive error dict if the patch cannot be
    applied cleanly after _MAX_EDIT_RETRIES attempts.
    """
    workspace_files = [
        item["path"] for item in list_files_flat() if item["type"] == "file"
    ]
    plan = create_plan(message, workspace_files)

    # Discover which files in the workspace the message is targeting
    target_paths = _extract_target_files(message, workspace_files)
    if not target_paths:
        # Could not identify specific file — fall back to agent mode signal
        logger.warning(
            "edit_agent: no target files found in workspace for message %r — "
            "caller should fall back to agent mode",
            message[:80],
        )
        return {
            "message": (
                "Could not identify a specific file to edit. "
                "Try mentioning the exact filename (e.g. 'fix the bug in auth.py')."
            ),
            "mode": AgentMode.EDIT,
            "steps": [],
            "filesModified": [],
            "plan": plan.to_dict(),
            "providerStatus": {"used": False, "provider": provider_name or "none"},
            "fallback": True,   # signal to caller to retry with agent mode
        }

    # Read all target files
    target_files: dict[str, str] = {}
    unreadable: list[str] = []
    for path in target_paths:
        try:
            content = read_text_file(path)
            if len(content) > _MAX_FILE_CHARS_FOR_EDIT:
                content = content[:_MAX_FILE_CHARS_FOR_EDIT] + "\n… (file truncated for edit context)"
            target_files[path] = content
        except Exception as exc:
            logger.warning("edit_agent: could not read %r: %s", path, exc)
            unreadable.append(path)

    if not target_files:
        return {
            "message": f"Could not read target file(s): {', '.join(unreadable)}",
            "mode": AgentMode.EDIT,
            "steps": [],
            "filesModified": [],
            "plan": plan.to_dict(),
            "providerStatus": {"used": False, "provider": provider_name or "none"},
        }

    # Build context snapshot for richer prompt
    snapshot = build_context_snapshot(session_id, plan.files_of_interest, context)
    context_block = snapshot.to_prompt_block()

    # Build plan steps for frontend visibility
    read_step = PlanStep(
        id="edit-read",
        name="Read Target Files",
        status=StepStatus.COMPLETED,
        description=f"Read {len(target_files)} file(s) for editing.",
        details=", ".join(target_files.keys()),
    )
    patch_step = PlanStep(
        id="edit-patch",
        name="Apply Edit",
        status=StepStatus.PENDING,
        description="Sent edit instruction to model and applied patch.",
    )
    validate_step = PlanStep(
        id="edit-validate",
        name="Validate",
        status=StepStatus.PENDING,
        description="Validated syntax and structure of patched files.",
    )
    write_step = PlanStep(
        id="edit-write",
        name="Write Changes",
        status=StepStatus.PENDING,
        description="Wrote validated changes to workspace.",
    )
    plan.steps.extend([read_step, patch_step, validate_step, write_step])

    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    retry_errors: list[str] = []
    files_modified: list[str] = []

    for attempt in range(1, _MAX_EDIT_RETRIES + 2):  # +2 so range gives correct count
        prompt = _build_edit_prompt(
            message, target_files, context_block, retry_errors, attempt
        )

        try:
            response = generate_with_provider(prompt, provider_name=provider_name)
            provider_status = {
                "used": True,
                "provider": response.provider,
                "model": response.model,
            }
            patch_step.status = StepStatus.RUNNING
            logger.info(
                "edit_agent: attempt %d/%d — provider %s (%d chars)",
                attempt, _MAX_EDIT_RETRIES + 1, response.provider, len(response.content),
            )
        except Exception as exc:
            logger.exception("edit_agent: provider call failed: %s", exc)
            patch_step.status = StepStatus.FAILED
            patch_step.error = str(exc)
            validate_step.status = StepStatus.FAILED
            write_step.status = StepStatus.FAILED
            return {
                "message": f"Edit failed — provider error: {exc}",
                "mode": AgentMode.EDIT,
                "steps": [s.to_dict() for s in plan.steps],
                "filesModified": [],
                "plan": plan.to_dict(),
                "providerStatus": provider_status,
            }

        edited_files, parse_errors = _parse_edited_files(response.content)

        # Per-file syntax validation
        validation_errors: list[str] = list(parse_errors)
        valid_files: list[dict[str, str]] = []
        for item in edited_files:
            result = validate_content(item["path"], item["content"]).to_dict()
            if result["ok"]:
                valid_files.append(item)
            else:
                for msg in result["messages"]:
                    validation_errors.append(f"{item['path']}: {msg}")

        if validation_errors:
            patch_step.status = StepStatus.FAILED
            validate_step.status = StepStatus.FAILED
            validate_step.details = " | ".join(validation_errors)
            retry_errors = validation_errors
            logger.warning(
                "edit_agent: attempt %d failed validation: %s",
                attempt, validation_errors,
            )
            if attempt > _MAX_EDIT_RETRIES:
                write_step.status = StepStatus.FAILED
                return {
                    "message": (
                        "Edit failed validation after all attempts.\n\n"
                        "Issues:\n" + "\n".join(f"- {e}" for e in validation_errors)
                    ),
                    "mode": AgentMode.EDIT,
                    "steps": [s.to_dict() for s in plan.steps],
                    "filesModified": [],
                    "plan": plan.to_dict(),
                    "providerStatus": provider_status,
                }
            continue  # retry

        # All validated — checkpoint and write
        patch_step.status = StepStatus.COMPLETED
        validate_step.status = StepStatus.COMPLETED
        validate_step.details = f"Validated {len(valid_files)} file(s)"

        for item in valid_files:
            try:
                create_file_checkpoint(item["path"], f"Pre-edit checkpoint for session {session_id}")
                write_text_file(item["path"], item["content"])
                files_modified.append(item["path"])
                logger.info("edit_agent: wrote edited file %r", item["path"])
            except Exception as exc:
                logger.exception("edit_agent: failed to write %r: %s", item["path"], exc)
                write_step.status = StepStatus.FAILED
                write_step.error = str(exc)
                return {
                    "message": f"Edit patch was valid but write failed for {item['path']}: {exc}",
                    "mode": AgentMode.EDIT,
                    "steps": [s.to_dict() for s in plan.steps],
                    "filesModified": files_modified,
                    "plan": plan.to_dict(),
                    "providerStatus": provider_status,
                }

        write_step.status = StepStatus.COMPLETED
        write_step.details = ", ".join(files_modified)

        file_list = "\n".join(f"- {p}" for p in files_modified)
        return {
            "message": (
                f"Edit applied successfully to {len(files_modified)} file(s).\n\n"
                f"Files modified:\n{file_list}"
            ),
            "mode": AgentMode.EDIT,
            "steps": [s.to_dict() for s in plan.steps],
            "filesModified": files_modified,
            "plan": plan.to_dict(),
            "providerStatus": provider_status,
        }

    # Should never be reached but satisfies type checkers
    return {
        "message": "Edit agent exited unexpectedly.",
        "mode": AgentMode.EDIT,
        "steps": [s.to_dict() for s in plan.steps],
        "filesModified": [],
        "plan": plan.to_dict(),
        "providerStatus": provider_status,
    }
