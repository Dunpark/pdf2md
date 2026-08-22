from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

NOTION_API_BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
_MAX_RETRY_AFTER_SECONDS = 5.0
_MAX_REQUEST_BYTES = 500 * 1024
_MAX_RICH_TEXT_CHARS = 2000
_ALLOWED_PROVIDER_ERROR_CODES = {
    "invalid_grant",
    "invalid_client",
    "test_env_error",
    "internal_server_error",
    "invalid_json",
    "invalid_request_url",
    "invalid_request",
    "validation_error",
    "missing_version",
    "invalid_beta",
    "unauthorized",
    "restricted_resource",
    "object_not_found",
    "conflict_error",
    "rate_limited",
    "service_overload",
    "bad_gateway",
    "service_unavailable",
    "database_connection_unavailable",
    "gateway_timeout",
}


@dataclass(frozen=True)
class NotionOAuthToken:
    access_token: str
    refresh_token: str
    bot_id: str
    workspace_id: str
    workspace_name: str | None
    expires_at: int | None
    duplicated_template_id: str | None = None


@dataclass(frozen=True)
class NotionPage:
    id: str
    url: str
    title: str


class NotionAPIError(Exception):
    def __init__(self, status_code: int, category: str) -> None:
        super().__init__(f"Notion API error {status_code}: {category}")
        self.status_code = status_code
        self.category = category


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return f"Basic {encoded}"


def _json_size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _validate_title(title: str) -> None:
    if not title.strip():
        raise NotionAPIError(400, "validation_error")
    if len(title) > _MAX_RICH_TEXT_CHARS:
        raise NotionAPIError(400, "validation_error")


def _validate_payload(payload: dict[str, Any]) -> None:
    if _json_size(payload) > _MAX_REQUEST_BYTES:
        raise NotionAPIError(400, "validation_error")


def _title_property(title: str) -> dict[str, Any]:
    _validate_title(title)
    return {"title": {"title": [{"type": "text", "text": {"content": title}}]}}


def _category_for_status(status_code: int) -> str:
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not_found"
    if status_code == 429:
        return "rate_limited"
    if status_code == 529:
        return "service_overload"
    if 500 <= status_code:
        return "provider_unavailable"
    return "request_failed"


def _category_for_response(response: httpx.Response) -> str:
    fallback = _category_for_status(response.status_code)
    try:
        data = response.json()
    except ValueError:
        return fallback
    if not isinstance(data, dict):
        return fallback
    code = data.get("code")
    if isinstance(code, str) and code in _ALLOWED_PROVIDER_ERROR_CODES:
        return code
    return fallback


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def safe_notion_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = parsed.hostname.lower() if parsed.hostname else ""
    if parsed.scheme != "https":
        return None
    if host in {"notion.com", "notion.so", "notion.site"}:
        return url
    if host.endswith((".notion.com", ".notion.so", ".notion.site")):
        return url
    return None


async def _post_json(
    path: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    retry: bool = True,
) -> dict[str, Any]:
    request_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
        **headers,
    }
    url = f"{NOTION_API_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=request_headers, json=payload)
        except httpx.TransportError as exc:
            raise NotionAPIError(502, "transport_error") from exc
        if response.status_code in (429, 529) and retry:
            delay = _retry_after_seconds(response)
            if delay is not None and delay <= _MAX_RETRY_AFTER_SECONDS:
                await asyncio.sleep(delay)
                try:
                    response = await client.post(url, headers=request_headers, json=payload)
                except httpx.TransportError as exc:
                    raise NotionAPIError(502, "transport_error") from exc

    if response.status_code >= 400:
        raise NotionAPIError(response.status_code, _category_for_response(response))
    try:
        data = response.json()
    except ValueError as exc:
        raise NotionAPIError(502, "invalid_response") from exc
    if not isinstance(data, dict):
        raise NotionAPIError(502, "invalid_response")
    return data


