from __future__ import annotations

import json
import logging
import re
from typing import Any

from assistant_backend.config import get_cached_settings
from assistant_backend.core.context_builder import build_context_snapshot
from assistant_backend.core.edit_agent import (
    _is_edit_request,  # noqa: PLC2701 — shared detection helper
    run_edit_mode,
)
from assistant_backend.core.executor import (
    normalize_generation_output,
    repair_generation_output,
    should_execute,
    validate_generation_output,
    write_generated_files,
)
from assistant_backend.core.models import AgentMode, ContextSnapshot, Plan, PlanStep, StepStatus
from assistant_backend.core.plan_agent import run_plan_agent
from assistant_backend.core.planner import create_plan
from assistant_backend.core.reviewer import review_generation
from assistant_backend.providers.router import generate as generate_with_provider
from assistant_backend.storage.database import append_message, get_messages
from assistant_backend.tools import run_tool
from assistant_backend.tools.filesystem_tool import list_files_flat
from assistant_backend.validation.sandbox_validator import validate_files_in_docker_sandbox

logger = logging.getLogger(__name__)
_MAX_TOOL_ITERATIONS = 3
_AUTO_SEARCH_HINTS = (
    "latest",
    "current",
    "research",
    "official",
    "recent",
    "today",
    "news",
    "breaking",
    "2025",
    "2026",
)
# Number of recent messages to inject into agent prompts for conversational continuity
_HISTORY_IN_PROMPT = 6
_QUESTION_PREFIXES = (
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "which",
    "is",
    "are",
    "can",
    "could",
    "should",
    "do",
    "does",
    "did",
    "tell me",
    "explain",
    "summarize",
)
_FOLLOW_UP_MESSAGES = {
    "again",
    "retry",
    "try again",
    "continue",
    "go on",
    "ok",
    "okay",
    "yes",
    "sure",
    "please do",
    "do it",
    "do that",
    "fix it",
    "make it work",
}
_WEB_SEARCH_CONFIG_HINTS = (
    "missing brave_search_api_key",
    "missing serpapi_api_key",
    "missing bing_search_api_key",
    "web search is not configured",
    "web search is disabled",
)


def _summarize_accepted_files(accepted_files: list[str] | None) -> str:
    if not accepted_files:
        return ""
    preview = accepted_files[:8]
    remainder = len(accepted_files) - len(preview)
    lines = [
        f"Files already accepted and do not need regeneration ({len(accepted_files)} total):"
    ]
    lines.extend(f"- {path}" for path in preview)
    if remainder > 0:
        lines.append(f"- ... and {remainder} more accepted files")
    return "\n".join(lines) + "\n\n"


def _build_stack_guidance(plan: Plan) -> str:
    expected = set(plan.expected_files)
    if {"backend/app/main.py", "frontend/src/main.tsx", "frontend/package.json"}.issubset(expected):
        return (
            "Stack guidance for this project:\n"
            "- Use FastAPI + SQLAlchemy + Pydantic Settings on the backend.\n"
            "- Use React 18 + TypeScript + Vite on the frontend.\n"
            "- requirements.txt should use modern compatible versions, for example:\n"
            "  fastapi>=0.110,<1\n"
            "  uvicorn>=0.29,<1\n"
            "  sqlalchemy>=2.0,<3\n"
            "  pydantic>=2.6,<3\n"
            "  pydantic-settings>=2.2,<3\n"
            "- If auth uses jose, include python-jose[cryptography].\n"
            "- frontend/package.json must include scripts for dev and build using vite.\n"
            "- frontend/package.json devDependencies must include vite, @vitejs/plugin-react, typescript, @types/react, and @types/react-dom.\n"
            "- frontend/src/main.tsx should import createRoot from react-dom/client and mount App to #root.\n"
            "- backend/app/config.py should import BaseSettings from pydantic_settings, never from pydantic.\n"
            "- Keep backend/app/routes.py imports consistent with backend/app/schemas.py. If routes imports TodoCreateSchema and TodoUpdateSchema, define those exact classes in schemas.py.\n"
            "- Reuse exact class names across models, schemas, services, and routes. Do not invent alternate schema names in only one file.\n"
            "- Do not omit frontend/src/main.tsx.\n\n"
            "Reference pattern for frontend/src/main.tsx:\n"
            "import { createRoot } from \"react-dom/client\";\n"
            "import App from \"./App\";\n"
            "import \"./styles.css\";\n\n"
            "createRoot(document.getElementById(\"root\")!).render(<App />);\n\n"
        )
    if {
        "README.md",
        "requirements.txt",
        "app.py",
        "fastapi_example.py",
        "flask_example.py",
        "comparison.py",
    }.issubset(expected):
        return (
            "Stack guidance for this project:\n"
            "- This is a Python CLI comparison project, not a backend service scaffold.\n"
            "- Keep exactly the requested files unless the user explicitly asks for more.\n"
            "- requirements.txt should use modern compatible versions, for example:\n"
            "  fastapi>=0.110,<1\n"
            "  flask>=3.0,<4\n"
            "  uvicorn>=0.29,<1\n"
            "- app.py should serve as the CLI or entry point for the comparison project.\n"
            "- fastapi_example.py should show current FastAPI patterns.\n"
            "- flask_example.py should show current Flask patterns.\n"
            "- comparison.py should compare the approaches in plain Python code.\n"
            "- Keep the examples lightweight. Do not add env/settings/config layers unless the user explicitly asks for them.\n"
            "- Do not import pydantic_settings, SQLAlchemy, auth helpers, or database tooling unless the requested files actually need them.\n"
            "- Keep function names consistent across app.py and comparison.py. If app.py imports a helper from comparison.py, define that exact function in comparison.py.\n"
            "- README.md must include a short 'Sources Used' section with the researched links.\n\n"
        )
    if {
        "README.md",
        "ARCHITECTURE.md",
        "requirements.txt",
        "app/main.py",
        "app/services/rate_limiter.py",
        "app/services/retry_policy.py",
    }.issubset(expected):
        return (
            "Stack guidance for this project:\n"
            "- This is a service/system architecture request, not a tiny CLI scaffold.\n"
            "- Prefer a modular Python service layout with clear separation between config, routes, services, retry logic, and observability.\n"
            "- If the request mentions chat, prefer FastAPI with WebSocket support for the service entrypoint.\n"
            "- requirements.txt should use modern compatible versions, for example:\n"
            "  fastapi>=0.110,<1\n"
            "  uvicorn>=0.29,<1\n"
            "  pydantic>=2.6,<3\n"
            "  pydantic-settings>=2.2,<3\n"
            "  redis>=5,<6\n"
            "- CRITICAL: Create package __init__.py files and properly re-export symbols:\n"
            "  * app/__init__.py must re-export public symbols from subpackages\n"
            "  * app/services/__init__.py MUST export rate_limiter, retry_policy, RateLimiter, RetryPolicy\n"
            "  * Example: from app.services.rate_limiter import rate_limiter, RateLimiter\n"
            "  * When main.py imports 'from app.services import rate_limiter', the __init__.py MUST make it available\n"
            "- app/services/rate_limiter.py should contain: class RateLimiter + module-level instance 'rate_limiter = RateLimiter(...)'\n"
            "- app/services/retry_policy.py should contain: class RetryPolicy + module-level instance 'retry_policy = RetryPolicy(...)'\n"
            "- app/observability.py should contain structured logging and monitoring hooks.\n"
            "- Put bottlenecks, scaling strategy, and operational tradeoffs in ARCHITECTURE.md.\n"
            "- Keep imports and exported helper names consistent across routes and services.\n"
            "- All generated Python symbols must be defined at module level or explicitly imported, not computed dynamically.\n\n"
        )
    return ""


