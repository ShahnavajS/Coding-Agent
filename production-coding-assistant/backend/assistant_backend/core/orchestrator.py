from __future__ import annotations

import logging
from typing import Any

from assistant_backend.core.executor import build_execution_preview, infer_target_path, should_execute
from assistant_backend.core.planner import create_plan
from assistant_backend.providers.router import generate as generate_with_provider
from assistant_backend.storage.database import append_message
from assistant_backend.tools.filesystem_tool import list_files_flat

logger = logging.getLogger(__name__)


def build_provider_prompt(
    message: str,
    context: dict[str, Any],
    files_of_interest: list[str],
) -> str:
    active_file = context.get("activeFilePath") or "none"
    selected_text = context.get("selectedText") or ""
    target = infer_target_path(message, context)
    is_code_request = should_execute(message)

    # For code-generation requests, instruct the model to return a single complete
    # implementation inside ONE fenced code block — no skeletons, no placeholders.
    code_instruction = ""
    if is_code_request and target:
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
        f"User request:\n{message}\n\n"
        f"Active file: {active_file}\n"
        f"Files of interest: {', '.join(files_of_interest) or 'none'}\n"
        f"Selected text:\n{selected_text[:1200]}"
        f"{code_instruction}"
    )


def run_agent(
    message: str,
    session_id: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    workspace_files = [
        item["path"] for item in list_files_flat() if item["type"] == "file"
    ]
    plan = create_plan(message, workspace_files)
    append_message(session_id, "user", message, {"context": context})

    provider_name = context.get("provider")
    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    provider_message = ""

    logger.info("Running agent for session=%s provider=%s", session_id, provider_name or "default")

    try:
        provider_response = generate_with_provider(
            build_provider_prompt(message, context, plan.files_of_interest),
            provider_name=provider_name,
        )
        provider_message = provider_response.content.strip()
        provider_status = {
            "used": True,
            "provider": provider_response.provider,
            "model": provider_response.model,
        }
        logger.info(
            "Provider %s responded (%d chars)",
            provider_response.provider,
            len(provider_message),
        )
    except Exception as exc:
        logger.exception("Provider call failed for session=%s: %s", session_id, exc)
        provider_message = (
            "No live model response was available. The planner is still active, "
            "but your selected provider could not answer and no fallback succeeded.\n\n"
            f"Detail: {exc}"
        )
        provider_status = {
            "used": False,
            "provider": provider_name or "none",
            "error": str(exc),
        }

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
            final_message += (
                f"\n\nModel: {provider_status['provider']} / {provider_status['model']}"
            )
        logger.info("Execution preview ready for %s", execution_preview["path"])
    else:
        # No file was generated — return the plan + provider explanation
        final_message = (
            f"{plan.summary}\n\n"
            f"Risk: {plan.risk_level}\n"
            f"Suggested files: {', '.join(plan.files_of_interest) or 'none'}\n\n"
            f"{provider_message}"
        )
        logger.info("No execution preview — returning plan only")

    append_message(
        session_id,
        "assistant",
        final_message,
        {
            "plan": plan.to_dict(),
            "providerStatus": provider_status,
            "executionPreview": execution_preview,
        },
    )

    return {
        "message": final_message,
        "steps": [step.to_dict() for step in plan.steps],
        "filesModified": [execution_preview["path"]] if execution_preview else [],
        "plan": plan.to_dict(),
        "providerStatus": provider_status,
        "diffPreview": execution_preview,
    }
