from __future__ import annotations

"""Plan agent — researches the codebase and produces a structured plan.

Behaviour mirrors the plan.agent.md spec:
  - Discovery: lists workspace files, reads files of interest
  - Design: produces a comprehensive markdown plan following the style guide
  - Never writes or executes code — plan only
"""

import logging
import re
import uuid
from typing import Any

from assistant_backend.core.models import AgentMode, Plan, PlanDocument, PlanStep, RiskLevel
from assistant_backend.core.planner import create_plan
from assistant_backend.providers.router import generate as generate_with_provider
from assistant_backend.tools.filesystem_tool import list_files_flat, read_text_file

logger = logging.getLogger(__name__)

# Maximum characters read from each file of interest
_MAX_FILE_CHARS = 2000
# Maximum number of files to read for context
_MAX_FILES_TO_READ = 4


def _read_files_of_interest(paths: list[str]) -> dict[str, str]:
    """Read the first N files of interest for context, truncating long files."""
    snippets: dict[str, str] = {}
    for path in paths[:_MAX_FILES_TO_READ]:
        try:
            content = read_text_file(path)
            snippets[path] = content[:_MAX_FILE_CHARS] + (
                "\n… (truncated)" if len(content) > _MAX_FILE_CHARS else ""
            )
        except Exception as exc:
            snippets[path] = f"(could not read: {exc})"
    return snippets


def _build_plan_prompt(
    message: str,
    context: dict[str, Any],
    workspace_files: list[str],
    file_snippets: dict[str, str],
) -> str:
    active_file    = context.get("activeFilePath") or "none"
    selected_text  = context.get("selectedText") or ""
    files_list     = "\n".join(f"  - {f}" for f in workspace_files[:30]) or "  (empty workspace)"

    snippets_block = ""
    if file_snippets:
        parts = []
        for path, content in file_snippets.items():
            parts.append(f"### {path}\n```\n{content}\n```")
        snippets_block = "\n\n**Relevant file contents:**\n" + "\n\n".join(parts)

    selected_block = (
        f"\n\n**Selected text:**\n```\n{selected_text[:800]}\n```"
        if selected_text else ""
    )

    return f"""You are a PLANNING AGENT for a production-grade AI coding assistant.

Your SOLE responsibility is producing a detailed, actionable implementation plan.
NEVER write, execute, or suggest executing code. NEVER implement anything.
You research the codebase, clarify requirements, and capture findings into a plan.

## Plan style guide

Produce a markdown plan using EXACTLY this structure:

## Plan: {{Title (2-10 words)}}

{{TL;DR — what, why, and recommended approach (2-3 sentences)}}

**Steps**
1. {{Step — note dependencies or parallelism when applicable}}
2. …

**Relevant files**
- `{{full/path/to/file}}` — {{what to modify or reuse}}

**Verification**
1. {{Specific verification step — commands, tests, or manual checks}}

**Decisions** (if applicable)
- {{Key decisions, assumptions, scope inclusions/exclusions}}

**Further Considerations** (if applicable, max 3)
1. {{Clarifying question or open issue with recommendation}}

Rules:
- No code blocks in the plan — describe changes in plain English
- Be specific enough that another engineer can implement without asking questions
- Mark steps that can run in parallel vs steps that depend on prior steps
- Identify risk level: low / medium / high

---

**User request:** {message}

**Active file:** {active_file}

**Workspace files:**
{files_list}
{snippets_block}{selected_block}

Produce a comprehensive plan now. Do NOT start implementing.
"""


