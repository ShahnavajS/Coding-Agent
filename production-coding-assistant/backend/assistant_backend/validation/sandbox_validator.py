from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from assistant_backend.config import APP_DIR, get_cached_settings
from assistant_backend.tools.docker_sandbox_tool import docker_available, run_in_sandbox

logger = logging.getLogger(__name__)


def _safe_temp_write(root: Path, relative_path: str, content: str) -> None:
    normalized = relative_path.strip().replace("\\", "/")
    if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
        raise ValueError(f"Invalid generated file path for sandbox: {relative_path}")
    target = (root / normalized).resolve()
    target.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _has_python_files(files: list[dict[str, str]]) -> bool:
    return any(item["path"].endswith(".py") for item in files)


def _package_json_dirs(files: list[dict[str, str]]) -> list[str]:
    dirs: list[str] = []
    for item in files:
        path = item["path"].replace("\\", "/")
        if not path.endswith("package.json"):
            continue
        parent = str(Path(path).parent).replace("\\", "/")
        dirs.append("" if parent == "." else parent)
    return list(dict.fromkeys(dirs))


def _format_command(command: list[str]) -> str:
    return " ".join(command)


def _summarize_result(result: dict[str, Any]) -> str:
    command = _format_command(result.get("command", []))
    image = result.get("image", "")
    if result.get("skipped"):
        return f"SKIPPED {image}: {command} ({result.get('error')})"
    if result.get("ok"):
        return f"PASS {image}: {command}"
    detail = result.get("error") or result.get("stderr") or result.get("stdout")
    return f"FAIL {image}: {command} ({str(detail).strip()})"


def validate_files_in_docker_sandbox(files: list[dict[str, str]]) -> dict[str, Any]:
    """Run lightweight Docker validation against generated files.

    The validator writes files into a temporary directory, mounts that directory
    into Docker, and runs safe syntax/manifest checks. It avoids dependency
    installation by default so validation remains deterministic and network-free.
    """
    settings = get_cached_settings().docker_sandbox
    if not settings.enabled:
        return {
            "ok": True,
            "enabled": False,
            "skipped": True,
            "errors": [],
            "details": "Docker sandbox validation is disabled.",
            "commands": [],
        }

    available, reason = docker_available()
    if not available:
        return {
            "ok": not settings.fail_on_error,
            "enabled": True,
            "skipped": True,
            "errors": [reason] if settings.fail_on_error else [],
            "details": f"Docker sandbox skipped: {reason}",
            "commands": [],
        }

    sandbox_root = APP_DIR / "sandboxes"
    sandbox_root.mkdir(parents=True, exist_ok=True)
    command_results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="generated-", dir=sandbox_root) as temp_dir:
        temp_path = Path(temp_dir).resolve()
        for item in files:
            _safe_temp_write(temp_path, item["path"], item["content"])

        if _has_python_files(files):
            command_results.append(
                run_in_sandbox(
                    temp_path,
                    settings.python_image,
                    ["python", "-m", "compileall", "."],
                ).to_dict()
            )

        for package_dir in _package_json_dirs(files):
            package_path = "/workspace" if not package_dir else f"/workspace/{package_dir}"
            command_results.append(
                run_in_sandbox(
                    temp_path,
                    settings.node_image,
                    [
                        "node",
                        "-e",
                        (
                            "const fs=require('fs');"
                            "JSON.parse(fs.readFileSync('package.json','utf8'));"
                            "console.log('package.json ok');"
                        ),
                    ],
                    workdir=package_path,
                ).to_dict()
            )

    if not command_results:
        return {
            "ok": True,
            "enabled": True,
            "skipped": True,
            "errors": [],
            "details": "Docker sandbox found no supported validation commands for these files.",
            "commands": [],
        }

    hard_failures = [
        result for result in command_results
        if not result.get("ok") and not result.get("skipped")
    ]
    skipped_failures = [
        result for result in command_results
        if result.get("skipped") and result.get("error")
    ]
    errors = [
        _summarize_result(result)
        for result in hard_failures
    ]
    if settings.fail_on_error:
        errors.extend(_summarize_result(result) for result in skipped_failures)

    details = "\n".join(_summarize_result(result) for result in command_results)
    logger.info("Docker sandbox validation result: %s", json.dumps({
        "ok": not errors,
        "commands": len(command_results),
    }))
    return {
        "ok": not errors,
        "enabled": True,
        "skipped": False,
        "errors": errors,
        "details": details,
        "commands": command_results,
    }
