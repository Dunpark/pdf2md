"""notion_upload.py 동작 테스트 — httpx.MockTransport만 쓴다. 네트워크 없음 (CLAUDE.md §7).

토큰은 mineru_api 자체 점검과 같은 방식으로 env에 직접 주입한다.
sleep은 monkeypatch로 죽인다 — 요청 간 0.34s가 테스트를 느리게 만들면 안 된다.
"""

import json
import os
from pathlib import Path

import httpx
import pytest

import pdf2md.notion_upload as nu
from pdf2md.strict import NotionApiError, NotionDoc

os.environ["NOTION_API_KEY"] = "test-token"  # load_dotenv는 기존 env를 덮지 않는다

PAGE_ID = "3c402360b04780f7bcd9fe1ee0c87948"
PAGE_URL = f"https://www.notion.so/{PAGE_ID}"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """0.34s 간격·재시도 대기를 기록만 하고 실제로 자지 않는다."""
    slept: list[float] = []
    monkeypatch.setattr(nu.time, "sleep", slept.append)
    return slept


def make_doc(blocks, images=None) -> NotionDoc:
    return NotionDoc(blocks=blocks, images=images or [], citations=[],
                     ref_targets={}, warnings=[])


def para(text: str) -> dict:
    return {"type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def append_ok(request: httpx.Request) -> httpx.Response:
    """PATCH children을 받아 블록 수만큼 가짜 id를 돌려준다."""
    children = json.loads(request.content)["children"]
    return httpx.Response(200, json={
        "results": [{"id": f"id-{i}"} for i in range(len(children))]})


# ---- page_id_from_url ----

def test_page_id_accepts_known_shapes():
    dashed = "3c402360-b047-80f7-bcd9-fe1ee0c87948"
    for url in [
        PAGE_ID,                                                   # 맨 id
        dashed,                                                    # 대시 id
        f"https://www.notion.so/Attention-is-all-you-need-{PAGE_ID}?pvs=4",
        f"https://notion.so/{dashed}",                             # www 없음 + 대시
    ]:
        assert nu.page_id_from_url(url) == PAGE_ID


def test_page_id_rejects_garbage_with_expected_shape():
    with pytest.raises(NotionApiError) as e:
        nu.page_id_from_url("https://www.notion.so/My-Page")
    assert "32" in str(e.value)  # 기대 형태(32-hex)를 메시지로 보여준다


# ---- 배치 append ----

def test_250_blocks_appended_as_three_ordered_batches():
    doc = make_doc([para(f"b{i}") for i in range(250)])
    seen: list[list] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert f"/blocks/{PAGE_ID}/children" in str(request.url)
        seen.append(json.loads(request.content)["children"])
        return append_ok(request)

    url = nu.upload(doc, PAGE_URL, transport=httpx.MockTransport(handler))
    assert url == PAGE_URL
    assert [len(b) for b in seen] == [100, 100, 50]
    flat = [c["paragraph"]["rich_text"][0]["text"]["content"]
            for batch in seen for c in batch]
    assert flat == [f"b{i}" for i in range(250)]  # 문서 순서 보존


def test_batch_over_500kb_is_split_before_sending():
    # 5500자 문단 200개 → 100개 배치 하나가 ~560KB로 500KB를 넘는다
    doc = make_doc([para("x" * 5500) for _ in range(200)])
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sizes.append(len(request.content))
        return append_ok(request)

    nu.upload(doc, PAGE_URL, transport=httpx.MockTransport(handler))
    assert len(sizes) > 2  # 100+100 두 방이 아니라 더 잘게 나뉜다
    assert all(s <= 500_000 for s in sizes)


# ---- 이미지 2단계 업로드 ----

def test_image_two_step_upload_fills_placeholder(tmp_path):
    img = tmp_path / "fig.jpg"
    img.write_bytes(b"\xff\xd8fake-jpeg")
    image_block = {"type": "image",
                   "image": {"type": "file_upload", "file_upload": {"id": ""}}}
    doc = make_doc([para("before"), image_block], images=[(1, img)])
    steps: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/file_uploads") and request.method == "POST":
            steps.append("create")
            assert json.loads(request.content)["filename"] == "fig.jpg"
            return httpx.Response(200, json={"id": "fu-123"})
        if url.endswith("/file_uploads/fu-123/send"):
            steps.append("send")
            assert b'name="file"' in request.content  # multipart 필드명 file
            assert b"fake-jpeg" in request.content
            return httpx.Response(200, json={"id": "fu-123", "status": "uploaded"})
        if "/blocks/" in url:
            steps.append("append")
            children = json.loads(request.content)["children"]
            assert children[1]["image"]["file_upload"]["id"] == "fu-123"
            return append_ok(request)
        raise AssertionError(f"unexpected request: {url}")

    nu.upload(doc, PAGE_URL, transport=httpx.MockTransport(handler))
    assert steps == ["create", "send", "append"]


def test_image_over_20mb_halts_before_any_request(tmp_path):
    img = tmp_path / "big.png"
    with open(img, "wb") as f:
        f.truncate(20 * 1024 * 1024 + 1)  # sparse — 디스크는 안 먹는다
    doc = make_doc([{"type": "image",
                     "image": {"type": "file_upload", "file_upload": {"id": ""}}}],
                   images=[(0, img)])

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched")

    with pytest.raises(NotionApiError) as e:
        nu.upload(doc, PAGE_URL, transport=httpx.MockTransport(handler))
    assert "20MB" in str(e.value)


# ---- 재시도 정책 ----

def test_429_retries_once_honouring_retry_after(no_sleep):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return append_ok(request)

    nu.upload(make_doc([para("a")]), PAGE_URL, transport=httpx.MockTransport(handler))
    assert calls["n"] == 2
    assert 7.0 in no_sleep  # Retry-After를 실제로 기다렸다


def test_400_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"code": "validation_error", "message": "bad"})

    with pytest.raises(NotionApiError):
        nu.upload(make_doc([para("a")]), PAGE_URL, transport=httpx.MockTransport(handler))
    assert calls["n"] == 1


