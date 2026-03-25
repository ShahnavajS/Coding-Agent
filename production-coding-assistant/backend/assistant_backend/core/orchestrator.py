from __future__ import annotations

import logging
from typing import Any

from assistant_backend.core.executor import build_execution_preview, infer_target_path, should_execute
from assistant_backend.core.models import AgentMode
from assistant_backend.core.plan_agent import run_plan_agent
from assistant_backend.core.planner import create_plan
from assistant_backend.providers.router import generate as generate_with_provider
from assistant_backend.storage.database import append_message
from assistant_backend.tools.filesystem_tool import list_files_flat

logger = logging.getLogger(__name__)


# ── Agent mode prompt ────────────────────────────────────────────────
def build_agent_prompt(
    message: str,
    context: dict[str, Any],
    files_of_interest: list[str],
) -> str:
    active_file   = context.get("activeFilePath") or "none"
    selected_text = context.get("selectedText") or ""
    target        = infer_target_path(message, "", context)
    is_code_req   = should_execute(message)

    code_instruction = ""
    if is_code_req and target:
        lang = target.rsplit(".", 1)[-1] if "." in target else "python"
        code_instruction = (
            f"\n\nCRITICAL INSTRUCTION: The user wants a real, working file.\n"
            f"You MUST respond with ONE complete ```{lang} ... ``` code block containing\n"
            f"the FULL implementation of `{target}` — no placeholders, no '# implementation',\n"
            f"no 'pass', no TODOs. Every method must have a real body. The code must run as-is.\n"
            f"Put ALL code in a single fenced block. Do not split it across multiple blocks.\n"
        )

    return (
        "You are the code-generation layer of a production-grade AI coding assistant.\n"
        "When asked to create or modify a file, return the COMPLETE file contents inside "
        "a single fenced code block. Never return skeletons or outlines.\n\n"
        "You have access to the following tools:\n"
        "- File operations: read, write, create, delete files in the workspace\n"
        "- Grep/Search: regex and literal search across all files with context lines\n"
        "- Find & Replace: preview and apply text replacements in files\n"
        "- Git: status, diff, log, branch, commit, stash, checkout\n"
        "- Code Analysis: extract symbols, compute complexity, detect code smells\n"
        "- Dependency Analysis: import graphs, reverse-dependency maps, project structure\n"
        "- Terminal: execute shell commands in the workspace\n"
        "- Diff Preview: preview and apply file changes with checkpoints\n\n"
        f"User request:\n{message}\n\n"
        f"Active file: {active_file}\n"
        f"Files of interest: {', '.join(files_of_interest) or 'none'}\n"
        f"Selected text:\n{selected_text[:1200]}"
        f"{code_instruction}"
    )


# ── Ask mode prompt ──────────────────────────────────────────────────
def build_ask_prompt(message: str, context: dict[str, Any]) -> str:
    active_file   = context.get("activeFilePath") or "none"
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


# ── Agent mode runner ────────────────────────────────────────────────
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

    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    provider_message = ""

    try:
        resp = generate_with_provider(
            build_agent_prompt(message, context, plan.files_of_interest),
            provider_name=provider_name,
        )
        provider_message = resp.content.strip()
        provider_status  = {"used": True, "provider": resp.provider, "model": resp.model}
        logger.info("Provider %s responded (%d chars)", resp.provider, len(provider_message))
    except Exception as exc:
        logger.exception("Provider call failed for session=%s: %s", session_id, exc)
        provider_message = (
            "No live model response available. The planner is still active, "
            "but your provider could not answer.\n\nDetail: " + str(exc)
        )
        provider_status = {"used": False, "provider": provider_name or "none", "error": str(exc)}

    execution_preview = build_execution_preview(message, provider_message, context)

    if execution_preview is not None:
        plan.steps.append(
            type(plan.steps[0])(
                id="execution-preview",
                name="Prepared Diff Preview",
                status="completed",
                description="Created a concrete file change and queued it for review.",
                details=f"Target file: {execution_preview['path']}",
            )
        )
        final_message = (
            f"Ready to create `{execution_preview['path']}`.\n\n"
            "A diff preview is waiting — review it and click **Apply** to write the file."
        )
        if provider_status.get("used"):
            final_message += f"\n\nModel: {provider_status['provider']} / {provider_status['model']}"
        logger.info("Execution preview ready for %s", execution_preview["path"])
    else:
        final_message = (
            f"{plan.summary}\n\n"
            f"Risk: {plan.risk_level}\n"
            f"Suggested files: {', '.join(plan.files_of_interest) or 'none'}\n\n"
            f"{provider_message}"
        )

    return {
        "message":       final_message,
        "mode":          AgentMode.AGENT,
        "steps":         [s.to_dict() for s in plan.steps],
        "filesModified": [execution_preview["path"]] if execution_preview else [],
        "plan":          plan.to_dict(),
        "providerStatus":provider_status,
        "diffPreview":   execution_preview,
    }


# ── Ask mode runner ──────────────────────────────────────────────────
def run_ask_mode(
    message: str,
    session_id: str,
    context: dict[str, Any],
    provider_name: str | None,
) -> dict[str, Any]:
    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    answer = ""

    try:
        resp    = generate_with_provider(build_ask_prompt(message, context), provider_name=provider_name)
        answer  = resp.content.strip()
        provider_status = {"used": True, "provider": resp.provider, "model": resp.model}
        logger.info("Ask mode: provider %s responded", resp.provider)
    except Exception as exc:
        logger.exception("Ask mode provider failed for session=%s: %s", session_id, exc)
        answer = f"Provider unavailable: {exc}"
        provider_status = {"used": False, "provider": provider_name or "none", "error": str(exc)}

    return {
        "message":       answer,
        "mode":          AgentMode.ASK,
        "steps":         [],
        "filesModified": [],
        "plan":          None,
        "providerStatus":provider_status,
        "diffPreview":   None,
    }


# ── Main entry point ─────────────────────────────────────────────────
def run_agent(
    message: str,
    session_id: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Route the request to the correct agent mode and persist to DB."""
    context       = context or {}
    mode          = context.get("mode", AgentMode.AGENT)
    provider_name = context.get("provider")

    logger.info(
        "run_agent session=%s mode=%s provider=%s",
        session_id, mode, provider_name or "default",
    )

    append_message(session_id, "user", message, {"context": context})

    # ── Route by mode ────────────────────────────────────────────────
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
            "mode":           result["mode"],
            "plan":           result.get("plan"),
            "providerStatus": result["providerStatus"],
            "executionPreview": result.get("diffPreview"),
            "planDocument":   result.get("planDocument"),
        },
    )

    result["sessionId"] = session_id
    return result