def _build_repair_guidance(retry_errors: list[str] | None) -> str:
    if not retry_errors:
        return ""

    guidance: list[str] = []
    joined = "\n".join(retry_errors)
    required_exports: dict[str, set[str]] = {}
    if "import Request from 'fastapi', not 'fastapi.requests'" in joined:
        guidance.append("- Import Request from fastapi, never from fastapi.requests.")
    if "use BaseSettings from pydantic_settings, not from pydantic" in joined:
        guidance.append("- If you use BaseSettings, import it from pydantic_settings and keep requirements.txt aligned.")
    if "imported symbol" in joined:
        guidance.append("- Every symbol imported in one file MUST be defined at module level in the target file.")
        guidance.append("- Use explicit module-level definitions: 'rate_limiter = RateLimiter(...)', 'my_var = value'.")
        guidance.append("- For packages (directories with __init__.py), the __init__.py MUST re-export all symbols imported from submodules.")
        guidance.append("- Example: app/services/__init__.py must contain 'from app.services.rate_limiter import rate_limiter'")
        guidance.append("- When regenerating, regenerate both the module file AND its __init__.py in the same attempt.")

    import_symbol_re = re.compile(
        r"(?P<importer>[^:\n]+): imported symbol '(?P<symbol>[^']+)' is not defined in (?P<target>[^\n]+)"
    )
    for match in import_symbol_re.finditer(joined):
        importer = match.group("importer")
        symbol = match.group("symbol")
        target = match.group("target")
        required_exports.setdefault(target, set()).add(symbol)
        
        # Enhanced guidance for __init__.py files
        if target.endswith("__init__.py"):
            guidance.append(
                f"- {target}: import and re-export '{symbol}' (imported by {importer}). "
                f"Example: from {target.replace('/__init__.py', '').replace('/', '.')}.{symbol.split('_')[0]}_module import {symbol}"
            )
        else:
            guidance.append(
                f"- Ensure {target} defines {symbol} at module level (imported by {importer}). "
                f"Example: {symbol} = SomeClass(...) or def {symbol}(): ..."
            )

    contract_lines: list[str] = []
    for target, symbols in sorted(required_exports.items()):
        contract_lines.append(
            f"- {target} must export: {', '.join(sorted(symbols))}"
        )

    if not guidance and not contract_lines:
        return ""
    deduped = list(dict.fromkeys(guidance))
    sections: list[str] = []
    if deduped:
        sections.append("Repair guidance:\n" + "\n".join(deduped))
    if contract_lines:
        sections.append("Required export contracts for this retry:\n" + "\n".join(contract_lines))
    return "\n".join(sections) + "\n"