# ---- 부분 실패 보고 ----

def test_partial_failure_reports_exact_progress_and_deletes_nothing():
    doc = make_doc([para(f"b{i}") for i in range(250)])
    state = {"batch": 0, "deletes": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            state["deletes"] += 1
            return httpx.Response(200, json={})
        state["batch"] += 1
        if state["batch"] >= 2:  # 배치 2가 재시도까지 전부 5xx
            return httpx.Response(500)
        return append_ok(request)

    with pytest.raises(NotionApiError) as e:
        nu.upload(doc, PAGE_URL, transport=httpx.MockTransport(handler))
    msg = str(e.value)
    assert "appended 100 of 250 blocks" in msg
    assert "batch 2/3" in msg
    assert PAGE_URL in msg
    assert "delete them in Notion before rerunning, or accept duplicates" in msg
    assert state["deletes"] == 0  # 롤백하지 않는다


# ---- 기타 경계 ----

def test_empty_blocks_skip_network_entirely():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched")

    url = nu.upload(make_doc([]), PAGE_URL, transport=httpx.MockTransport(handler))
    assert url == PAGE_URL


def test_404_names_the_integration():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "object_not_found"})

    with pytest.raises(NotionApiError) as e:
        nu.upload(make_doc([para("a")]), PAGE_URL, transport=httpx.MockTransport(handler))
    assert "Automations" in str(e.value)  # 404는 "없음"과 "공유 안 됨"을 구분 못 한다


def test_count_children_paginates():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        if "start_cursor" not in str(request.url):
            return httpx.Response(200, json={
                "results": [{}] * 100, "has_more": True, "next_cursor": "c2"})
        return httpx.Response(200, json={
            "results": [{}] * 7, "has_more": False, "next_cursor": None})

    n = nu.count_children(PAGE_URL, transport=httpx.MockTransport(handler))
    assert n == 107


def test_missing_token_raises_before_network(monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.setattr(nu, "load_dotenv", lambda *a, **k: None)  # .env 탐색 차단

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched")

    with pytest.raises(NotionApiError) as e:
        nu.upload(make_doc([para("a")]), PAGE_URL, transport=httpx.MockTransport(handler))
    assert "NOTION_API_KEY" in str(e.value)


def test_httpx_exceptions_do_not_escape():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(NotionApiError) as e:
        nu.upload(make_doc([para("a")]), PAGE_URL, transport=httpx.MockTransport(handler))
    assert "boom" in str(e.value)


# ---- 인용 → 참조 블록 점프 링크 패치 (#19) ----

def make_cited_doc() -> NotionDoc:
    """블록 0: 본문 인용(rt 인덱스 1이 "18"), 블록 1: References 항목 [18]."""
    body = {"type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "text": {"content": "see ["}},
        {"type": "text", "text": {"content": "18"}},
        {"type": "text", "text": {"content": "]"}}]}}
    doc = make_doc([body, para("[18] Some Author. Some Paper.")])
    doc.citations.append((0, 1, "18"))
    doc.ref_targets["18"] = 1
    return doc


