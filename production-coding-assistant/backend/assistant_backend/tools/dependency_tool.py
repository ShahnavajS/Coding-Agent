"""Dependency analysis tool — map module imports and inter-file relationships.

Analyses the workspace to build a dependency graph showing
which files import which modules, helping the agent understand
the project structure before making changes.
"""
from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any

from assistant_backend.tools.filesystem_tool import workspace_root, safe_resolve

logger = logging.getLogger(__name__)

_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "out", ".assistant",
})


def _collect_python_files(root: Path) -> list[Path]:
    """Walk the workspace and collect all .py files (excluding skip dirs)."""
    py_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            if f.endswith(".py"):
                py_files.append(Path(dirpath) / f)
    return py_files


def _extract_imports(source: str) -> list[dict[str, Any]]:
    """Parse a Python source string and extract import statements."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "type": "import",
                    "module": alias.name,
                    "alias": alias.asname or "",
                    "line": node.lineno,
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level  # relative import depth
            for alias in node.names:
                imports.append({
                    "type": "from",
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname or "",
                    "line": node.lineno,
                    "level": level,
                })
    return imports


def analyze_dependencies(path: str | None = None) -> dict[str, Any]:
    """Analyse import dependencies for a single file or the entire workspace.

    When *path* is given, returns imports for that file.
    When *path* is None, builds a workspace-wide dependency graph.

    Returns
    -------
    dict
        ``{"files": {rel_path: {"imports": [...], "importedBy": [...]}}, "error": ...}``
    """
    root = workspace_root()

    if path:
        target = safe_resolve(path)
        if not target.exists():
            return {"files": {}, "error": f"File not found: {path}"}
        if target.suffix != ".py":
            return {"files": {}, "error": "Only Python files are supported"}
        source = target.read_text(encoding="utf-8", errors="replace")
        rel = str(target.relative_to(root)).replace("\\", "/")
        return {
            "files": {rel: {"imports": _extract_imports(source), "importedBy": []}},
            "error": None,
        }

    # Build workspace-wide graph
    py_files = _collect_python_files(root)
    graph: dict[str, dict[str, Any]] = {}

    for pf in py_files:
        rel = str(pf.relative_to(root)).replace("\\", "/")
        try:
            source = pf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        graph[rel] = {
            "imports": _extract_imports(source),
            "importedBy": [],
        }

    # Build reverse edges (importedBy)
    module_to_file: dict[str, str] = {}
    for rel_path in graph:
        # Convert file path to a module-like name: "src/utils.py" -> "src.utils"
        mod = rel_path.replace("/", ".").removesuffix(".py")
        if mod.endswith(".__init__"):
            mod = mod.removesuffix(".__init__")
        module_to_file[mod] = rel_path

    for rel_path, info in graph.items():
        for imp in info["imports"]:
            module_name = imp.get("module", "")
            if module_name in module_to_file:
                target_file = module_to_file[module_name]
                if rel_path not in graph[target_file]["importedBy"]:
                    graph[target_file]["importedBy"].append(rel_path)

    logger.info("Dependency analysis: %d files scanned", len(graph))
    return {"files": graph, "error": None}


def get_project_structure() -> dict[str, Any]:
    """Return a tree-view summary of the workspace for the agent's context.

    Returns
    -------
    dict
        ``{"tree": str, "stats": {"totalFiles": int, "byExtension": {...}}}``
    """
    root = workspace_root()
    lines: list[str] = []
    stats: dict[str, int] = {}
    total = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
        level = len(Path(dirpath).relative_to(root).parts)
        indent = "  " * level
        dirname = Path(dirpath).name
        if level > 0:
            lines.append(f"{indent}{dirname}/")

        for f in sorted(filenames):
            total += 1
            ext = Path(f).suffix or "(no ext)"
            stats[ext] = stats.get(ext, 0) + 1
            lines.append(f"{indent}  {f}")

    tree_str = "\n".join(lines) if lines else "(empty workspace)"
    return {
        "tree": tree_str,
        "stats": {"totalFiles": total, "byExtension": stats},
    }
