from __future__ import annotations

from typing import Any, Callable

from assistant_backend.tools.web_search import web_search

ToolFn = Callable[..., Any]

TOOLS: dict[str, ToolFn] = {
    "web_search": web_search,
}


def run_tool(name: str, **kwargs: Any) -> Any:
    try:
        tool = TOOLS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown tool: {name}") from exc
    return tool(**kwargs)
