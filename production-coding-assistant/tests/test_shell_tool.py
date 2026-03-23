"""Tests for assistant_backend.tools.shell_tool"""
from __future__ import annotations

import pytest

from assistant_backend.tools.shell_tool import classify_command


class TestClassifyCommand:
    @pytest.mark.parametrize("command", [
        "rm -rf /",
        "del /f /q .",
        "git commit -m 'test'",
        "npm install",
        "pip install requests",
        "curl https://example.com",
        "wget https://example.com/file.zip",
    ])
    def test_dangerous_commands_require_review(self, command: str):
        assert classify_command(command) == "review"

    @pytest.mark.parametrize("command", [
        "python main.py",
        "echo hello",
        "ls -la",
        "cat README.md",
        "python -m pytest",
    ])
    def test_safe_commands_are_classified_safe(self, command: str):
        assert classify_command(command) == "safe"

    def test_empty_string_is_safe(self):
        assert classify_command("") == "safe"

    def test_malformed_command_requires_review(self):
        # Unbalanced quotes cannot be parsed by shlex and fall back to "review"
        assert classify_command("echo 'unclosed") == "review"

    def test_case_insensitive_detection(self):
        assert classify_command("RM -rf /tmp") == "review"
        assert classify_command("GIT status") == "review"