def build_agent_prompt(
    message: str,
    context: dict[str, Any],
    plan: Plan,
    remaining_files: list[str],
    accepted_files: list[str] | None = None,
    require_structure: bool = True,
    retry_errors: list[str] | None = None,
    attempt: int = 1,
    research_context: str = "",
    context_snapshot: ContextSnapshot | None = None,
) -> str:
    active_file = context.get("activeFilePath") or "none"
    selected_text = context.get("selectedText") or ""
    accepted_section = _summarize_accepted_files(accepted_files)
    retry_section = ""
    if retry_errors:
        retry_action = (
            "Include the project structure block first, then regenerate only the files listed under "
            "'Files to generate in this response'."
            if require_structure
            else "Regenerate only the files listed under 'Files to generate in this response'. "
            "Do not repeat already accepted files or the structure tree."
        )
        retry_section = (
            f"\nPrevious output was rejected. Fix every issue below. {retry_action}\n"
            + "\n".join(f"- {error}" for error in retry_errors)
            + "\n"
        )
        retry_section += _build_repair_guidance(retry_errors)

    expected_files = (
        "\n".join(f"- {path}" for path in remaining_files)
        if remaining_files
        else "- Generate a sensible multi-file structure"
    )
    stack_guidance = _build_stack_guidance(plan)
    structure_section = (
        "Planned project structure:\n"
        f"{plan.project_structure}\n\n"
        if require_structure
        else "The project structure has already been accepted. Do not repeat it.\n\n"
    )
    research_section = ""
    if research_context:
        research_section = (
            "Web search context already collected for this request:\n"
            f"{research_context}\n\n"
        )

    # --- Context snapshot (codebase awareness + conversation history) ----------
    context_section = ""
    if context_snapshot:
        block = context_snapshot.to_prompt_block()
        if block:
            context_section = f"Codebase context and conversation history:\n{block}\n\n"

    # --- File snippets from the planner (existing workspace files) ------------
    snippet_section = ""
    if plan.file_snippets:
        lines = ["Existing workspace files (for reference — do not regenerate unless listed below):"]
        for path, content in list(plan.file_snippets.items())[:4]:
            lines.append(f"\n--- {path} ---")
            lines.append(content[:1000])
        snippet_section = "\n".join(lines) + "\n\n"

    return (
        "You are the code-generation layer of a production-grade AI coding assistant.\n"
        "You must generate all requested files in one response.\n"
        + (
            "Start by outputting the project structure as a plain tree.\n"
            if require_structure
            else "The project structure has already been accepted. Output only the remaining FILE blocks.\n"
        )
        + "Then output the files using this exact format:\n"
        "FILE: relative/path.ext\n"
        "<full file content>\n"
        "FILE: another/path.ext\n"
        "<full file content>\n\n"
        "Strict rules:\n"
        "- No explanations outside the structure tree and FILE blocks.\n"
        "- No markdown fences.\n"
        "- No UI simulation.\n"
        "- No placeholder implementations, TODOs, or unfinished sections.\n"
        "- Do not stop until ALL files are generated.\n"
        "- Verify all files are generated before finishing.\n"
        "- Output each planned file exactly once.\n"
        "- Keep Python and Node dependencies in separate manifests.\n"
        "- Never place stdlib modules like sqlite3 in requirements.txt.\n"
        "- Do not guess ancient exact versions. Prefer modern compatible versions or conservative version ranges.\n"
        "- Keep one build tool choice per project. Do not mix Vite and webpack unless the user explicitly asked for both.\n"
        "- For React, use React 18 createRoot() patterns.\n"
        "- Prefer Vite for React + TypeScript projects unless the user asked for another bundler.\n"
        "- Include all required config files for the chosen stack.\n"
        "- If you import Request in FastAPI, import it from fastapi.\n"
        "- JSONResponse may be imported from fastapi.responses.\n"
        "- If you use BaseSettings, import it from pydantic_settings and include pydantic-settings in requirements.txt.\n"
        "- If frontend code imports axios or react-router-dom, include them in frontend/package.json.\n"
        "- Do not add Node built-ins like path or fs to frontend/package.json.\n"
        "- If the user asks for explanations, bottlenecks, or scaling notes, put them in README.md or ARCHITECTURE.md inside FILE blocks.\n"
        "- If you need current or external information, respond with JSON only using this exact tool shape:\n"
        '  {"tool":"web_search","query":"your search query","num_results":5}\n'
        "- Do not mix tool JSON with FILE blocks or explanations.\n"
        "- After web search results are provided, continue with the requested FILE output.\n"
        "- Output raw executable source code only.\n\n"
        f"{stack_guidance}"
        f"{research_section}"
        f"{context_section}"
        f"{snippet_section}"
        f"User request:\n{message}\n\n"
        f"Active file: {active_file}\n"
        f"Files of interest: {', '.join(plan.files_of_interest) or 'none'}\n"
        f"Expected file count: {len(remaining_files) or plan.expected_file_count or 2}\n"
        f"{structure_section}"
        "Files to generate in this response:\n"
        f"{expected_files}\n\n"
        f"{accepted_section}"
        f"Selected text:\n{selected_text[:1200]}"
        f"{retry_section}"
        f"\nAttempt: {attempt}/3\n"
    )


def build_ask_prompt(message: str, context: dict[str, Any]) -> str:
    active_file = context.get("activeFilePath") or "none"
    selected_text = context.get("selectedText") or ""
    selected_block = (
        f"\n\nSelected text:\n```\n{selected_text[:800]}\n```" if selected_text else ""
    )
    return (
        "You are a helpful AI coding assistant. Answer the user's question clearly and concisely.\n"
        "You may reference code concepts, patterns, and best practices.\n"
        "Do NOT generate full file implementations unless explicitly asked.\n\n"
        f"User question:\n{message}\n\n"
        f"Active file: {active_file}"
        f"{selected_block}"
    )


