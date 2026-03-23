"""Tests for assistant_backend.core.planner"""
from __future__ import annotations

import pytest

from assistant_backend.core.planner import create_plan


WORKSPACE_FILES = [
    "src/main.py",
    "src/utils.py",
    "README.md",
    "config.json",
]


class TestRiskClassification:
    def test_delete_keyword_gives_high_risk(self):
        plan = create_plan("delete the database file", WORKSPACE_FILES)
        assert plan.risk_level == "high"

    def test_remove_keyword_gives_high_risk(self):
        plan = create_plan("remove all log files", WORKSPACE_FILES)
        assert plan.risk_level == "high"

    def test_read_keyword_gives_low_risk(self):
        plan = create_plan("read the config file", WORKSPACE_FILES)
        assert plan.risk_level == "low"

    def test_explain_keyword_gives_low_risk(self):
        plan = create_plan("explain how main.py works", WORKSPACE_FILES)
        assert plan.risk_level == "low"

    def test_neutral_keyword_gives_medium_risk(self):
        plan = create_plan("add a new feature to main.py", WORKSPACE_FILES)
        assert plan.risk_level == "medium"


class TestFilesOfInterest:
    def test_matches_filename_in_message(self):
        plan = create_plan("update main.py with a new function", WORKSPACE_FILES)
        assert any("main.py" in f for f in plan.files_of_interest)

    def test_falls_back_to_first_three_files_when_no_match(self):
        plan = create_plan("do something unrelated", WORKSPACE_FILES)
        assert len(plan.files_of_interest) <= 3

    def test_empty_workspace_returns_empty_files(self):
        plan = create_plan("create a new file", [])
        assert plan.files_of_interest == []

    def test_at_most_five_files_returned(self):
        many_files = [f"file_{i}.py" for i in range(20)]
        plan = create_plan("update file_1 file_2 file_3 file_4 file_5 file_6", many_files)
        assert len(plan.files_of_interest) <= 5


class TestPlanStructure:
    def test_plan_has_steps(self):
        plan = create_plan("do something", WORKSPACE_FILES)
        assert len(plan.steps) >= 1

    def test_plan_has_summary(self):
        plan = create_plan("do something", WORKSPACE_FILES)
        assert plan.summary

    def test_plan_has_validation_plan(self):
        plan = create_plan("do something", WORKSPACE_FILES)
        assert isinstance(plan.validation_plan, list)
        assert len(plan.validation_plan) > 0

    def test_plan_to_dict_has_required_keys(self):
        plan = create_plan("do something", WORKSPACE_FILES)
        d = plan.to_dict()
        assert "summary" in d
        assert "riskLevel" in d
        assert "filesOfInterest" in d
        assert "steps" in d
