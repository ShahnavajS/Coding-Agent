"""Code analysis tool — static analysis, symbol extraction, and complexity metrics.

Provides AST-level code intelligence for Python files:
  - Extract all classes, functions, imports from a file
  - Compute cyclomatic complexity
  - Detect common code smells (unused imports, too-long functions, etc.)
  - Find all references to a symbol across the workspace
"""
from __future__ import annotations

import ast
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from assistant_backend.tools.filesystem_tool import workspace_root, safe_resolve

logger = logging.getLogger(__name__)

MAX_FUNCTION_LINES = 50  # threshold for "too long" functions
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB


@dataclass
class SymbolInfo:
    name: str
    kind: str  # "class", "function", "method", "import", "variable"
    line: int
    end_line: int = 0
    parent: str = ""
    docstring: str = ""
    args: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "line": self.line,
            "endLine": self.end_line,
        }
        if self.parent:
            d["parent"] = self.parent
        if self.docstring:
            d["docstring"] = self.docstring[:200]
        if self.args:
            d["args"] = self.args
        if self.decorators:
            d["decorators"] = self.decorators
        return d


@dataclass
class CodeSmell:
    kind: str
    message: str
    line: int
    severity: str = "warning"  # "info", "warning", "error"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message,
                "line": self.line, "severity": self.severity}


def _get_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    names = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(ast.unparse(dec))
        elif isinstance(dec, ast.Call):
            names.append(ast.unparse(dec.func) if hasattr(dec, 'func') else ast.unparse(dec))
    return names


def _get_function_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    return [arg.arg for arg in node.args.args]


def extract_symbols(path: str) -> dict[str, Any]:
    """Parse a Python file and return all top-level and nested symbols.

    Returns
    -------
    dict
        ``{"path": str, "symbols": [...], "imports": [...], "error": str | None}``
    """
    target = safe_resolve(path)
    if not target.exists():
        return {"path": path, "symbols": [], "imports": [], "error": "File not found"}
    if target.suffix != ".py":
        return {"path": path, "symbols": [], "imports": [],
                "error": "Only Python files are supported for symbol extraction"}

    source = target.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return {"path": path, "symbols": [], "imports": [],
                "error": f"SyntaxError: {exc.msg} (line {exc.lineno})"}

    symbols: list[SymbolInfo] = []
    imports: list[dict[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"module": alias.name, "alias": alias.asname or "", "line": node.lineno})
            else:
                module = node.module or ""
                for alias in node.names:
                    imports.append({
                        "module": f"{module}.{alias.name}" if module else alias.name,
                        "alias": alias.asname or "",
                        "line": node.lineno,
                        "from": module,
                    })

        elif isinstance(node, ast.ClassDef):
            symbols.append(SymbolInfo(
                name=node.name,
                kind="class",
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                docstring=ast.get_docstring(node) or "",
                decorators=_get_decorators(node),
            ))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parent = ""
            for potential_parent in ast.walk(tree):
                if isinstance(potential_parent, ast.ClassDef):
                    for child in ast.iter_child_nodes(potential_parent):
                        if child is node:
                            parent = potential_parent.name
                            break
            kind = "method" if parent else "function"
            symbols.append(SymbolInfo(
                name=node.name,
                kind=kind,
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                parent=parent,
                docstring=ast.get_docstring(node) or "",
                args=_get_function_args(node),
                decorators=_get_decorators(node),
            ))

    return {
        "path": path,
        "symbols": [s.to_dict() for s in symbols],
        "imports": imports,
        "error": None,
    }


