from __future__ import annotations

import json
import logging
import re
from typing import Any

from assistant_backend.config import get_cached_settings
from assistant_backend.core.executor import (
    should_execute,
    validate_generation_output,
    write_generated_files,
)
from assistant_backend.core.models import AgentMode, Plan, PlanStep, StepStatus
from assistant_backend.core.plan_agent import run_plan_agent
from assistant_backend.core.planner import create_plan
from assistant_backend.providers.router import generate as generate_with_provider
from assistant_backend.storage.database import append_message
from assistant_backend.tools import run_tool
from assistant_backend.tools.filesystem_tool import list_files_flat

logger = logging.getLogger(__name__)
_MAX_TOOL_ITERATIONS = 3
_AUTO_SEARCH_HINTS = ("latest", "current", "research", "official", "recent", "2025", "2026")


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
            "- app/services/rate_limiter.py should contain the rate-limiting policy.\n"
            "- app/services/retry_policy.py should contain retry/backoff logic.\n"
            "- app/observability.py should contain structured logging and monitoring hooks.\n"
            "- Put bottlenecks, scaling strategy, and operational tradeoffs in ARCHITECTURE.md.\n"
            "- Keep imports and exported helper names consistent across routes and services.\n\n"
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
        guidance.append("- When you regenerate dependent files, keep imports and exported symbols consistent in the same attempt.")

    import_symbol_re = re.compile(
        r"(?P<importer>[^:\n]+): imported symbol '(?P<symbol>[^']+)' is not defined in (?P<target>[^\n]+)"
    )
    for match in import_symbol_re.finditer(joined):
        importer = match.group("importer")
        symbol = match.group("symbol")
        target = match.group("target")
        required_exports.setdefault(target, set()).add(symbol)
        guidance.append(
            f"- Ensure {target} defines {symbol} exactly as imported by {importer}."
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


def _parse_tool_call(response_text: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = response_text.strip()
    if not stripped or not stripped.startswith("{") or not stripped.endswith("}"):
        return None, None
    if '"tool"' not in stripped:
        return None, None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, f"Tool call JSON is invalid: {exc.msg}"

    if not isinstance(payload, dict):
        return None, "Tool call must be a JSON object."

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

        results = run_tool(
            "web_search",
            query=tool_call["query"],
            num_results=tool_call["num_results"],
            provider=search_provider,
            session_id=session_id,
        )
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


def _build_agent_steps(plan: Plan) -> tuple[PlanStep, PlanStep, PlanStep]:
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
    plan.steps.extend([execute_step, validate_step, write_step])
    return execute_step, validate_step, write_step


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
    execute_step, validate_step, write_step = _build_agent_steps(plan)

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
            logger.info(
                "Provider %s responded after %d tool calls (%d chars)",
                provider_status.get("provider"),
                len(generation.get("toolEvents", [])),
                len(raw_output),
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
            raw_output,
            plan,
            required_files=remaining_files,
            require_structure=not structure_present,
            known_files=accepted_files,
        )
        for path in validation.get("invalidPaths", []):
            accepted_files.pop(path, None)
        structure_present = structure_present or validation["structurePresent"]
        for item in validation["validFiles"]:
            accepted_files[item["path"]] = item["content"]
        remaining_files = [
            path for path in plan.expected_files if path not in accepted_files
        ]
        validate_step.details = "\n".join(validation["errors"]) or "Validated successfully."
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
            write_result = write_generated_files(
                ordered_files + extra_files,
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

    try:
        response = generate_with_provider(
            build_ask_prompt(message, context),
            provider_name=provider_name,
        )
        answer = response.content.strip()
        provider_status = {"used": True, "provider": response.provider, "model": response.model}
        logger.info("Ask mode: provider %s responded", response.provider)
    except Exception as exc:
        logger.exception("Ask mode provider failed for session=%s: %s", session_id, exc)
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


def run_agent(
    message: str,
    session_id: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    mode = context.get("mode", AgentMode.AGENT)
    provider_name = context.get("provider")

    logger.info(
        "run_agent session=%s mode=%s provider=%s",
        session_id, mode, provider_name or "default",
    )

    append_message(session_id, "user", message, {"context": context})

    result: dict[str, Any] = {}
    if mode == AgentMode.PLAN:
        result = run_plan_agent(message, session_id, context, provider_name)
    elif mode == AgentMode.ASK:
        result = run_ask_mode(message, session_id, context, provider_name)
    else:
        result = run_agent_mode(message, session_id, context, provider_name)

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