def _parse_token(data: dict[str, Any], fallback_refresh_token: str | None = None) -> NotionOAuthToken:
    refresh_token = data.get("refresh_token") or fallback_refresh_token
    access_token = data.get("access_token")
    bot_id = data.get("bot_id")
    workspace_id = data.get("workspace_id")
    if not all(isinstance(value, str) and value for value in (access_token, refresh_token, bot_id, workspace_id)):
        raise NotionAPIError(502, "invalid_token_response")
    return NotionOAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        bot_id=bot_id,
        workspace_id=workspace_id,
        workspace_name=data.get("workspace_name"),
        expires_at=data.get("expires_at"),
        duplicated_template_id=(
            data.get("duplicated_template_id")
            if isinstance(data.get("duplicated_template_id"), str)
            else None
        ),
    )


def _parse_page(data: dict[str, Any], title: str) -> NotionPage:
    page_id = data.get("id")
    url = safe_notion_url(data.get("url") if isinstance(data.get("url"), str) else None)
    if not all(isinstance(value, str) and value for value in (page_id, url)):
        raise NotionAPIError(502, "invalid_page_response")
    return NotionPage(id=page_id, url=url, title=title)


def _page_title(data: dict[str, Any]) -> str | None:
    properties = data.get("properties")
    if not isinstance(properties, dict):
        return None
    for property_data in properties.values():
        if not isinstance(property_data, dict):
            continue
        title = property_data.get("title")
        if not isinstance(title, list):
            continue
        value = "".join(
            item.get("plain_text")
            for item in title
            if isinstance(item, dict) and isinstance(item.get("plain_text"), str)
        ).strip()
        if value:
            return value
    return None


async def exchange_notion_code(
    code: str, redirect_uri: str, client_id: str, client_secret: str
) -> NotionOAuthToken:
    data = await _post_json(
        "/oauth/token",
        headers={"Authorization": _basic_auth_header(client_id, client_secret)},
        payload={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        retry=False,
    )
    return _parse_token(data)


async def refresh_notion_token(
    refresh_token: str, client_id: str, client_secret: str
) -> NotionOAuthToken:
    data = await _post_json(
        "/oauth/token",
        headers={"Authorization": _basic_auth_header(client_id, client_secret)},
        payload={"grant_type": "refresh_token", "refresh_token": refresh_token},
        retry=False,
    )
    return _parse_token(data, fallback_refresh_token=refresh_token)


async def find_page_by_title(access_token: str, title: str) -> NotionPage | None:
    payload = {
        "query": title,
        "page_size": 100,
        "filter": {"property": "object", "value": "page"},
    }
    _validate_payload(payload)
    data = await _post_json(
        "/search",
        headers={"Authorization": f"Bearer {access_token}"},
        payload=payload,
    )
    results = data.get("results")
    if not isinstance(results, list):
        raise NotionAPIError(502, "invalid_search_response")
    for result in results:
        if not isinstance(result, dict):
            continue
        result_title = _page_title(result)
        if result_title and result_title.casefold() == title.strip().casefold():
            return _parse_page(result, result_title)
    return None


async def create_workspace_page(access_token: str, title: str) -> NotionPage:
    payload = {
        "parent": {"type": "workspace", "workspace": True},
        "properties": _title_property(title),
    }
    _validate_payload(payload)
    data = await _post_json(
        "/pages",
        headers={"Authorization": f"Bearer {access_token}"},
        payload=payload,
    )
    return _parse_page(data, title)


async def create_child_page(
    access_token: str, parent_page_id: str, title: str, markdown: str
) -> NotionPage:
    payload = {
        "parent": {"page_id": parent_page_id},
        "properties": _title_property(title),
        "markdown": markdown,
    }
    _validate_payload(payload)
    data = await _post_json(
        "/pages",
        headers={"Authorization": f"Bearer {access_token}"},
        payload=payload,
    )
    return _parse_page(data, title)
