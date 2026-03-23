from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class RiskLevel:
    """Constants for plan risk levels. Use these instead of raw strings."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StepStatus:
    """Constants for plan step statuses."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PlanStep:
    id: str
    name: str
    status: str          # Use StepStatus constants
    description: str
    details: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    summary: str
    risk_level: str      # Use RiskLevel constants
    files_of_interest: list[str] = field(default_factory=list)
    validation_plan: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "riskLevel": self.risk_level,
            "filesOfInterest": self.files_of_interest,
            "validationPlan": self.validation_plan,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class ValidationResult:
    ok: bool
    language: str
    parser: str
    messages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
