from __future__ import annotations

import logging
import uuid

from assistant_backend.core.models import Plan, PlanStep, RiskLevel

logger = logging.getLogger(__name__)

_HIGH_RISK_TOKENS = frozenset({"delete", "remove", "drop", "reset", "wipe", "purge"})
_LOW_RISK_TOKENS = frozenset({"read", "inspect", "explain", "show", "list", "describe"})


def _classify_risk(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in _HIGH_RISK_TOKENS):
        return RiskLevel.HIGH
    if any(token in lowered for token in _LOW_RISK_TOKENS):
        return RiskLevel.LOW
    return RiskLevel.MEDIUM


def _find_files_of_interest(message: str, workspace_files: list[str]) -> list[str]:
    """Return workspace files whose names appear as tokens in the message."""
    tokens = set(message.lower().replace(",", " ").split())
    matched = [
        path for path in workspace_files
        if any(token and token in path.lower() for token in tokens)
    ]
    return matched[:5] if matched else workspace_files[:3]


def create_plan(message: str, workspace_files: list[str]) -> Plan:
    """Analyse the user's message and produce an execution plan."""
    risk_level = _classify_risk(message)
    files_of_interest = _find_files_of_interest(message, workspace_files)

    logger.debug(
        "Plan created: risk=%s files=%s",
        risk_level,
        files_of_interest,
    )

    steps = [
        PlanStep(
            id=str(uuid.uuid4()),
            name="Analyze Request",
            status="completed",
            description="Parsed the prompt and estimated risk, affected files, and likely execution path.",
            details=f"Risk level: {risk_level}. Files of interest: {', '.join(files_of_interest) or 'none'}",
        ),
        PlanStep(
            id=str(uuid.uuid4()),
            name="Prepare Validation",
            status="completed",
            description="Prepared parser, formatter, and checkpoint workflow before any write.",
        ),
        PlanStep(
            id=str(uuid.uuid4()),
            name="Execution Recommendation",
            status="completed",
            description="Recommend using diff-preview and checkpointed apply for any file mutation.",
        ),
    ]

    return Plan(
        summary=f"Plan generated for: {message}",
        risk_level=risk_level,
        files_of_interest=files_of_interest,
        validation_plan=["syntax parse", "checkpoint before write", "atomic apply", "post-write validation"],
        steps=steps,
    )