def _cyclomatic_complexity(node: ast.AST) -> int:
    """Compute McCabe cyclomatic complexity for a function node."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.Assert):
            complexity += 1
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            complexity += 1
    return complexity


def analyze_complexity(path: str) -> dict[str, Any]:
    """Compute per-function complexity metrics for a Python file.

    Returns
    -------
    dict
        ``{"path": str, "functions": [...], "averageComplexity": float, "error": str | None}``
    """
    target = safe_resolve(path)
    if not target.exists():
        return {"path": path, "functions": [], "averageComplexity": 0, "error": "File not found"}
    if target.suffix != ".py":
        return {"path": path, "functions": [], "averageComplexity": 0,
                "error": "Only Python files are supported"}

    source = target.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return {"path": path, "functions": [], "averageComplexity": 0,
                "error": f"SyntaxError: {exc.msg}"}

    functions: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = _cyclomatic_complexity(node)
            line_count = (node.end_lineno or node.lineno) - node.lineno + 1
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "endLine": node.end_lineno or node.lineno,
                "complexity": cc,
                "lineCount": line_count,
                "rating": "low" if cc <= 5 else ("medium" if cc <= 10 else "high"),
            })

    avg = sum(f["complexity"] for f in functions) / max(len(functions), 1)
    return {
        "path": path,
        "functions": functions,
        "averageComplexity": round(avg, 2),
        "error": None,
    }


def detect_code_smells(path: str) -> dict[str, Any]:
    """Run heuristic checks on a Python file to detect common code smells.

    Checks:
      - Functions longer than MAX_FUNCTION_LINES
      - High cyclomatic complexity (> 10)
      - Unused imports (basic heuristic)
      - Missing docstrings on public functions/classes
      - Star imports
    """
    target = safe_resolve(path)
    if not target.exists():
        return {"path": path, "smells": [], "error": "File not found"}
    if target.suffix != ".py":
        return {"path": path, "smells": [], "error": "Only Python files are supported"}

    source = target.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return {"path": path, "smells": [],
                "error": f"SyntaxError: {exc.msg}"}

    smells: list[CodeSmell] = []

    # Collect import names for unused-import check
    imported_names: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imported_names[name] = node.lineno
                if alias.name == "*":
                    smells.append(CodeSmell("star-import",
                                            f"Star import: import {alias.name}",
                                            node.lineno))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    smells.append(CodeSmell("star-import",
                                            f"Star import from {node.module}",
                                            node.lineno))
                else:
                    name = alias.asname or alias.name
                    imported_names[name] = node.lineno

    # Check for unused imports (very basic: scan source text for the name)
    for name, line in imported_names.items():
        # Count occurrences of the name as a whole word
        import re
        count = len(re.findall(rf"\b{re.escape(name)}\b", source))
        if count <= 1:  # Only the import itself
            smells.append(CodeSmell("unused-import",
                                    f"Possibly unused import: '{name}'",
                                    line, severity="info"))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            line_count = (node.end_lineno or node.lineno) - node.lineno + 1

            # Too-long function
            if line_count > MAX_FUNCTION_LINES:
                smells.append(CodeSmell(
                    "long-function",
                    f"Function '{node.name}' is {line_count} lines (threshold: {MAX_FUNCTION_LINES})",
                    node.lineno,
                ))

            # High complexity
            cc = _cyclomatic_complexity(node)
            if cc > 10:
                smells.append(CodeSmell(
                    "high-complexity",
                    f"Function '{node.name}' has complexity {cc} (threshold: 10)",
                    node.lineno,
                ))

            # Missing docstring on public function
            if not node.name.startswith("_") and not ast.get_docstring(node):
                smells.append(CodeSmell(
                    "missing-docstring",
                    f"Public function '{node.name}' has no docstring",
                    node.lineno,
                    severity="info",
                ))

        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_") and not ast.get_docstring(node):
                smells.append(CodeSmell(
                    "missing-docstring",
                    f"Public class '{node.name}' has no docstring",
                    node.lineno,
                    severity="info",
                ))

    return {
        "path": path,
        "smells": [s.to_dict() for s in smells],
        "error": None,
    }


def find_symbol_references(symbol_name: str, include_globs: list[str] | None = None) -> dict[str, Any]:
    """Find all references to a symbol name across Python files in the workspace.

    This is a text-based search scoped to `*.py` files (or custom globs).
    """
    from assistant_backend.tools.grep_tool import grep_workspace
    globs = include_globs or ["*.py"]
    return grep_workspace(
        rf"\b{symbol_name}\b",
        is_regex=True,
        include_globs=globs,
        context_lines=1,
    )
