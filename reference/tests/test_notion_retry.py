"""Tests for Notion upload retry behavior in notes_poc."""

from __future__ import annotations

import httpx
import pytest

import notes.notion_uploader as notion_uploader
from notes.constants import NOTION_API_BASE
from notes.notion_uploader import upload_to_notion


def _set_notion_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTION_API_KEY", "test-key")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "test-parent")


def test_upload_to_notion_retries_once_then_succeeds_on_create(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_notion_env(monkeypatch)
    monkeypatch.setattr(notion_uploader, "md_to_notion_blocks", lambda _: [])

    calls: list[tuple[str, str]] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: int,
    ) -> httpx.Response:
        calls.append((method, url))
        req = httpx.Request(method, url)
        if len(calls) == 1:
            return httpx.Response(500, request=req, text="temporary error")
        return httpx.Response(
            200,
            request=req,
            json={"id": "page-123", "url": "https://notion.so/page-123"},
        )

    monkeypatch.setattr(httpx, "request", fake_request)

    url = upload_to_notion("label", "2026-04-02 00:00:00", "notes")

    assert url == "https://notion.so/page-123"
    assert calls == [
        ("POST", f"{NOTION_API_BASE}/pages"),
        ("POST", f"{NOTION_API_BASE}/pages"),
    ]


def test_upload_to_notion_does_not_retry_on_non_retryable_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_notion_env(monkeypatch)
    monkeypatch.setattr(notion_uploader, "md_to_notion_blocks", lambda _: [])

    calls = 0

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: int,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1
        req = httpx.Request(method, url)
        return httpx.Response(400, request=req, text="bad request")

    monkeypatch.setattr(httpx, "request", fake_request)

    with pytest.raises(httpx.HTTPStatusError):
        upload_to_notion("label", "2026-04-02 00:00:00", "notes")

    assert calls == 1


def test_upload_to_notion_429_uses_retry_after_before_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_notion_env(monkeypatch)
    monkeypatch.setattr(notion_uploader, "md_to_notion_blocks", lambda _: [])

    calls = 0
    slept: list[int] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: int,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1
        req = httpx.Request(method, url)
        if calls == 1:
            return httpx.Response(429, request=req, headers={"Retry-After": "2"}, text="rate limited")
        return httpx.Response(
            200,
            request=req,
            json={"id": "page-123", "url": "https://notion.so/page-123"},
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    monkeypatch.setattr(notion_uploader.time, "sleep", lambda sec: slept.append(sec))

    url = upload_to_notion("label", "2026-04-02 00:00:00", "notes")

    assert url == "https://notion.so/page-123"
    assert calls == 2
    assert slept == [2]