def _build_ask_prompt_with_context(
    message: str,
    context: dict[str, Any],
    context_snapshot: ContextSnapshot | None = None,
    research_context: str = "",
) -> str:
    base_prompt = build_ask_prompt(message, context)
    parts = [base_prompt]
    if context_snapshot:
        context_block = context_snapshot.to_prompt_block()
        if context_block:
            parts.append(f"Codebase context and conversation history:\n{context_block}")
    if research_context:
        parts.append(f"Web search context:\n{research_context}")
    parts.append(
        "Rules:\n"
        "- Answer the user's question directly.\n"
        "- Use the conversation history and workspace context below when they are available.\n"
        "- Do not claim there is no project context if the prompt includes prior chat history or file context.\n"
        "- Do not generate project files, FILE blocks, or new scaffolds unless the user explicitly asks you to build or modify code.\n"
        "- If you need external information, respond with JSON only using this exact shape:\n"
        '  {"tool":"web_search","query":"your query","num_results":5}\n'
        "- After search context is provided, answer the question normally.\n"
    )
    return "\n\n".join(parts)


def _validate_tool_payload(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    tool_name = str(payload.get("tool", "")).strip()
    if tool_name != "web_search":
        return None, f"Unknown tool requested: {tool_name or 'none'}"

    query = str(payload.get("query", "")).strip()
    if not query:
        return None, "web_search tool call must include a non-empty query."

    max_results = get_cached_settings().web_search.max_results
    raw_num = payload.get("num_results", payload.get("num", max_results))
    try:
        num_results = max(1, min(int(raw_num), max_results))
    except (TypeError, ValueError):
        return None, "web_search tool call must include a numeric num_results value."

    return {
        "tool": "web_search",
        "query": query,
        "num_results": num_results,
    }, None


def _parse_tool_call(response_text: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = response_text.strip()
    if not stripped or '"tool"' not in stripped:
        return None, None

    decoder = json.JSONDecoder()
    saw_tool_payload = False
    first_error: str | None = None

    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or "tool" not in payload:
            continue
        saw_tool_payload = True
        tool_call, tool_error = _validate_tool_payload(payload)
        if tool_error and first_error is None:
            first_error = tool_error
            continue
        if tool_call is not None:
            return tool_call, None

    if saw_tool_payload:
        return None, first_error or "Tool call JSON is invalid."
    return None, None


def _is_web_search_setup_error(exc: Exception | str) -> bool:
    lowered = str(exc).lower()
    return any(token in lowered for token in _WEB_SEARCH_CONFIG_HINTS)


def _build_web_search_unavailable_message(reason: str) -> str:
    return (
        "I need live web search to answer that current-information request, but web search is not configured right now.\n\n"
        f"Reason: {reason}\n\n"
        "Add one of these in your app settings or .env and try again:\n"
        "- BRAVE_SEARCH_API_KEY\n"
        "- SERPAPI_API_KEY\n"
        "- BING_SEARCH_API_KEY"
    )


def _format_search_results_for_prompt(query: str, results: list[dict[str, str]]) -> str:
    lines = [f"Search query: {query}"]
    for index, item in enumerate(results[:6], start=1):
        title = item.get("title", "").strip() or "(untitled)"
        source = item.get("source", "").strip() or "unknown source"
        snippet = item.get("snippet", "").strip() or "No snippet."
        lines.append(f"{index}. {title} ({source}) - {snippet}")
        link = item.get("link", "").strip()
        if link:
            lines.append(f"   Link: {link}")
    return "\n".join(lines)


def _should_auto_search(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in _AUTO_SEARCH_HINTS)


def _build_auto_search_queries(message: str, plan: Plan) -> list[str]:
    lowered = message.lower()
    queries: list[str] = []
    if "fastapi" in lowered and "flask" in lowered:
        queries.append("latest FastAPI and Flask best practices official docs 2026")
    elif "fastapi" in lowered and "react" in lowered:
        queries.append("latest FastAPI React Vite TypeScript setup official docs 2026")
        queries.append("latest pydantic settings best practices official docs 2026")
    elif "fastapi" in lowered:
        queries.append("latest FastAPI best practices official docs 2026")
    elif "react" in lowered and "vite" in lowered:
        queries.append("latest React 18 Vite TypeScript setup official docs 2026")

    if not queries:
        trimmed = " ".join(message.strip().split())
        queries.append(trimmed[:140])

    deduped: list[str] = []
    for query in queries:
        query = query.strip()
        if query and query not in deduped:
            deduped.append(query)
    return deduped[:2]


def _is_follow_up_request(message: str) -> bool:
    lowered = " ".join(message.lower().split())
    return lowered in _FOLLOW_UP_MESSAGES


def _resolve_follow_up_message(session_id: str, message: str) -> str:
    if not _is_follow_up_request(message):
        return message

    history = get_messages(session_id)
    normalized_current = " ".join(message.lower().split())
    skipped_current = False
    for item in reversed(history):
        if item["role"] != "user":
            continue
        content = str(item.get("content", "")).strip()
        normalized = " ".join(content.lower().split())
        if not skipped_current and normalized == normalized_current:
            skipped_current = True
            continue
        if not content or _is_follow_up_request(content):
            continue
        if should_execute(content) or _is_edit_request(content):
            return (
                f"{content}\n\n"
                "Follow-up instruction: retry the previous request, keep the same scope, "
                "and fix the last issues instead of changing the project type."
            )
        return content
    return message


def _looks_like_information_request(message: str) -> bool:
    lowered = " ".join(message.lower().split())
    if not lowered:
        return False
    if should_execute(lowered) or _is_edit_request(lowered):
        return False
    if lowered.endswith("?"):
        return True
    if any(lowered.startswith(prefix + " ") for prefix in _QUESTION_PREFIXES):
        return True
    return any(
        phrase in lowered
        for phrase in (
            "what is",
            "what does",
            "how does",
            "tell me about",
            "explain this",
            "summarize this",
            "latest news",
            "news about",
            "current news",
        )
    )


def _should_auto_route_to_ask(mode: str, message: str) -> bool:
    return mode == AgentMode.AGENT and _looks_like_information_request(message)


def _looks_like_project_summary_question(message: str) -> bool:
    lowered = " ".join(message.lower().split())
    return any(
        phrase in lowered
        for phrase in (
            "what this project do",
            "what does this project do",
            "what is this project",
            "what this code do",
            "what does it do",
            "what project is this",
        )
    )


def _response_lacks_context(answer: str) -> bool:
    lowered = answer.lower()
    return any(
        phrase in lowered
        for phrase in (
            "this conversation has just started",
            "i haven't received any information",
            "provide more context",
            "need more context",
            "not enough context",
        )
    )


def _find_last_substantive_code_request(session_id: str, current_message: str) -> str:
    normalized_current = " ".join(current_message.lower().split())
    skipped_current = False
    for item in reversed(get_messages(session_id)):
        if item["role"] != "user":
            continue
        content = str(item.get("content", "")).strip()
        normalized = " ".join(content.lower().split())
        if not skipped_current and normalized == normalized_current:
            skipped_current = True
            continue
        if not content or _is_follow_up_request(content):
            continue
        if should_execute(content) or _is_edit_request(content):
            return content
    return ""


def _build_local_project_summary(
    session_id: str,
    current_message: str,
    workspace_files: list[str],
) -> str:
    request_summary = _find_last_substantive_code_request(session_id, current_message)
    top_levels = sorted({path.split("/")[0] for path in workspace_files if path})
    notable_files = workspace_files[:8]

    lines: list[str] = []
    if request_summary:
        lines.append(
            f"In this chat, the active project request is: {request_summary}"
        )
    else:
        lines.append(
            "This chat already has project context, but I could not find a single earlier build request to summarize."
        )

    if workspace_files:
        lines.append(
            f"The current workspace contains {len(workspace_files)} files."
        )
        if top_levels:
            lines.append(
                "Main project areas: " + ", ".join(top_levels[:6]) + "."
            )
        if notable_files:
            lines.append(
                "Notable files: " + ", ".join(notable_files[:8]) + "."
            )
    else:
        lines.append("The workspace is currently empty, so only the chat request defines the project.")

    lines.append(
        "If you want, I can also break down the architecture, explain the file layout, or walk through how the generated pieces fit together."
    )
    return "\n\n".join(lines)


def _generate_with_tools(
    message: str,
    context: dict[str, Any],
    plan: Plan,
    remaining_files: list[str],
    accepted_files: list[str],
    require_structure: bool,
    retry_errors: list[str],
    attempt: int,
    provider_name: str | None,
    session_id: str,
    context_snapshot: ContextSnapshot | None = None,
) -> dict[str, Any]:
    research_blocks: list[str] = []
    tool_events: list[dict[str, Any]] = []
    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    search_provider = context.get("webSearchProvider")

    if attempt == 1 and not accepted_files and _should_auto_search(message):
        for query in _build_auto_search_queries(message, plan):
            try:
                results = run_tool(
                    "web_search",
                    query=query,
                    num_results=min(4, get_cached_settings().web_search.max_results),
                    provider=search_provider,
                    session_id=session_id,
                )
            except Exception as exc:
                logger.warning("Auto web search failed for query %r: %s", query, exc)
                continue
            if not results:
                continue
            research_blocks.append(_format_search_results_for_prompt(query, results))
            tool_events.append(
                {
                    "tool": "web_search",
                    "query": query,
                    "resultCount": len(results),
                    "provider": search_provider or get_cached_settings().web_search.provider,
                    "mode": "auto-seeded",
                }
            )

    for tool_iteration in range(1, _MAX_TOOL_ITERATIONS + 1):
        prompt = build_agent_prompt(
            message,
            context,
            plan,
            remaining_files=remaining_files,
            accepted_files=accepted_files,
            require_structure=require_structure,
            retry_errors=retry_errors,
            attempt=attempt,
            research_context="\n\n".join(research_blocks),
            context_snapshot=context_snapshot,
        )
        response = generate_with_provider(prompt, provider_name=provider_name)
        provider_status = {
            "used": True,
            "provider": response.provider,
            "model": response.model,
        }
        content = response.content.strip()
        tool_call, tool_error = _parse_tool_call(content)
        if tool_error:
            return {
                "ok": False,
                "error": tool_error,
                "providerStatus": provider_status,
                "toolEvents": tool_events,
            }
        if tool_call is None:
            return {
                "ok": True,
                "content": content,
                "providerStatus": provider_status,
                "toolEvents": tool_events,
            }
        if tool_iteration == _MAX_TOOL_ITERATIONS:
            return {
                "ok": False,
                "error": "Model kept requesting web_search after the maximum tool iterations.",
                "providerStatus": provider_status,
                "toolEvents": tool_events,
            }

        try:
            results = run_tool(
                "web_search",
                query=tool_call["query"],
                num_results=tool_call["num_results"],
                provider=search_provider,
                session_id=session_id,
            )
        except Exception as exc:
            if _is_web_search_setup_error(exc):
                return {
                    "ok": False,
                    "error": _build_web_search_unavailable_message(str(exc)),
                    "providerStatus": provider_status,
                    "toolEvents": tool_events,
                }
            raise
        if not results:
            return {
                "ok": False,
                "error": f"web_search returned no results for query: {tool_call['query']}",
                "providerStatus": provider_status,
                "toolEvents": tool_events,
            }
        research_blocks.append(_format_search_results_for_prompt(tool_call["query"], results))
        tool_events.append(
            {
                "tool": "web_search",
                "query": tool_call["query"],
                "resultCount": len(results),
                "provider": search_provider or get_cached_settings().web_search.provider,
            }
        )

    return {
        "ok": False,
        "error": "Tool loop exited unexpectedly.",
        "providerStatus": provider_status,
        "toolEvents": tool_events,
    }


def _generate_ask_with_tools(
    message: str,
    context: dict[str, Any],
    provider_name: str | None,
    session_id: str,
    context_snapshot: ContextSnapshot | None = None,
) -> dict[str, Any]:
    research_blocks: list[str] = []
    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    search_provider = context.get("webSearchProvider")
    plan = create_plan(message, [])

    if _should_auto_search(message):
        for query in _build_auto_search_queries(message, plan):
            try:
                results = run_tool(
                    "web_search",
                    query=query,
                    num_results=min(4, get_cached_settings().web_search.max_results),
                    provider=search_provider,
                    session_id=session_id,
                )
            except Exception as exc:
                logger.warning("Ask-mode auto search failed for query %r: %s", query, exc)
                continue
            if results:
                research_blocks.append(_format_search_results_for_prompt(query, results))

    for _ in range(_MAX_TOOL_ITERATIONS):
        prompt = _build_ask_prompt_with_context(
            message,
            context,
            context_snapshot=context_snapshot,
            research_context="\n\n".join(research_blocks),
        )
        response = generate_with_provider(prompt, provider_name=provider_name)
        provider_status = {
            "used": True,
            "provider": response.provider,
            "model": response.model,
        }
        content = response.content.strip()
        tool_call, tool_error = _parse_tool_call(content)
        if tool_error:
            return {
                "message": f"Provider returned an invalid tool request: {tool_error}",
                "providerStatus": provider_status,
            }
        if tool_call is None:
            return {"message": content, "providerStatus": provider_status}

        try:
            results = run_tool(
                "web_search",
                query=tool_call["query"],
                num_results=tool_call["num_results"],
                provider=search_provider,
                session_id=session_id,
            )
        except Exception as exc:
            if _is_web_search_setup_error(exc):
                return {
                    "message": _build_web_search_unavailable_message(str(exc)),
                    "providerStatus": provider_status,
                }
            raise
        if not results:
            return {
                "message": f"Web search returned no results for query: {tool_call['query']}",
                "providerStatus": provider_status,
            }
        research_blocks.append(_format_search_results_for_prompt(tool_call["query"], results))

    return {
        "message": "Reached the maximum number of tool-assisted reasoning steps without a final answer.",
        "providerStatus": provider_status,
    }


def _build_agent_steps(plan: Plan) -> tuple[PlanStep, PlanStep, PlanStep, PlanStep]:
    execute_step = PlanStep(
        id="execute-files",
        name="Execute Generation",
        status=StepStatus.PENDING,
        description="Requested strict multi-file output from the model.",
    )
    validate_step = PlanStep(
        id="validate-output",
        name="Validate Output",
        status=StepStatus.PENDING,
        description="Validated FILE blocks, planned structure, expected file count, and per-file syntax.",
    )
    write_step = PlanStep(
        id="write-files",
        name="Write Files",
        status=StepStatus.PENDING,
        description="Wrote validated files directly into the workspace.",
    )
    sandbox_step = PlanStep(
        id="docker-sandbox",
        name="Docker Sandbox",
        status=StepStatus.PENDING,
        description="Runs generated files in an isolated Docker validation workspace when enabled.",
    )
    plan.steps.extend([execute_step, validate_step, sandbox_step, write_step])
    return execute_step, validate_step, sandbox_step, write_step


def _build_success_message(plan: Plan, files_modified: list[str]) -> str:
    file_list = "\n".join(f"- {path}" for path in files_modified)
    return (
        f"Generated {len(files_modified)} files.\n\n"
        f"Structure:\n{plan.project_structure}\n\n"
        f"Files written:\n{file_list}"
    )


def run_agent_mode(
    message: str,
    session_id: str,
    context: dict[str, Any],
    provider_name: str | None,
) -> dict[str, Any]:
    workspace_files = [
        item["path"] for item in list_files_flat() if item["type"] == "file"
    ]
    plan = create_plan(message, workspace_files)

    # --- Build codebase context snapshot (file snippets + history) ---
    context_snapshot = build_context_snapshot(
        session_id, plan.files_of_interest, context
    )

    execute_step, validate_step, sandbox_step, write_step = _build_agent_steps(plan)

    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    validation_errors: list[str] = []
    accepted_files: dict[str, str] = {}
    structure_present = False
    remaining_files = list(plan.expected_files)

    for attempt in range(1, 4):
        try:
            generation = _generate_with_tools(
                message,
                context,
                plan,
                remaining_files=remaining_files,
                accepted_files=list(accepted_files.keys()),
                require_structure=not structure_present,
                retry_errors=validation_errors,
                attempt=attempt,
                provider_name=provider_name,
                session_id=session_id,
                context_snapshot=context_snapshot,
            )
            provider_status = generation["providerStatus"]
            execute_step.status = StepStatus.COMPLETED
            execute_step.details = (
                f"Attempt {attempt} of 3. Remaining files before generation: "
                f"{len(remaining_files) or plan.expected_file_count}. "
                f"Tool calls used: {len(generation.get('toolEvents', []))}."
            )
            if not generation["ok"]:
                validation_errors = [generation["error"]]
                validate_step.status = StepStatus.FAILED
                validate_step.details = generation["error"]
                logger.warning("Generation attempt %d tool phase failed: %s", attempt, generation["error"])
                continue
            raw_output = generation["content"]
            normalized_output, normalization_notes = normalize_generation_output(
                raw_output,
                plan,
                require_structure=not structure_present,
            )
            logger.info(
                "Provider %s responded after %d tool calls (%d chars)",
                provider_status.get("provider"),
                len(generation.get("toolEvents", [])),
                len(normalized_output),
            )
        except Exception as exc:
            logger.exception("Provider call failed for session=%s: %s", session_id, exc)
            execute_step.status = StepStatus.FAILED
            execute_step.error = str(exc)
            validate_step.status = StepStatus.FAILED
            write_step.status = StepStatus.FAILED
            return {
                "message": f"Generation failed because the provider could not answer: {exc}",
                "mode": AgentMode.AGENT,
                "steps": [step.to_dict() for step in plan.steps],
                "filesModified": [],
                "plan": plan.to_dict(),
                "providerStatus": {
                    "used": False,
                    "provider": provider_name or "none",
                    "error": str(exc),
                },
            }

        validation = validate_generation_output(
            normalized_output,
            plan,
            required_files=remaining_files,
            require_structure=not structure_present,
            known_files=accepted_files,
        )
        repair_notes = list(normalization_notes)
        if validation["errors"]:
            repaired_output, deterministic_notes = repair_generation_output(
                normalized_output,
                plan,
                validation["errors"],
            )
            if deterministic_notes:
                repair_notes.extend(deterministic_notes)
                validation = validate_generation_output(
                    repaired_output,
                    plan,
                    required_files=remaining_files,
                    require_structure=not structure_present,
                    known_files=accepted_files,
                )
                normalized_output = repaired_output
        for path in validation.get("invalidPaths", []):
            accepted_files.pop(path, None)
        structure_present = structure_present or validation["structurePresent"]
        for item in validation["validFiles"]:
            accepted_files[item["path"]] = item["content"]
        remaining_files = [
            path for path in plan.expected_files if path not in accepted_files
        ]
        validate_messages = list(validation["errors"])
        if repair_notes:
            validate_messages = [*repair_notes, *validate_messages]
        validate_step.details = "\n".join(validate_messages) or "Validated successfully."
        if structure_present and not remaining_files:
            validate_step.status = StepStatus.COMPLETED
            ordered_files = [
                {"path": path, "content": accepted_files[path]}
                for path in plan.expected_files
                if path in accepted_files
            ]
            extra_files = [
                {"path": path, "content": content}
                for path, content in accepted_files.items()
                if path not in plan.expected_files
            ]
            all_files = ordered_files + extra_files

            # --- Semantic reviewer pass (multi-role reasoning) ---
            review_step = PlanStep(
                id="reviewer-pass",
                name="Reviewer Pass",
                status=StepStatus.RUNNING,
                description="Senior-engineer review: checking cross-file consistency and logic.",
            )
            plan.steps.append(review_step)
            reviewer_issues = review_generation(
                all_files, plan.summary, provider_name
            )
            if reviewer_issues:
                review_step.status = StepStatus.COMPLETED
                review_step.details = (
                    "Reviewer warnings (advisory only): " + " | ".join(reviewer_issues)
                )
                logger.warning(
                    "Reviewer found %d advisory issues on attempt %d",
                    len(reviewer_issues), attempt,
                )
            else:
                review_step.status = StepStatus.COMPLETED
                review_step.details = "No issues found."

            sandbox_step.status = StepStatus.RUNNING
            sandbox_result = validate_files_in_docker_sandbox(all_files)
            sandbox_step.details = sandbox_result["details"]
            if sandbox_result["ok"]:
                sandbox_step.status = StepStatus.COMPLETED
            else:
                sandbox_step.status = StepStatus.FAILED
                validation_errors = sandbox_result["errors"] or [sandbox_result["details"]]
                validate_step.status = StepStatus.FAILED
                validate_step.details = "\n".join(validation_errors)
                remaining_files = [
                    path for path in plan.expected_files if path in accepted_files
                ]
                for path in remaining_files:
                    accepted_files.pop(path, None)
                logger.warning(
                    "Docker sandbox validation failed on attempt %d: %s",
                    attempt,
                    validation_errors,
                )
                continue

            write_result = write_generated_files(
                all_files,
                summary=f"Agent generation for session {session_id}",
            )
            write_step.status = StepStatus.COMPLETED
            write_step.details = ", ".join(write_result["filesModified"])
            return {
                "message": _build_success_message(plan, write_result["filesModified"]),
                "mode": AgentMode.AGENT,
                "steps": [step.to_dict() for step in plan.steps],
                "filesModified": write_result["filesModified"],
                "plan": plan.to_dict(),
                "providerStatus": provider_status,
            }

        validate_step.status = StepStatus.FAILED if validation["errors"] else StepStatus.PENDING
        validation_errors = list(validation["errors"])
        if not structure_present:
            validation_errors.append("Project structure block is still missing.")
        if remaining_files:
            validation_errors.append(
                "Still missing files: " + ", ".join(remaining_files)
            )
        logger.warning("Generation attempt %d failed validation: %s", attempt, validation_errors)

    write_step.status = StepStatus.FAILED
    write_step.error = "Validation failed after 3 attempts."
    accepted_expected_count = sum(
        1 for path in plan.expected_files if path in accepted_files
    )
    final_message = (
        f"{plan.summary}\n\n"
        "Generation failed validation after 3 attempts.\n\n"
        f"Structure:\n{plan.project_structure}\n\n"
        f"Accepted files so far: {accepted_expected_count} / {plan.expected_file_count}\n\n"
        "Errors:\n" + "\n".join(f"- {error}" for error in validation_errors)
    )
    return {
        "message": final_message,
        "mode": AgentMode.AGENT,
        "steps": [step.to_dict() for step in plan.steps],
        "filesModified": [],
        "plan": plan.to_dict(),
        "providerStatus": provider_status,
    }


def run_ask_mode(
    message: str,
    session_id: str,
    context: dict[str, Any],
    provider_name: str | None,
) -> dict[str, Any]:
    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    answer = ""
    workspace_files = [
        item["path"] for item in list_files_flat() if item["type"] == "file"
    ]
    plan = create_plan(message, workspace_files)
    context_snapshot = build_context_snapshot(
        session_id, plan.files_of_interest, context
    )

    try:
        ask_result = _generate_ask_with_tools(
            message,
            context,
            provider_name,
            session_id,
            context_snapshot=context_snapshot,
        )
        answer = ask_result["message"].strip()
        provider_status = ask_result["providerStatus"]
        if _looks_like_project_summary_question(message) and _response_lacks_context(answer):
            answer = _build_local_project_summary(session_id, message, workspace_files)
        logger.info("Ask mode: provider %s responded", provider_status.get("provider"))
    except Exception as exc:
        logger.exception("Ask mode provider failed for session=%s: %s", session_id, exc)
        if _is_web_search_setup_error(exc):
            answer = _build_web_search_unavailable_message(str(exc))
        elif _looks_like_project_summary_question(message):
            answer = _build_local_project_summary(session_id, message, workspace_files)
        else:
            answer = f"Provider unavailable: {exc}"
        provider_status = {"used": False, "provider": provider_name or "none", "error": str(exc)}

    return {
        "message": answer,
        "mode": AgentMode.ASK,
        "steps": [],
        "filesModified": [],
        "plan": None,
        "providerStatus": provider_status,
    }


def _run_decompose_mode(
    message: str,
    session_id: str,
    context: dict[str, Any],
    provider_name: str | None,
) -> dict[str, Any]:
    """Decompose a complex task into subtasks without executing any code."""
    workspace_files = [
        item["path"] for item in list_files_flat() if item["type"] == "file"
    ]
    plan = create_plan(message, workspace_files)
    snapshot = build_context_snapshot(session_id, plan.files_of_interest, context)
    context_block = snapshot.to_prompt_block()

    decompose_prompt = (
        "You are a senior software architect performing task decomposition.\n"
        "Break the following request into concrete, ordered subtasks.\n"
        "Each subtask should be independently implementable and testable.\n"
        "Identify dependencies between subtasks (mark them as 'depends on step N').\n"
        "Output format: numbered list, one subtask per line.\n"
        "After the list, add a section '## Risk' with: low / medium / high and one-line reason.\n\n"
        f"{context_block}\n\n"
        f"Request: {message}\n\n"
        "Decompose now:"
    )

    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    try:
        response = generate_with_provider(decompose_prompt, provider_name=provider_name)
        provider_status = {
            "used": True,
            "provider": response.provider,
            "model": response.model,
        }
        decomposition = response.content.strip()
        logger.info(
            "Decompose mode: provider %s produced %d chars",
            response.provider, len(decomposition),
        )
    except Exception as exc:
        logger.exception("Decompose mode provider call failed: %s", exc)
        decomposition = f"Provider unavailable: {exc}\n\nFallback plan:\n{plan.project_structure}"
        provider_status = {"used": False, "provider": provider_name or "none", "error": str(exc)}

    return {
        "message": decomposition,
        "mode": AgentMode.DECOMPOSE,
        "steps": [],
        "filesModified": [],
        "plan": plan.to_dict(),
        "providerStatus": provider_status,
    }


def run_agent(
    message: str,
    session_id: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    mode = context.get("mode", AgentMode.AGENT)
    provider_name = context.get("provider")
    resolved_message = message

    logger.info(
        "run_agent session=%s mode=%s provider=%s",
        session_id, mode, provider_name or "default",
    )

    append_message(session_id, "user", message, {"context": context})
    resolved_message = _resolve_follow_up_message(session_id, message)
    if _should_auto_route_to_ask(mode, resolved_message):
        logger.info("run_agent: auto-routing informational request to ask mode")
        mode = AgentMode.ASK

    # --- Smart mode auto-detection: override AGENT → EDIT if message looks like a targeted patch ---
    if mode == AgentMode.AGENT and _is_edit_request(resolved_message):
        logger.info("run_agent: auto-detected EDIT request — switching to edit mode")
        mode = AgentMode.EDIT

    result: dict[str, Any] = {}
    if mode == AgentMode.PLAN:
        result = run_plan_agent(resolved_message, session_id, context, provider_name)
    elif mode == AgentMode.ASK:
        result = run_ask_mode(resolved_message, session_id, context, provider_name)
    elif mode == AgentMode.EDIT:
        result = run_edit_mode(resolved_message, session_id, context, provider_name)
        # If the edit agent couldn't find a target file, fall back to agent mode
        if result.get("fallback"):
            logger.info("run_agent: edit mode fallback — running agent mode instead")
            result = run_agent_mode(resolved_message, session_id, context, provider_name)
    elif mode == AgentMode.DECOMPOSE:
        result = _run_decompose_mode(resolved_message, session_id, context, provider_name)
    else:
        result = run_agent_mode(resolved_message, session_id, context, provider_name)

    append_message(
        session_id,
        "assistant",
        result["message"],
        {
            "mode": result["mode"],
            "plan": result.get("plan"),
            "providerStatus": result["providerStatus"],
            "filesModified": result.get("filesModified", []),
            "planDocument": result.get("planDocument"),
        },
    )

    result["sessionId"] = session_id
    return result
