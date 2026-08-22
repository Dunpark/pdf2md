"""
notes/notion_uploader.py — upload notes to Notion pages.
"""

import os
import time

import httpx

from notes.constants import (
    NOTION_API_BASE,
    NOTION_MAX_RETRIES,
    NOTION_VERSION,
    _NOTION_BATCH,
)
from notes.notion_parser import md_to_notion_blocks


def upload_to_notion(label: str, generated: str, notes: str) -> str:
    """Create a Notion page from markdown notes. Returns the page URL."""
    api_key = os.getenv("NOTION_API_KEY")
    parent_id = os.getenv("NOTION_PARENT_PAGE_ID")
    if not api_key:
        raise EnvironmentError("NOTION_API_KEY is not set.")
    if not parent_id:
        raise EnvironmentError("NOTION_PARENT_PAGE_ID is not set.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
        "User-Agent": "Mozilla/5.0 (compatible; notetaker/1.0)",
    }

    blocks = md_to_notion_blocks(notes)
    first_batch = blocks[:_NOTION_BATCH]
    rest = blocks[_NOTION_BATCH:]

    def _notion_request_with_retry(method: str, url: str, payload: dict, action: str) -> httpx.Response:
        for attempt in range(NOTION_MAX_RETRIES + 1):
            try:
                resp = httpx.request(
                    method,
                    url,
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                if resp.is_error:
                    is_retryable = resp.status_code == 429 or resp.status_code >= 500
                    if is_retryable and attempt < NOTION_MAX_RETRIES:
                        if resp.status_code == 429:
                            retry_after = resp.headers.get("Retry-After", "").strip()
                            try:
                                wait_seconds = max(0, int(retry_after))
                            except ValueError:
                                wait_seconds = 1
                            print(
                                f"  Notion {action} rate-limited (429), waiting {wait_seconds}s before retry... "
                                f"({attempt + 1}/{NOTION_MAX_RETRIES})"
                            )
                            time.sleep(wait_seconds)
                            continue
                        print(
                            f"  Notion {action} failed ({resp.status_code}), retrying... "
                            f"({attempt + 1}/{NOTION_MAX_RETRIES})"
                        )
                        continue
                    raise httpx.HTTPStatusError(
                        f"{resp.status_code}: {resp.text}",
                        request=resp.request,
                        response=resp,
                    )
                return resp
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt < NOTION_MAX_RETRIES:
                    print(f"  Notion {action} timeout/network error, retrying... ({attempt + 1}/{NOTION_MAX_RETRIES})")
                    continue
                raise
        raise RuntimeError("Unreachable: retry loop must return or raise.")

    resp = _notion_request_with_retry(
        "POST",
        f"{NOTION_API_BASE}/pages",
        {
            "parent": {"type": "page_id", "page_id": parent_id},
            "properties": {
                "title": {"title": [{"text": {"content": f"{label} — {generated}"}}]}
            },
            "children": first_batch,
        },
        "page creation",
    )
    page = resp.json()
    page_id = page["id"]

    while rest:
        batch, rest = rest[:_NOTION_BATCH], rest[_NOTION_BATCH:]
        _notion_request_with_retry(
            "PATCH",
            f"{NOTION_API_BASE}/blocks/{page_id}/children",
            {"children": batch},
            "block append",
        )

    return page["url"]
