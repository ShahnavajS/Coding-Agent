from __future__ import annotations

import ast
import json
import re
from typing import Iterable

from assistant_backend.core.models import Plan

_NODE_PACKAGES = {
    "react",
    "react-dom",
    "typescript",
    "vite",
    "webpack",
    "webpack-cli",
    "webpack-dev-server",
    "html-webpack-plugin",
    "css-loader",
    "style-loader",
    "@vitejs/plugin-react",
}
_NODE_STDLIB_PACKAGES = {
    "buffer",
    "crypto",
    "events",
    "fs",
    "os",
    "path",
    "process",
    "stream",
    "url",
    "util",
}
_PYTHON_STDLIB_PACKAGES = {
    "sqlite3",
    "json",
    "os",
    "sys",
    "pathlib",
    "typing",
    "re",
}
_PYTHON_IMPORT_TO_PACKAGE = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "jose": "python-jose",
    "passlib": "passlib",
    "bcrypt": "bcrypt",
    "requests": "requests",
    "dotenv": "python-dotenv",
}
_FRONTEND_RUNTIME_IMPORTS = {
    "axios",
    "react",
    "react-dom",
    "react-router-dom",
}


def _issue(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def _package_name(requirement: str) -> str:
    return re.split(r"[<>=!~\[]", requirement.strip(), maxsplit=1)[0].strip().lower()


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts[:3])


def _iter_requirements(content: str) -> list[str]:
    requirements: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirements.append(line)
    return requirements


