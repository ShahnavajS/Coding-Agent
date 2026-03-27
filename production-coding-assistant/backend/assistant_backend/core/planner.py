from __future__ import annotations

import logging
import re
import uuid

from assistant_backend.core.models import Plan, PlanStep, RiskLevel

logger = logging.getLogger(__name__)

_HIGH_RISK_TOKENS = frozenset({"delete", "remove", "drop", "reset", "wipe", "purge"})
_LOW_RISK_TOKENS = frozenset({"read", "inspect", "explain", "show", "list", "describe"})
_CODE_REQUEST_TOKENS = frozenset({"make", "create", "build", "write", "implement", "generate", "add"})
_FILE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])([A-Za-z0-9_./-]+?\.(?:py|tsx|jsx|ts|js|json|md|html|css|yml|yaml|txt))(?![A-Za-z0-9_./-])"
)


def _classify_risk(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in _HIGH_RISK_TOKENS):
        return RiskLevel.HIGH
    if any(token in lowered for token in _LOW_RISK_TOKENS):
        return RiskLevel.LOW
    return RiskLevel.MEDIUM


def _is_code_request(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in _CODE_REQUEST_TOKENS)


def _find_files_of_interest(message: str, workspace_files: list[str]) -> list[str]:
    tokens = set(message.lower().replace(",", " ").split())
    matched = [
        path for path in workspace_files
        if any(token and token in path.lower() for token in tokens)
    ]
    return matched[:5] if matched else workspace_files[:3]


def _extract_explicit_files(message: str) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for match in _FILE_PATTERN.finditer(message):
        path = match.group(1).strip().replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        if path and path not in seen:
            seen.add(path)
            results.append(path)
    return results


def _infer_default_structure(message: str, explicit_files: list[str]) -> list[str]:
    lowered = message.lower()
    inferred = list(explicit_files)

    if (
        ("full-stack" in lowered or "full stack" in lowered or "backend" in lowered)
        and "fastapi" in lowered
        and "react" in lowered
    ):
        inferred.extend(
            [
                "README.md",
                ".env.example",
                "requirements.txt",
                "backend/app/main.py",
                "backend/app/config.py",
                "backend/app/database.py",
                "backend/app/models.py",
                "backend/app/schemas.py",
                "backend/app/security.py",
                "backend/app/routes.py",
                "backend/app/services.py",
                "frontend/package.json",
                "frontend/tsconfig.json",
                "frontend/vite.config.ts",
                "frontend/index.html",
                "frontend/src/main.tsx",
                "frontend/src/App.tsx",
                "frontend/src/pages/LoginPage.tsx",
                "frontend/src/pages/TodosPage.tsx",
                "frontend/src/components/TodoFilters.tsx",
                "frontend/src/styles.css",
            ]
        )
    elif "calculator" in lowered:
        inferred.extend(
            [
                "app.py",
                "calculator.py",
                "operations.py",
                "cli.py",
                "tests/test_calculator.py",
                "README.md",
            ]
        )
    elif "api" in lowered or "backend" in lowered or "server" in lowered:
        inferred.extend(
            [
                "app.py",
                "routes.py",
                "service.py",
                "models.py",
                "storage.py",
                "requirements.txt",
                "README.md",
            ]
        )
    elif "react" in lowered or "frontend" in lowered or "ui" in lowered:
        inferred.extend(
            [
                "src/App.tsx",
                "src/components/AppShell.tsx",
                "src/components/Sidebar.tsx",
                "src/lib/types.ts",
                "src/styles/app.css",
                "README.md",
            ]
        )
    elif _is_code_request(message):
        inferred.extend(
            [
                "app.py",
                "core.py",
                "cli.py",
                "tests/test_app.py",
                "README.md",
            ]
        )

    deduped: list[str] = []
    seen: set[str] = set()
    for path in inferred:
        normalized = path.strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _render_tree(paths: list[str]) -> str:
    if not paths:
        return "(no new files planned)"

    tree: dict[str, dict] = {}
    for path in paths:
        node = tree
        parts = [part for part in path.split("/") if part]
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = {}

    lines: list[str] = ["project/"]

    def walk(node: dict[str, dict], prefix: str = "") -> None:
        keys = sorted(node.keys())
        for index, key in enumerate(keys):
            connector = "`-- " if index == len(keys) - 1 else "|-- "
            lines.append(f"{prefix}{connector}{key}")
            child = node[key]
            if child:
                extension = "    " if index == len(keys) - 1 else "|   "
                walk(child, prefix + extension)

    walk(tree)
    return "\n".join(lines)


def create_plan(message: str, workspace_files: list[str]) -> Plan:
    risk_level = _classify_risk(message)
    explicit_files = _extract_explicit_files(message)
    expected_files = _infer_default_structure(message, explicit_files)
    files_of_interest = list(
        dict.fromkeys(expected_files + _find_files_of_interest(message, workspace_files))
    )[:8]
    project_structure = _render_tree(expected_files)

    logger.debug(
        "Plan created: risk=%s files=%s expected=%s",
        risk_level,
        files_of_interest,
        expected_files,
    )

    steps = [
        PlanStep(
            id=str(uuid.uuid4()),
            name="Analyze Request",
            status="completed",
            description="Parsed the prompt and estimated risk, affected files, and likely execution path.",
            details=f"Risk level: {risk_level}. Files of interest: {', '.join(files_of_interest) or 'none'}",
        ),
        PlanStep(
            id=str(uuid.uuid4()),
            name="Draft Structure",
            status="completed",
            description="Generated a lightweight project structure to guide execution.",
            details=project_structure,
        ),
        PlanStep(
            id=str(uuid.uuid4()),
            name="Prepare Execution",
            status="completed",
            description="Prepared strict FILE-block generation, retry validation, and direct writes.",
        ),
    ]

    return Plan(
        summary=f"Plan generated for: {message}",
        risk_level=risk_level,
        files_of_interest=files_of_interest,
        expected_files=expected_files,
        expected_file_count=len(expected_files),
        project_structure=project_structure,
        validation_plan=[
            "strict FILE block parse",
            "planned structure check",
            "expected file count check",
            "per-file syntax validation",
            "project-level import and dependency validation",
            "direct workspace write",
        ],
        steps=steps,
    )
