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
    AGENT    = "agent"     # default: generate + execute code
    PLAN     = "plan"      # research + produce a structured plan, no code execution
    ASK      = "ask"       # conversational Q&A, no code execution
    EDIT     = "edit"      # targeted patch: modify specific parts of existing files
    DECOMPOSE = "decompose" # break the task into subtasks, return without executing


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
    # Snippets of existing files read before generation for codebase awareness
    file_snippets: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary":          self.summary,
            "riskLevel":        self.risk_level,
            "filesOfInterest":  self.files_of_interest,
            "expectedFiles":    self.expected_files,
            "expectedFileCount": self.expected_file_count,
            "projectStructure": self.project_structure,
            "validationPlan":   self.validation_plan,
            "steps":            [s.to_dict() for s in self.steps],
            # file_snippets intentionally omitted from the wire format (large)
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
class ContextSnapshot:
    """Rich context injected into agent prompts for codebase awareness."""
    active_file_path: str
    active_file_content: str        # content of the currently open file (truncated)
    file_snippets: dict[str, str]   # other relevant files {path: snippet}
    recent_messages: list[dict[str, str]]  # last N messages [{role, content}]
    selected_text: str

    def to_prompt_block(self) -> str:
        """Render the snapshot as a structured string to inject into prompts."""
        parts: list[str] = []
        if self.recent_messages:
            history_lines = []
            for msg in self.recent_messages:
                role_label = "User" if msg["role"] == "user" else "Assistant"
                text = msg["content"][:400].strip()
                history_lines.append(f"{role_label}: {text}")
            parts.append("Recent conversation history:\n" + "\n".join(history_lines))
        if self.active_file_content:
            parts.append(
                f"Currently open file ({self.active_file_path}):\n"
                f"{self.active_file_content[:2000]}"
            )
        if self.file_snippets:
            snippet_lines = []
            for path, content in list(self.file_snippets.items())[:5]:
                snippet_lines.append(f"--- {path} ---\n{content[:800]}")
            parts.append("Related files in workspace:\n" + "\n\n".join(snippet_lines))
        if self.selected_text:
            parts.append(f"Selected text in editor:\n{self.selected_text[:800]}")
        return "\n\n".join(parts)


@dataclass
class ValidationResult:
    ok: bool
    language: str
    parser: str
    messages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