def cite_handler(patches: dict):
    """append는 정상 처리하고, 블록 단건 PATCH는 patches에 기록하는 핸들러."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "PATCH" and url.endswith("/children"):
            return append_ok(request)
        if request.method == "PATCH" and "/blocks/" in url:
            patches[url.rsplit("/", 1)[-1]] = json.loads(request.content)
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected request: {request.method} {url}")
    return handler


def test_citation_patch_links_to_target_block_id():
    patches: dict = {}
    url = nu.upload(make_cited_doc(), PAGE_URL,
                    transport=httpx.MockTransport(cite_handler(patches)))
    assert url == PAGE_URL
    assert list(patches) == ["id-0"]  # 인용이 있는 블록만 패치한다
    rt = patches["id-0"]["paragraph"]["rich_text"]
    # 앵커는 probe 실측 형태: …/{page_id}#{블록 id 대시 제거}. 참조 항목은 id-1
    assert rt[1]["text"]["link"]["url"] == f"https://www.notion.so/{PAGE_ID}#id1"
    assert rt[1]["text"]["content"] == "18"  # 텍스트는 그대로 — 링크만 단다
    assert "link" not in rt[0]["text"]  # 인용이 아닌 요소는 건드리지 않는다
    assert len(rt) == 3  # 전체 배열을 온전히 다시 보낸다


def test_two_citations_in_one_block_are_one_patch():
    doc = make_cited_doc()
    # 블록 0에 두 번째 인용 추가 (rt 인덱스 2를 "7"로 교체), 참조 항목 [7] 추가
    doc.blocks[0]["paragraph"]["rich_text"][2] = {
        "type": "text", "text": {"content": "7"}}
    doc.blocks.append(para("[7] Other Author."))
    doc.citations.append((0, 2, "7"))
    doc.ref_targets["7"] = 2
    patches: dict = {}
    nu.upload(doc, PAGE_URL, transport=httpx.MockTransport(cite_handler(patches)))
    assert list(patches) == ["id-0"]  # 블록당 한 번, 인용당 한 번이 아니다
    rt = patches["id-0"]["paragraph"]["rich_text"]
    assert rt[1]["text"]["link"]["url"].endswith("#id1")
    assert rt[2]["text"]["link"]["url"].endswith("#id2")


def test_patch_failure_warns_but_exit_stays_success(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "PATCH" and url.endswith("/children"):
            return append_ok(request)
        return httpx.Response(400, json={"code": "validation_error"})

    url = nu.upload(make_cited_doc(), PAGE_URL, transport=httpx.MockTransport(handler))
    assert url == PAGE_URL  # 패치 실패는 halt가 아니다 — 인용은 평문으로 읽힌다
    err = capsys.readouterr().err
    assert "notion:" in err and "citation" in err


def test_no_citations_means_no_patch_requests():
    doc = make_doc([para("plain text, no citations")])
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return append_ok(request)

    nu.upload(doc, PAGE_URL, transport=httpx.MockTransport(handler))
    assert all(u.endswith("/children") for u in calls)  # append 외 요청 없음


def test_citation_without_target_is_left_plain_with_warning(capsys):
    doc = make_cited_doc()
    doc.ref_targets.clear()  # 방어 경로 — #16이 보장하지만 침묵 손실은 안 된다
    patches: dict = {}
    nu.upload(doc, PAGE_URL, transport=httpx.MockTransport(cite_handler(patches)))
    assert patches == {}  # 링크할 대상이 없으면 패치도 없다
    assert "notion:" in capsys.readouterr().err


# ---- 페이지 제목 설정 (#25) ----

def titled_doc(title="Attention Is All You Need") -> NotionDoc:
    doc = make_doc([para("body")])
    doc.title = title
    return doc


def page_handler(existing_title: str, calls: dict):
    """GET/PATCH /pages/{id}를 기록하고, append는 정상 처리하는 핸들러."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/pages/" in url and request.method == "GET":
            calls["get"] = calls.get("get", 0) + 1
            rt = ([{"type": "text", "text": {"content": existing_title}}]
                  if existing_title else [])
            return httpx.Response(200, json={"properties": {"title": {"title": rt}}})
        if "/pages/" in url and request.method == "PATCH":
            calls["patch"] = json.loads(request.content)
            return httpx.Response(200, json={})
        if url.endswith("/children") and request.method == "PATCH":
            return append_ok(request)
        raise AssertionError(f"unexpected request: {request.method} {url}")
    return handler


def test_empty_page_title_is_set_with_prefix():
    calls: dict = {}
    nu.upload(titled_doc(), PAGE_URL, transport=httpx.MockTransport(page_handler("", calls)))
    got = calls["patch"]["properties"]["title"]["title"][0]["text"]["content"]
    assert got == "[\ub17c\ubb38] Attention Is All You Need"  # "[논문] " 접두


def test_existing_page_title_is_left_untouched(capsys):
    calls: dict = {}
    nu.upload(titled_doc(), PAGE_URL,
              transport=httpx.MockTransport(page_handler("My Manual Title", calls)))
    assert "patch" not in calls  # 사용자가 지정한 제목을 덮지 않는다
    assert "notion:" in capsys.readouterr().err


def test_doc_without_title_makes_no_page_requests():
    calls: dict = {}
    nu.upload(titled_doc(title=""), PAGE_URL,
              transport=httpx.MockTransport(page_handler("", calls)))
    assert calls == {}  # h1이 없으면 /pages는 아예 건드리지 않는다


# ---------- 전송 오류 재시도 (#46, CLAUDE.md §11.25) ----------

def test_transport_error_retries_once(no_sleep):
    # 실측 2회: 180블록+이미지를 올리는 1분 사이 한 번 끊기면 전량 실패였다.
    # #46로 인용 패치가 늘어 업로드가 두 배로 길어졌으므로 더 자주 걸린다.
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("connection reset")
        return append_ok(request)

    nu.upload(make_doc([para("a")]), PAGE_URL, transport=httpx.MockTransport(handler))
    assert calls["n"] == 2


def test_transport_error_twice_still_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset")

    with pytest.raises(NotionApiError):
        nu.upload(make_doc([para("a")]), PAGE_URL, transport=httpx.MockTransport(handler))