def _parse_plan_document(markdown: str, risk_level: str) -> PlanDocument:
    """Parse the provider's markdown plan into a structured PlanDocument."""
    title_match = re.search(r"##\s*Plan:\s*(.+)", markdown)
    title = title_match.group(1).strip() if title_match else "Implementation Plan"

    # TL;DR is the first paragraph after the title
    tldr = ""
    tldr_match = re.search(r"##\s*Plan:.+\n+([^#\*\n][^\n]+(?:\n[^#\*\n][^\n]+)*)", markdown)
    if tldr_match:
        tldr = tldr_match.group(1).strip()

    # Numbered steps
    steps = re.findall(r"^\d+\.\s+(.+)$", markdown, re.MULTILINE)

    # Relevant files (lines starting with backtick path)
    relevant_files = re.findall(r"`([^`]+)`\s*—", markdown)

    # Verification items
    verification_match = re.search(
        r"\*\*Verification\*\*.*?\n(.*?)(?=\n\*\*|\Z)", markdown, re.DOTALL
    )
    verification = []
    if verification_match:
        verification = re.findall(r"^\d+\.\s+(.+)$", verification_match.group(1), re.MULTILINE)

    # Decisions
    decisions_match = re.search(
        r"\*\*Decisions\*\*.*?\n(.*?)(?=\n\*\*|\Z)", markdown, re.DOTALL
    )
    decisions = []
    if decisions_match:
        decisions = re.findall(r"^-\s+(.+)$", decisions_match.group(1), re.MULTILINE)

    # Further considerations
    considerations_match = re.search(
        r"\*\*Further Considerations\*\*.*?\n(.*?)(?=\n\*\*|\Z)", markdown, re.DOTALL
    )
    considerations = []
    if considerations_match:
        considerations = re.findall(
            r"^\d+\.\s+(.+)$", considerations_match.group(1), re.MULTILINE
        )

    return PlanDocument(
        title=title,
        tldr=tldr,
        steps=steps,
        relevant_files=relevant_files,
        verification=verification,
        decisions=decisions,
        considerations=considerations,
        risk_level=risk_level,
        raw_markdown=markdown,
    )


def run_plan_agent(
    message: str,
    session_id: str,
    context: dict[str, Any],
    provider_name: str | None,
) -> dict[str, Any]:
    """Run the Plan agent — research + structured plan, no code execution."""
    workspace_files = [
        item["path"] for item in list_files_flat() if item["type"] == "file"
    ]
    base_plan = create_plan(message, workspace_files)
    file_snippets = _read_files_of_interest(base_plan.files_of_interest)

    prompt = _build_plan_prompt(message, context, workspace_files, file_snippets)

    provider_status: dict[str, Any] = {"used": False, "provider": provider_name or "none"}
    plan_markdown = ""

    try:
        response = generate_with_provider(prompt, provider_name=provider_name)
        plan_markdown = response.content.strip()
        provider_status = {
            "used": True,
            "provider": response.provider,
            "model": response.model,
        }
        logger.info("Plan agent got response from %s (%d chars)", response.provider, len(plan_markdown))
    except Exception as exc:
        logger.exception("Plan agent provider call failed: %s", exc)
        plan_markdown = (
            f"## Plan: {message[:60]}\n\n"
            "Provider was unavailable — here is a basic structural plan.\n\n"
            "**Steps**\n"
            "1. Review the relevant files listed below\n"
            "2. Implement the requested changes\n"
            "3. Run tests to verify\n\n"
            f"**Relevant files**\n"
            + "\n".join(f"- `{f}`" for f in base_plan.files_of_interest)
        )
        provider_status = {"used": False, "provider": provider_name or "none", "error": str(exc)}

    doc = _parse_plan_document(plan_markdown, base_plan.risk_level)

    # Build plan steps from the structured document
    plan_steps = [
        PlanStep(
            id=str(uuid.uuid4()),
            name="Discovery",
            status="completed",
            description=f"Analysed {len(workspace_files)} workspace files.",
            details=f"Files of interest: {', '.join(base_plan.files_of_interest) or 'none'}",
        ),
        PlanStep(
            id=str(uuid.uuid4()),
            name="Plan Generated",
            status="completed",
            description=f"{doc.title} — {len(doc.steps)} steps identified.",
            details=f"Risk: {doc.risk_level}",
        ),
    ]
    if doc.considerations:
        plan_steps.append(PlanStep(
            id=str(uuid.uuid4()),
            name="Open Questions",
            status="pending",
            description="Further considerations require clarification before implementation.",
            details="\n".join(doc.considerations),
        ))

    return {
        "message": plan_markdown,
        "mode": AgentMode.PLAN,
        "planDocument": doc.to_dict(),
        "steps": [s.to_dict() for s in plan_steps],
        "filesModified": [],
        "plan": base_plan.to_dict(),
        "providerStatus": provider_status,
        "diffPreview": None,
    }
