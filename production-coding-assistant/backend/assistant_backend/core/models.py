from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class RiskLevel:
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class StepStatus:
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class AgentMode:
    """Mode the agent operates in — sent from the frontend."""
    AGENT = "agent"   # default: generate + execute code
    PLAN  = "plan"    # research + produce a structured plan, no code execution
    ASK   = "ask"     # conversational Q&A, no code execution


@dataclass
class PlanStep:
    id: str
    name: str
    status: str
    description: str
    details: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    summary: str
    risk_level: str
    files_of_interest: list[str] = field(default_factory=list)
    expected_files: list[str] = field(default_factory=list)
    expected_file_count: int = 0
    project_structure: str = ""
    validation_plan: list[str]   = field(default_factory=list)
    steps: list[PlanStep]        = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary":        self.summary,
            "riskLevel":      self.risk_level,
            "filesOfInterest":self.files_of_interest,
            "expectedFiles": self.expected_files,
            "expectedFileCount": self.expected_file_count,
            "projectStructure": self.project_structure,
            "validationPlan": self.validation_plan,
            "steps":          [s.to_dict() for s in self.steps],
        }


@dataclass
class PlanDocument:
    """A structured plan document produced by the Plan agent."""
    title: str
    tldr: str
    steps: list[str]
    relevant_files: list[str]
    verification: list[str]
    decisions: list[str]
    considerations: list[str]
    risk_level: str
    raw_markdown: str           # full markdown as returned by the provider

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    ok: bool
    language: str
    parser: str
    messages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
