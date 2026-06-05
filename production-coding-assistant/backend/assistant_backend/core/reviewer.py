"""reviewer.py

Runs a focused code-review pass over generated files using the LLM.

After the executor generates code, this reviewer acts as a 'senior engineer
reviewing a PR' — it looks for semantic errors the syntax validator misses:
  - Broken cross-file imports (symbol defined in file A but misnamed in file B)
  - Incomplete implementations (stub functions with no body)
  - Inconsistent naming between layers (schema vs model vs route)
  - Missing entrypoints or obvious runtime errors

Returns a list of string issues to feed back into the orchestrator's retry loop.
If the code looks correct, returns an empty list (no retry triggered).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Only trigger a reviewer pass when the generated set is large enough to have
# cross-file issues worth catching.
_MIN_FILES_FOR_REVIEW = 3
# Limit how many files we send to the reviewer to keep the prompt small.
_MAX_FILES_FOR_REVIEW = 10
# Max chars per file sent to the reviewer.
_MAX_FILE_CHARS = 1_200


def _build_reviewer_prompt(files: list[dict[str, str]], plan_summary: str) -> str:
    file_blocks = []
    for item in files[:_MAX_FILES_FOR_REVIEW]:
        content = item["content"]
        if len(content) > _MAX_FILE_CHARS:
            content = content[:_MAX_FILE_CHARS] + "\n… (truncated)"
        file_blocks.append(f"FILE: {item['path']}\n{content}")

    files_text = "\n\n".join(file_blocks)

    return (
        "You are a senior software engineer reviewing generated code before it ships.\n"
        "Your ONLY job is to find real bugs — not style issues.\n\n"
        "Check for:\n"
        "1. Imports that reference symbols not exported by the target file\n"
        "2. Functions referenced in one file but not defined in another\n"
        "3. Schema/model/route naming inconsistencies (e.g. TodoCreate vs TodoCreateSchema)\n"
        "4. Incomplete stub implementations (functions with only `pass` or TODO)\n"
        "5. Missing entry points (e.g. if main.py exists but has no app/server creation)\n"
        "6. Package usage without the package being in requirements.txt or package.json\n\n"
        "If you find NO issues, respond with exactly: OK\n"
        "If you find issues, list them one per line starting with '-'.\n"
        "Do NOT suggest style improvements. Do NOT suggest new features. Only real bugs.\n"
        "Be concise — max 10 issues.\n\n"
        f"Task: {plan_summary}\n\n"
        f"Generated files:\n\n{files_text}"
    )


def review_generation(
    files: list[dict[str, str]],
    plan_summary: str,
    provider_name: str | None,
) -> list[str]:
    """Run a reviewer LLM pass over generated files.

    Args:
        files: List of {path, content} dicts from the generator.
        plan_summary: Short string describing what was built.
        provider_name: Which LLM provider to use (same as the generator used).

    Returns:
        List of issue strings. Empty list means the code passed review.
    """
    if len(files) < _MIN_FILES_FOR_REVIEW:
        logger.debug("reviewer: skipping pass — only %d files generated", len(files))
        return []

    # Import here to avoid circular imports at module load
    from assistant_backend.providers.router import generate as generate_with_provider

    prompt = _build_reviewer_prompt(files, plan_summary)

    try:
        response = generate_with_provider(prompt, provider_name=provider_name)
        content = response.content.strip()
        logger.info(
            "reviewer: got response from %s (%d chars)", response.provider, len(content)
        )
    except Exception as exc:
        logger.warning("reviewer: provider call failed (%s) — skipping review", exc)
        return []

    if content.strip().upper() == "OK" or not content.strip():
        logger.info("reviewer: no issues found")
        return []

    issues = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("-"):
            issue = line[1:].strip()
            if issue:
                issues.append(issue)
        elif line and not line.startswith("#"):
            # Accept bare lines too (model may not always use dashes)
            issues.append(line)

    logger.info("reviewer: found %d issues", len(issues))
    return issues[:10]  # cap at 10 to avoid flooding the retry prompt
