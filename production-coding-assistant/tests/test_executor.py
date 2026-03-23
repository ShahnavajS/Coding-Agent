"""Tests for assistant_backend.core.executor"""
from __future__ import annotations

import pytest

from assistant_backend.core.executor import (
    extract_code_block,
    infer_target_path,
    should_execute,
)


class TestShouldExecute:
    @pytest.mark.parametrize("message", [
        "create a new file",
        "build a REST API",
        "write a function that sorts a list",
        "implement a binary search",
        "fix the bug in utils.py",
        "update the config",
        "generate a boilerplate class",
        "add error handling",
        "make a calculator",
    ])
    def test_returns_true_for_action_messages(self, message: str):
        assert should_execute(message) is True

    @pytest.mark.parametrize("message", [
        "what does this code do?",
        "explain the architecture",
        "show me the file list",
        "how does the planner work?",
    ])
    def test_returns_false_for_non_action_messages(self, message: str):
        assert should_execute(message) is False

    def test_case_insensitive(self):
        assert should_execute("CREATE a module") is True
        assert should_execute("BUILD the app") is True


class TestInferTargetPath:
    def test_extracts_explicit_py_filename(self):
        result = infer_target_path("create utils.py", {})
        assert result == "utils.py"

    def test_extracts_explicit_ts_filename(self):
        result = infer_target_path("update src/components/Button.tsx", {})
        assert result == "src/components/Button.tsx"

    def test_uses_active_file_on_edit_keyword(self):
        ctx = {"activeFilePath": "app/models.py"}
        result = infer_target_path("fix the bug here", ctx)
        assert result == "app/models.py"

    def test_returns_none_when_no_path_inferrable(self):
        result = infer_target_path("do something abstract", {})
        assert result is None

    def test_strips_leading_dot_slash(self):
        result = infer_target_path("edit ./main.py", {})
        assert result == "main.py"


class TestExtractCodeBlock:
    def test_extracts_python_block(self):
        text = "Here is the code:\n```python\nprint('hello')\n```"
        result = extract_code_block(text)
        assert result is not None
        assert "print('hello')" in result

    def test_extracts_plain_block(self):
        text = "```\nx = 1\n```"
        result = extract_code_block(text)
        assert result is not None
        assert "x = 1" in result

    def test_returns_none_when_no_block(self):
        result = extract_code_block("just some text, no code block here")
        assert result is None

    def test_trailing_newline_added(self):
        text = "```python\npass\n```"
        result = extract_code_block(text)
        assert result is not None
        assert result.endswith("\n")
