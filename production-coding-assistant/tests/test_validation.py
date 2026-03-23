"""Tests for assistant_backend.validation.parser_checks"""
from __future__ import annotations

import pytest

from assistant_backend.validation.parser_checks import detect_language, validate_content


class TestDetectLanguage:
    @pytest.mark.parametrize("path,expected", [
        ("main.py", "python"),
        ("src/utils.ts", "typescript"),
        ("components/Button.tsx", "typescript"),
        ("app.js", "javascript"),
        ("index.jsx", "javascript"),
        ("config.json", "json"),
        ("README.md", "markdown"),
        ("styles.css", "css"),
        ("index.html", "html"),
        ("notes.txt", "text"),
        ("Makefile", "text"),
    ])
    def test_extension_mapping(self, path: str, expected: str):
        assert detect_language(path) == expected

    def test_case_insensitive_extension(self):
        assert detect_language("SCRIPT.PY") == "python"


class TestValidateContent:
    def test_valid_python_passes(self):
        result = validate_content("main.py", "x = 1\nprint(x)\n")
        assert result.ok is True
        assert result.language == "python"
        assert result.parser == "ast"

    def test_invalid_python_fails(self):
        result = validate_content("main.py", "def broken(\n")
        assert result.ok is False
        assert any("SyntaxError" in m for m in result.messages)

    def test_valid_json_passes(self):
        result = validate_content("config.json", '{"key": "value"}')
        assert result.ok is True
        assert result.language == "json"

    def test_invalid_json_fails(self):
        result = validate_content("config.json", '{key: value}')
        assert result.ok is False
        assert any("JSONDecodeError" in m for m in result.messages)

    def test_empty_content_fails(self):
        result = validate_content("main.py", "   ")
        assert result.ok is False
        assert any("empty" in m.lower() for m in result.messages)

    def test_unknown_language_passes_through(self):
        result = validate_content("notes.txt", "hello world")
        assert result.ok is True
        assert result.language == "text"

    def test_result_to_dict_has_required_keys(self):
        result = validate_content("main.py", "pass\n")
        d = result.to_dict()
        assert "ok" in d
        assert "language" in d
        assert "parser" in d
        assert "messages" in d
