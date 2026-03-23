from __future__ import annotations

import ast
import json
from typing import Any

from assistant_backend.tools.filesystem_tool import read_text_file, safe_resolve
from assistant_backend.tools.structured_editor import preview_file_update
from assistant_backend.validation.parser_checks import detect_language


def update_python_assignment(
    path: str,
    variable_name: str,
    expression: str,
) -> dict[str, Any]:
    target = safe_resolve(path)
    source = read_text_file(path) if target.exists() else ""
    tree = ast.parse(source or "\n")
    replacement = ast.parse(expression, mode="eval").body
    updated = False

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == variable_name:
                    node.value = replacement
                    updated = True
                    break

    if not updated:
        tree.body.append(
            ast.Assign(
                targets=[ast.Name(id=variable_name, ctx=ast.Store())],
                value=replacement,
            )
        )

    ast.fix_missing_locations(tree)
    updated_source = ast.unparse(tree) + "\n"
    return preview_file_update(path, updated_source)


def merge_json_object(path: str, patch: dict[str, Any]) -> dict[str, Any]:
    target = safe_resolve(path)
    source = read_text_file(path) if target.exists() else ""
    current = json.loads(source) if source.strip() else {}
    if not isinstance(current, dict):
        raise ValueError("JSON merge is only supported for top-level objects")
    current.update(patch)
    return preview_file_update(path, json.dumps(current, indent=2) + "\n")


def structured_update(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    language = detect_language(path)
    if language == "python":
        variable_name = str(payload.get("variableName", "")).strip()
        expression = str(payload.get("expression", "")).strip()
        if not variable_name or not expression:
            raise ValueError("Python structured update requires variableName and expression")
        return update_python_assignment(path, variable_name, expression)
    if language == "json":
        patch = payload.get("patch")
        if not isinstance(patch, dict):
            raise ValueError("JSON structured update requires an object patch")
        return merge_json_object(path, patch)
    raise ValueError(f"Structured updates are not configured for {language}")
