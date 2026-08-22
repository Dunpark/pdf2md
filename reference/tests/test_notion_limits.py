"""Tests for Notion field length limits in notes_poc."""

from __future__ import annotations

from notes.notion_parser import _eq


def test_equation_expression_is_trimmed_to_notion_limit() -> None:
    expr = "x" * 1200
    item = _eq(expr)
    assert item["type"] == "equation"
    assert len(item["equation"]["expression"]) == 1000

