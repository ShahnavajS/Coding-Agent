from __future__ import annotations

from assistant_backend.api.app import create_app
import assistant_backend.core.orchestrator as orchestrator


class FakeProviderResponse:
    def __init__(self, content: str, provider: str = "groq", model: str = "fake-model"):
        self.content = content
        self.provider = provider
        self.model = model


def test_run_agent_mode_uses_web_search_before_generation(monkeypatch):
    message = "make one calculator for me using current best practices"

    provider_responses = iter(
        [
            FakeProviderResponse(
                '{"tool":"web_search","query":"python calculator project structure best practices","num_results":3}'
            ),
            FakeProviderResponse(
                """project/
|-- README.md
|-- app.py
|-- calculator.py
|-- cli.py
|-- operations.py
`-- tests
    `-- test_calculator.py
FILE: app.py
from cli import main

if __name__ == "__main__":
    main()

FILE: calculator.py
from operations import add, divide, multiply, subtract


def calculate(operation: str, left: float, right: float) -> float:
    if operation == "+":
        return add(left, right)
    if operation == "-":
        return subtract(left, right)
    if operation == "*":
        return multiply(left, right)
    if operation == "/":
        return divide(left, right)
    raise ValueError("Unsupported operation")

FILE: operations.py
def add(left: float, right: float) -> float:
    return left + right


def subtract(left: float, right: float) -> float:
    return left - right


def multiply(left: float, right: float) -> float:
    return left * right


def divide(left: float, right: float) -> float:
    if right == 0:
        raise ValueError("Cannot divide by zero")
    return left / right

FILE: cli.py
from calculator import calculate


def main() -> None:
    print("Simple Calculator")
    operation = input("Operation (+, -, *, /): ").strip()
    left = float(input("Left operand: "))
    right = float(input("Right operand: "))
    print(calculate(operation, left, right))

FILE: tests/test_calculator.py
from calculator import calculate


def test_add() -> None:
    assert calculate("+", 2, 3) == 5

FILE: README.md
# Calculator

Simple multi-file calculator example.
"""
            ),
        ]
    )
    tool_calls: list[dict[str, object]] = []

    monkeypatch.setattr(orchestrator, "list_files_flat", lambda: [])
    monkeypatch.setattr(orchestrator, "generate_with_provider", lambda prompt, provider_name=None: next(provider_responses))
    monkeypatch.setattr(
        orchestrator,
        "run_tool",
        lambda name, **kwargs: tool_calls.append({"name": name, **kwargs}) or [
            {
                "title": "Python calculator tutorial",
                "link": "https://example.com/python-calculator",
                "snippet": "Create a modular calculator with separate CLI and operation modules.",
                "source": "example.com",
                "published_at": "2026-03-01",
            }
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "write_generated_files",
        lambda files, summary: {
            "filesModified": [item["path"] for item in files],
            "checkpoints": [],
        },
    )

    result = orchestrator.run_agent_mode(message, "session-1", {}, "groq")

    assert tool_calls
    assert tool_calls[0]["name"] == "web_search"
    assert "calculator.py" in result["filesModified"]
    assert "README.md" in result["filesModified"]
    assert result["providerStatus"]["provider"] == "groq"


def test_search_test_endpoint(monkeypatch):
    monkeypatch.setattr(
        "assistant_backend.api.app.web_search",
        lambda query, num_results=5, provider=None, session_id=None: [
            {
                "title": "FastAPI guide",
                "link": "https://example.com/fastapi",
                "snippet": "Use async endpoints and pydantic settings.",
                "source": "example.com",
                "published_at": "2026-03-01",
            }
        ],
    )

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/agent/search-test",
        json={"query": "latest FastAPI best practices", "numResults": 3},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["results"][0]["title"] == "FastAPI guide"
