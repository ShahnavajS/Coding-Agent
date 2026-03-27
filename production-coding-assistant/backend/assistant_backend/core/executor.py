from __future__ import annotations

import logging
import re
from typing import Any

from assistant_backend.core.checkpoints import create_file_checkpoint
from assistant_backend.core.models import Plan
from assistant_backend.tools.filesystem_tool import write_text_file
from assistant_backend.validation.parser_checks import validate_content
from assistant_backend.validation.project_checks import validate_project_files

logger = logging.getLogger(__name__)

CODE_REQUEST_TOKENS = (
    "make",
    "create",
    "build",
    "write",
    "implement",
    "generate",
    "add",
    "fix",
    "update",
)
FILE_HEADER_RE = re.compile(r"^FILE:\s+(.+?)\s*$")


def should_execute(message: str) -> bool:
    return any(token in message.lower() for token in CODE_REQUEST_TOKENS)


def _normalize_relative_path(path: str) -> str:
    normalized: str = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized.removeprefix("./")
    if normalized.startswith("project/"):
        normalized = normalized.removeprefix("project/")
    if not normalized:
        raise ValueError("FILE path cannot be empty.")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        raise ValueError(f"Invalid FILE path: {path}")
    return normalized


def parse_file_blocks(raw_output: str) -> tuple[list[dict[str, str]], list[str]]:
    files_by_path: dict[str, str] = {}
    errors: list[str] = []
    current_path: str | None = None
    current_lines: list[str] = []
    saw_file_header = False
    duplicate_paths: set[str] = set()

    def finalize_block(path: str | None, lines: list[str]) -> None:
        if path is None:
            return
        content = "\n".join(lines).strip("\n")
        if not content.strip():
            errors.append(f"{path}: content is empty")
            return
        if path in files_by_path:
            duplicate_paths.add(path)
        files_by_path[path] = content + "\n"

    for line in raw_output.splitlines():
        header = FILE_HEADER_RE.match(line)
        if header:
            saw_file_header = True
            finalize_block(current_path, current_lines)
            try:
                current_path = _normalize_relative_path(header.group(1))
            except ValueError as exc:
                errors.append(str(exc))
                current_path = None
            current_lines = []
            continue

        if current_path is None:
            continue

        current_lines.append(line)

    finalize_block(current_path, current_lines)

    if duplicate_paths:
        logger.warning(
            "Duplicate FILE blocks detected for %s; keeping the last valid block for each path.",
            ", ".join(sorted(duplicate_paths)),
        )

    files = [
        {"path": path, "content": content}
        for path, content in files_by_path.items()
    ]
    for item in files:
        if "```" in item["content"]:
            errors.append(f"{item['path']}: remove markdown fences and return raw file content only")

    if not saw_file_header:
        errors.append("No FILE blocks were found in the model output.")

    return files, errors


def extract_structure_block(raw_output: str) -> str:
    lines: list[str] = []
    for line in raw_output.splitlines():
        if FILE_HEADER_RE.match(line):
            break
        if line.strip():
            lines.append(line.rstrip())
    return "\n".join(lines).strip()


def validate_generation_output(
    raw_output: str,
    plan: Plan,
    required_files: list[str] | None = None,
    require_structure: bool = True,
    known_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    files, errors = parse_file_blocks(raw_output)
    validations: list[dict[str, Any]] = []
    structure_block = extract_structure_block(raw_output)
    valid_files: list[dict[str, str]] = []
    target_files = required_files or plan.expected_files

    if not plan.project_structure.strip():
        errors.append("Planner did not produce a project structure.")
    if require_structure and not structure_block:
        errors.append("Model output is missing the project structure block before the FILE sections.")

    expected_count = len(target_files) or plan.expected_file_count or 2
    if len(files) < expected_count:
        errors.append(
            f"Expected at least {expected_count} files, but received {len(files)}."
        )

    if target_files:
        actual_paths: set[str] = {item["path"] for item in files}
        missing: list[str] = [path for path in target_files if path not in actual_paths]
        if missing:
            errors.append("Missing planned files: " + ", ".join(missing))

    for item in files:
        validation = validate_content(item["path"], item["content"]).to_dict()
        validations.append({"path": item["path"], "validation": validation})
        if not validation["ok"]:
            errors.extend(
                f"{item['path']}: {message}" for message in validation["messages"]
            )
        else:
            valid_files.append(item)

    invalid_paths: set[str] = set()
    if valid_files or known_files:
        project_context: dict[str, str] = dict(known_files or {})
        project_context.update({item["path"]: item["content"] for item in valid_files})
        project_issues = validate_project_files(
            plan,
            [{"path": path, "content": content} for path, content in project_context.items()],
        )
        invalid_paths = {issue["path"] for issue in project_issues}
        if invalid_paths:
            valid_files = [item for item in valid_files if item["path"] not in invalid_paths]
        errors.extend(
            f"{issue['path']}: {issue['message']}" for issue in project_issues
        )

    return {
        "ok": not errors,
        "files": files,
        "validFiles": valid_files,
        "errors": errors,
        "validations": validations,
        "structurePresent": bool(structure_block),
        "invalidPaths": sorted(invalid_paths),
    }


def write_generated_files(files: list[dict[str, str]], summary: str) -> dict[str, Any]:
    written: list[str] = []
    checkpoints: list[dict[str, str]] = []

    for item in files:
        checkpoints.append(create_file_checkpoint(item["path"], summary))
        write_text_file(item["path"], item["content"])
        written.append(item["path"])

    logger.info("Wrote %d generated files", len(written))
    return {"filesModified": written, "checkpoints": checkpoints}
