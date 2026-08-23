"""Notion 업로드 — HTTP만 담당한다 (#17).

upload(doc, page_url) -> 페이지 URL. 이미지 2단계 업로드 → 100개 배치 append.
내용 때문에 실패할 일은 없어야 한다 — 모든 한도 검사는 to_blocks(#16)가 이미
끝냈고, 여기 남는 실패는 네트워크·권한·429뿐이다 (PLAN.md Notion 경로).

실패 정책: 롤백하지 않고 정확히 보고한다. DELETE 롤백은 그 자체가 N개의 새
요청이고 역시 중간에 실패하며, 무엇보다 사용자의 기존 페이지에 대고 지우는
동작이다 — 우리 블록이라는 근거가 append 응답 id인데 그 응답을 못 받은 것이
바로 실패 상황이다.

strict 외에는 프로젝트 안의 무엇도 임포트하지 않는다 (PLAN.md "파일 구조").
런타임 메시지는 전부 ASCII 영어 — cp949 콘솔 (CLAUDE.md 함정 8).
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from pdf2md.strict import NotionApiError, NotionDoc

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"  # PLAN.md 부록에서 동작 확인
MAX_BLOCKS_PER_REQUEST = 100
MAX_REQUEST_BYTES = 500_000
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # File Upload API 단일 파트 한도
REQUEST_INTERVAL = 0.34  # 평균 3 req/s 아래로 — 429를 만드는 것보다 싸다

_HEX32_RE = re.compile(r"[0-9a-f]{32}$")

_404_HINT = (
    "page not found, or not shared with the integration. "
    "Share the page with the `Automations` integration and retry."
)


def page_id_from_url(url: str) -> str:
    """Notion 페이지 URL 또는 id에서 32-hex page id를 뽑는다.

    수용: 맨 32-hex id, 대시 낀 id, 제목 슬러그 접두, ?pvs=4 꼬리, www. 유무.
    """
    tail = url.strip().split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    compact = tail.replace("-", "").lower()
    m = _HEX32_RE.search(compact)
    if not m or len(compact) < 32:
        raise NotionApiError(
            f"cannot find a page id in {url!r} - expected a Notion page URL "
            "ending in a 32-hex id, e.g. https://www.notion.so/Title-<32 hex chars>"
        )
    return m.group(0)


def count_children(page_url: str, *, transport: httpx.BaseTransport | None = None) -> int:
    """대상 페이지의 기존 1단계 자식 수 — 중복 안내(#18)가 upload 전에 부른다."""
    page_id = page_id_from_url(page_url)
    headers = _headers()
    try:
        with httpx.Client(timeout=60.0, transport=transport) as client:
            n, cursor = 0, None
            while True:
                params = {"page_size": 100}
                if cursor:
                    params["start_cursor"] = cursor
                data = _send(client, "GET", f"{BASE_URL}/blocks/{page_id}/children",
                             headers, "list children", params=params)
                n += len(data.get("results", []))
                if not data.get("has_more"):
                    return n
                cursor = data.get("next_cursor")
    except httpx.HTTPError as e:
        # httpx 예외는 여기서 끝난다 — 호출자는 NotionApiError만 본다 (CLAUDE.md §7)
        raise NotionApiError(f"Notion request failed: {type(e).__name__}: {e}") from e


def upload(doc: NotionDoc, page_url: str, *, transport: httpx.BaseTransport | None = None) -> str:
    """NotionDoc을 페이지에 append하고 페이지 URL을 돌려준다.

    순서: 이미지 2단계 업로드(placeholder id 채움) → 100개 배치 append →
    인용 링크 패치(#19). transport 는 테스트 주입구 — 실전에서는 넘기지 않는다.
    """
    page_id = page_id_from_url(page_url)
    result_url = f"https://www.notion.so/{page_id}"
    if not doc.blocks:
        return result_url  # 보낼 것이 없으면 네트워크를 건드리지 않는다

    # 20MB 검사는 네트워크 이전에 전부 끝낸다 — 반쪽 업로드를 만들지 않는다
    for _, img_path in doc.images:
        size = Path(img_path).stat().st_size
        if size > MAX_IMAGE_BYTES:
            raise NotionApiError(
                f"image exceeds the 20MB upload limit ({size} bytes): {img_path}"
            )

    headers = _headers()
    batches = _split_batches(doc.blocks)
    try:
        with httpx.Client(timeout=60.0, transport=transport) as client:
            # 1) 이미지 2단계 업로드 — id는 1시간 만료라 캐시하지 않는다
            for block_idx, img_path in doc.images:
                fid = _upload_image(client, headers, Path(img_path))
                doc.blocks[block_idx]["image"]["file_upload"]["id"] = fid

            # 2) 배치 append — 응답 results의 id를 문서 순서대로 모은다
            block_ids: list[str] = []
            for i, batch in enumerate(batches):
                try:
                    data = _send(client, "PATCH",
                                 f"{BASE_URL}/blocks/{page_id}/children",
                                 headers, f"append batch {i + 1}",
                                 json={"children": batch})
                except NotionApiError as e:
                    raise NotionApiError(
                        f"appended {len(block_ids)} of {len(doc.blocks)} "
                        f"blocks before failing at batch {i + 1}/{len(batches)}: {e} "
                        f"Page: {result_url} - "
                        "delete them in Notion before rerunning, or accept duplicates."
                    ) from e
                block_ids.extend(b["id"] for b in data.get("results", []))

            # 3) 인용 → 참조 블록 점프 링크 (#19). 실패해도 업로드는 이미 성공 —
            #    인용은 평문 [N]으로 읽히므로 경고만 내고 계속 간다
            _patch_citations(client, headers, doc, page_id, block_ids)
    except httpx.HTTPError as e:
        raise NotionApiError(f"Notion request failed: {type(e).__name__}: {e}") from e
    return result_url


# ---- 내부 ----

def _warn(msg: str) -> None:
    """CLI의 `notion: …` 관례와 같은 무늬로 stderr에 낸다.

    # ponytail: HTTP 모듈이 직접 stderr를 쓴다 — upload의 시그니처(-> str)가
    # 계약으로 고정돼 경고를 반환할 자리가 없다. 채널이 더 필요해지면 그때 뚫는다.
    """
    print(f"notion: {msg}", file=sys.stderr)


def _patch_citations(client: httpx.Client, headers: dict, doc: NotionDoc,
                     page_id: str, block_ids: list[str]) -> None:
    """본문 인용 [N]에 References 블록으로 가는 앵커 링크를 단다 (#19).

    앵커 형태는 probe 실측(2026-08-23): …/{page_id}#{블록 id 대시 제거}.
    블록당 PATCH 한 번 — 전체 rich_text 배열을 링크 단 채로 다시 보낸다.
    어떤 실패도 halt가 아니다: 인용 텍스트는 어느 쪽이든 살아 있다.
    """
    if not doc.citations:
        return

    by_block: dict[int, list[tuple[int, str]]] = {}
    for block_idx, rt_idx, num in doc.citations:
        by_block.setdefault(block_idx, []).append((rt_idx, num))

    failed = 0
    for block_idx, cites in sorted(by_block.items()):
        block = doc.blocks[block_idx]
        btype = block["type"]
        rich = block.get(btype, {}).get("rich_text")
        if rich is None:  # 방어 — 인용은 텍스트 블록에서만 온다 (#16이 보장)
            _warn(f"citation in a {btype} block cannot be patched; left plain")
            continue
        linked = 0
        for rt_idx, num in cites:
            target = doc.ref_targets.get(num)
            if target is None or target >= len(block_ids):
                _warn(f"citation [{num}] has no reference block; left plain")
                continue
            anchor = (f"https://www.notion.so/{page_id}"
                      f"#{block_ids[target].replace('-', '')}")
            rich[rt_idx]["text"]["link"] = {"url": anchor}
            linked += 1
        if not linked:
            continue
        try:
            _send(client, "PATCH", f"{BASE_URL}/blocks/{block_ids[block_idx]}",
                  headers, f"citation link patch (block {block_idx})",
                  json={btype: {"rich_text": rich}})
        except (NotionApiError, httpx.HTTPError):
            failed += 1
    if failed:
        _warn(f"citation link patch failed for {failed} block(s); "
              "those citations stay readable plain text")

def _headers() -> dict[str, str]:
    """토큰은 여기서 lazy하게 읽는다 — .env 없는 worktree에서 임포트가 죽으면 안 된다."""
    load_dotenv()  # 이미 설정된 env는 덮지 않는다
    token = os.environ.get("NOTION_API_KEY", "").strip()
    if not token:
        raise NotionApiError(
            "NOTION_API_KEY is missing. Put it in .env "
            "(create an integration at notion.so/my-integrations)"
        )
    return {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}


def _split_batches(blocks: list[dict]) -> list[list[dict]]:
    """100개씩 자르고, 직렬화가 500KB를 넘는 조각은 반으로 계속 쪼갠다."""
    out: list[list[dict]] = []

    def halve(chunk: list[dict]) -> None:
        if len(chunk) <= 1 or len(json.dumps(chunk).encode()) <= MAX_REQUEST_BYTES:
            out.append(chunk)
            return
        mid = len(chunk) // 2
        halve(chunk[:mid])
        halve(chunk[mid:])

    for i in range(0, len(blocks), MAX_BLOCKS_PER_REQUEST):
        halve(blocks[i:i + MAX_BLOCKS_PER_REQUEST])
    return out


def _upload_image(client: httpx.Client, headers: dict, img_path: Path) -> str:
    """File Upload 2단계: 생성 → multipart 전송(필드명 file). file_upload id를 돌려준다."""
    ctype = mimetypes.guess_type(img_path.name)[0] or "application/octet-stream"
    data = _send(client, "POST", f"{BASE_URL}/file_uploads", headers,
                 f"file_uploads create ({img_path.name})",
                 json={"filename": img_path.name, "content_type": ctype})
    fid = data.get("id")
    if not fid:
        raise NotionApiError(f"file_uploads response has no id: {data!r}")
    _send(client, "POST", f"{BASE_URL}/file_uploads/{fid}/send", headers,
          f"file_uploads send ({img_path.name})",
          files={"file": (img_path.name, img_path.read_bytes(), ctype)})
    return fid


def _send(client: httpx.Client, method: str, url: str, headers: dict,
          step: str, **kw) -> dict:
    """요청 간격 유지 + 429/5xx 1회 재시도 + 오류를 NotionApiError로 변환."""
    time.sleep(REQUEST_INTERVAL)
    resp = client.request(method, url, headers=headers, **kw)
    if resp.status_code == 429 or resp.status_code >= 500:
        # ponytail: Retry-After를 초 단위 숫자로만 해석한다. HTTP-date 형식이
        # 실제로 나타나면 그때 파싱을 더한다.
        try:
            wait = float(resp.headers.get("Retry-After", "1"))
        except ValueError:
            wait = 1.0
        time.sleep(wait)
        resp = client.request(method, url, headers=headers, **kw)

    if resp.status_code == 404:
        raise NotionApiError(f"{step}: HTTP 404 - {_404_HINT}")
    if resp.status_code != 200:
        raise NotionApiError(f"{step}: HTTP {resp.status_code} - {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as e:
        raise NotionApiError(f"{step}: non-JSON response - {resp.text[:200]}") from e