def _validate_requirements(
    content: str,
    backend_imports: set[str],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    requirements = _iter_requirements(content)
    packages = {_package_name(line) for line in requirements}

    for line in requirements:
        name = _package_name(line)
        if name in _PYTHON_STDLIB_PACKAGES:
            issues.append(_issue("requirements.txt", f"remove stdlib package '{name}'"))
        if name in _NODE_PACKAGES:
            issues.append(
                _issue(
                    "requirements.txt",
                    f"move Node package '{name}' to frontend/package.json",
                )
            )
        if name == "fastapi" and "==" in line and _version_tuple(line) < (0, 100, 0):
            issues.append(
                _issue(
                    "requirements.txt",
                    "FastAPI version is too old for a modern production scaffold",
                )
            )
        if name == "uvicorn" and "==" in line and _version_tuple(line) < (0, 23, 0):
            issues.append(
                _issue(
                    "requirements.txt",
                    "Uvicorn version is too old for the generated project",
                )
            )
        if name == "sqlalchemy" and "==" in line and _version_tuple(line) < (1, 4, 0):
            issues.append(
                _issue(
                    "requirements.txt",
                    "SQLAlchemy version is too old for the generated project",
                )
            )

    for module, package in _PYTHON_IMPORT_TO_PACKAGE.items():
        if module in backend_imports and package not in packages:
            issues.append(
                _issue(
                    "requirements.txt",
                    f"missing package '{package}' required by backend imports",
                )
            )

    return issues


def _load_package_json(content: str) -> tuple[dict[str, object] | None, list[dict[str, str]]]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return None, [
            _issue(
                "frontend/package.json",
                f"invalid JSON ({exc.msg} at line {exc.lineno})",
            )
        ]
    return data, []


def _extract_package_name(import_target: str) -> str:
    if import_target.startswith("@"):
        parts = import_target.split("/")
        return "/".join(parts[:2])
    return import_target.split("/")[0]


def _collect_frontend_imports(path_to_content: dict[str, str]) -> dict[str, set[str]]:
    runtime_imports: set[str] = set()
    dev_imports: set[str] = set()
    import_re = re.compile(
        r"""^\s*import(?:[\s\w{},*]+from\s+)?["']([^"']+)["']""",
        re.MULTILINE,
    )

    for path, content in path_to_content.items():
        if not path.startswith("frontend/"):
            continue
        for source in import_re.findall(content):
            if source.startswith(".") or source.startswith("/"):
                continue
            package = _extract_package_name(source)
            if package in _NODE_STDLIB_PACKAGES:
                continue
            if path.endswith("vite.config.ts") or path.endswith("vite.config.js"):
                dev_imports.add(package)
            elif path.endswith((".ts", ".tsx", ".js", ".jsx")):
                runtime_imports.add(package)

    return {
        "runtime": runtime_imports,
        "dev": dev_imports,
    }


def _validate_package_json(
    data: dict[str, object],
    frontend_imports: dict[str, set[str]],
    path_to_content: dict[str, str],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    dependencies = data.get("dependencies", {})
    dev_dependencies = data.get("devDependencies", {})
    scripts = data.get("scripts", {})

    if not isinstance(dependencies, dict):
        issues.append(_issue("frontend/package.json", "dependencies must be an object"))
        dependencies = {}
    if not isinstance(dev_dependencies, dict):
        issues.append(_issue("frontend/package.json", "devDependencies must be an object"))
        dev_dependencies = {}
    if not isinstance(scripts, dict):
        issues.append(_issue("frontend/package.json", "scripts must be an object"))
        scripts = {}

    if "react" not in dependencies:
        issues.append(_issue("frontend/package.json", "missing dependency 'react'"))
    if "react-dom" not in dependencies:
        issues.append(_issue("frontend/package.json", "missing dependency 'react-dom'"))
    if "vite" not in dev_dependencies:
        issues.append(_issue("frontend/package.json", "missing devDependency 'vite'"))
    if "typescript" not in dev_dependencies:
        issues.append(_issue("frontend/package.json", "missing devDependency 'typescript'"))
    if "@vitejs/plugin-react" not in dev_dependencies:
        issues.append(
            _issue("frontend/package.json", "missing devDependency '@vitejs/plugin-react'")
        )
    if any(path.endswith((".ts", ".tsx")) for path in path_to_content):
        if "@types/react" not in dev_dependencies:
            issues.append(
                _issue("frontend/package.json", "missing devDependency '@types/react'")
            )
        if "@types/react-dom" not in dev_dependencies:
            issues.append(
                _issue("frontend/package.json", "missing devDependency '@types/react-dom'")
            )
    for script_name in ("dev", "build"):
        if script_name not in scripts:
            issues.append(
                _issue("frontend/package.json", f"missing script '{script_name}'")
            )

    declared_runtime = set(dependencies.keys())
    declared_dev = set(dev_dependencies.keys())
    for package in frontend_imports["runtime"]:
        if package in _FRONTEND_RUNTIME_IMPORTS and package not in declared_runtime:
            issues.append(
                _issue(
                    "frontend/package.json",
                    f"missing dependency '{package}' required by frontend imports",
                )
            )
    for package in frontend_imports["dev"]:
        if package in {"vite", "@vitejs/plugin-react", "typescript"}:
            continue
        if package not in declared_dev and package not in declared_runtime:
            issues.append(
                _issue(
                    "frontend/package.json",
                    f"missing devDependency '{package}' required by config imports",
                )
            )

    if "frontend/vite.config.ts" in path_to_content and "frontend/webpack.config.js" in path_to_content:
        issues.append(
            _issue(
                "frontend/package.json",
                "do not mix Vite and webpack configs in the same generated frontend scaffold",
            )
        )

    script_text = " ".join(str(value) for value in scripts.values())
    if "vite" in script_text and "frontend/webpack.config.js" in path_to_content:
        issues.append(
            _issue(
                "frontend/package.json",
                "scripts use Vite but webpack.config.js is also present",
            )
        )
    if "webpack" in script_text and "frontend/vite.config.ts" in path_to_content:
        issues.append(
            _issue(
                "frontend/package.json",
                "scripts use webpack but vite.config.ts is also present",
            )
        )

    return issues


def _validate_main_tsx(content: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if "ReactDOM.render(" in content:
        issues.append(
            _issue("frontend/src/main.tsx", "use createRoot() for React 18 projects")
        )
    if 'import ReactDOM from "react-dom/client"' in content or "import ReactDOM from 'react-dom/client'" in content:
        issues.append(
            _issue(
                "frontend/src/main.tsx",
                "avoid default ReactDOM import from react-dom/client; import createRoot instead",
            )
        )
    return issues


def _collect_backend_imports(path_to_content: dict[str, str]) -> set[str]:
    imports: set[str] = set()
    for path, content in path_to_content.items():
        if not path.endswith(".py"):
            continue
        try:
            module = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    return imports


def _module_to_path(module: str) -> str:
    return module.replace(".", "/") + ".py"


def _symbol_exists_in_python_file(content: str, symbol: str) -> bool:
    try:
        module = ast.parse(content)
    except SyntaxError:
        return True
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol:
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_name = alias.asname or alias.name.split(".")[0]
                if imported_name == symbol:
                    return True
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol:
                    return True
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == symbol:
                return True
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname == symbol or alias.name == symbol:
                    return True
    return False


def _validate_python_imports(path_to_content: dict[str, str]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for path, content in path_to_content.items():
        if not path.endswith(".py"):
            continue
        try:
            module = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(module):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.module == "fastapi.requests":
                issues.append(
                    _issue(path, "import Request from 'fastapi', not 'fastapi.requests'")
                )
            if node.module == "fastapi.responses" and any(alias.name == "Request" for alias in node.names):
                issues.append(
                    _issue(path, "Request is not available from fastapi.responses; import it from fastapi")
                )
            if node.module == "pydantic" and any(alias.name == "BaseSettings" for alias in node.names):
                issues.append(
                    _issue(path, "use BaseSettings from pydantic_settings, not from pydantic")
                )

            target_path = _module_to_path(node.module)
            if target_path not in path_to_content:
                continue
            target_content = path_to_content[target_path]
            for alias in node.names:
                if alias.name == "*":
                    continue
                if not _symbol_exists_in_python_file(target_content, alias.name):
                    issues.append(
                        _issue(
                            path,
                            f"imported symbol '{alias.name}' is not defined in {target_path}",
                        )
                    )
    return issues


def validate_project_files(
    plan: Plan,
    files: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    path_to_content = {item["path"]: item["content"] for item in files}
    issues: list[dict[str, str]] = []

    backend_imports = _collect_backend_imports(path_to_content)
    requirements = path_to_content.get("requirements.txt")
    if requirements:
        issues.extend(_validate_requirements(requirements, backend_imports))

    if any(path.startswith("frontend/") for path in plan.expected_files):
        frontend_imports = _collect_frontend_imports(path_to_content)

        package_json = path_to_content.get("frontend/package.json")
        if package_json:
            data, load_issues = _load_package_json(package_json)
            issues.extend(load_issues)
            if data is not None:
                issues.extend(_validate_package_json(data, frontend_imports, path_to_content))

        main_tsx = path_to_content.get("frontend/src/main.tsx", "")
        if main_tsx:
            issues.extend(_validate_main_tsx(main_tsx))

        index_html = path_to_content.get("frontend/index.html", "")
        if index_html and 'id="root"' not in index_html and "id='root'" not in index_html:
            issues.append(_issue("frontend/index.html", "missing root mount element"))

    issues.extend(_validate_python_imports(path_to_content))

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (issue["path"], issue["message"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped
