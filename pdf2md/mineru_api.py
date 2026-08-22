"""MinerU v4 Precise API 클라이언트 — 네트워크만 담당한다 (#3).

fetch_zip(pdf_path) -> bytes : 업로드 → 폴링 → 결과 ZIP 바이트를 돌려준다.
캐시도 압축해제도 output/ 도 모른다 (PLAN.md "파일 구조").
strict 외에는 프로젝트 안의 무엇도 임포트하지 않는다.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from pdf2md.strict import MineruApiError

BASE_URL = "https://mineru.net/api/v4"
MAX_FILE_BYTES = 200 * 1024 * 1024  # 공식 한도 200MB (PLAN.md "사실 확인 결과")

# 401은 만료부터 의심한다 — 토큰 유효기간 14일, 자동 갱신 없음 (PLAN.md)
_EXPIRY_HINT = (
    "토큰이 만료됐을 수 있다(유효기간 14일, 자동 갱신 없음). "
    "mineru.net/apiManage/token 에서 재발급할 것"
)
# 사전 페이지 수 검사는 불가능하므로(이슈 #3 Design Decisions) 거부 응답에 힌트만 붙인다
_LIMIT_HINT = "200페이지·200MB 한도 초과일 수 있다"


def fetch_zip(
    pdf_path: Path,
    *,
    poll_interval: float = 5.0,
    poll_timeout: float = 600.0,
    transport: httpx.BaseTransport | None = None,
) -> bytes:
    """PDF 하나를 MinerU v4 Precise API로 보내고 결과 ZIP 바이트를 돌려준다.

    transport 는 자체 점검용 주입구 (httpx.MockTransport) — 실전에서는 넘기지 않는다.
    실패는 전부 MineruApiError 로 나간다. httpx 예외는 밖으로 새지 않는다.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise MineruApiError(f"PDF 파일이 없다: {pdf_path}")
    size = pdf_path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise MineruApiError(
            f"파일이 API 한도 200MB를 넘는다 ({size} bytes): {pdf_path.name}"
        )

    load_dotenv()  # .env의 MINERU_API_TOKEN — 이미 설정된 env는 덮지 않는다
    token = os.environ.get("MINERU_API_TOKEN", "").strip()
    if not token:
        raise MineruApiError(
            "MINERU_API_TOKEN이 없다. .env에 넣을 것 (발급: mineru.net/apiManage/token)"
        )
    auth = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=60.0, transport=transport, follow_redirects=True) as client:
            # 1단계 — 업로드 URL 발급. model_version="vlm" 은 생략 금지 (PLAN.md)
            resp = client.post(
                f"{BASE_URL}/file-urls/batch",
                headers=auth,
                json={
                    "files": [{"name": pdf_path.name, "data_id": pdf_path.stem}],
                    "model_version": "vlm",
                    "enable_formula": True,
                    "enable_table": True,
                    "language": "en",  # ponytail: 대상이 영어 논문뿐. 다국어 필요 시 인자로 뺀다
                },
            )
            data = _checked_data(resp, "file-urls/batch")
            batch_id = data.get("batch_id")
            file_urls = data.get("file_urls") or []
            if not batch_id or not file_urls:
                raise MineruApiError(
                    f"file-urls/batch 응답에 batch_id/file_urls가 없다: {data!r}"
                )

            # 2단계 — 바이너리 그대로 PUT. Content-Type 헤더를 붙이면 안 된다 (PLAN.md)
            up = client.put(file_urls[0], content=pdf_path.read_bytes())
            if up.status_code != 200:
                raise MineruApiError(f"업로드 실패: PUT HTTP {up.status_code}")

            # 3단계 — done/failed 까지 폴링. 타임아웃 상한을 둔다
            deadline = time.monotonic() + poll_timeout
            while True:
                resp = client.get(
                    f"{BASE_URL}/extract-results/batch/{batch_id}", headers=auth
                )
                data = _checked_data(resp, "extract-results")
                results = data.get("extract_result") or []
                item = results[0] if results else {}
                state = item.get("state")
                if state == "done":
                    zip_url = item.get("full_zip_url")
                    if not zip_url:
                        raise MineruApiError(f"done인데 full_zip_url이 없다: {item!r}")
                    zresp = client.get(zip_url)
                    if zresp.status_code != 200:
                        raise MineruApiError(f"ZIP 다운로드 실패: HTTP {zresp.status_code}")
                    return zresp.content
                if state == "failed":
                    raise MineruApiError(
                        f"MinerU 해석 실패: {item.get('err_msg', '(사유 없음)')} — {_LIMIT_HINT}"
                    )
                if time.monotonic() >= deadline:
                    raise MineruApiError(
                        f"폴링 타임아웃 {poll_timeout}s 초과 (마지막 state={state!r})"
                    )
                time.sleep(poll_interval)
    except httpx.HTTPError as e:
        # httpx 예외는 여기서 끝난다 — 호출자는 MineruApiError만 본다 (CLAUDE.md §7)
        raise MineruApiError(f"MinerU 통신 실패: {type(e).__name__}: {e}") from e


def _checked_data(resp: httpx.Response, step: str) -> dict:
    """HTTP·API 수준 오류를 전부 MineruApiError로 바꾸고 data 딕셔너리만 돌려준다."""
    if resp.status_code == 401:
        raise MineruApiError(f"{step}: HTTP 401 — {_EXPIRY_HINT}")
    if resp.status_code != 200:
        raise MineruApiError(f"{step}: HTTP {resp.status_code} — {resp.text[:200]}")
    try:
        body = resp.json()
    except ValueError as e:
        raise MineruApiError(f"{step}: JSON이 아닌 응답 — {resp.text[:200]}") from e
    if body.get("code") != 0:
        raise MineruApiError(
            f"{step}: API 거부 code={body.get('code')} msg={body.get('msg')!r} — {_LIMIT_HINT}"
        )
    data = body.get("data")
    return data if isinstance(data, dict) else {}


if __name__ == "__main__":
    # 자체 점검 — 프레임워크·픽스처 없이 assert만 (CLAUDE.md §7).
    # 실제 API는 호출하지 않는다: httpx.MockTransport 로 응답을 흉내 낸다.
    import json
    import tempfile

    tmp_pdf = Path(tempfile.mkdtemp()) / "t.pdf"
    tmp_pdf.write_bytes(b"%PDF-1.4 fake")
    os.environ["MINERU_API_TOKEN"] = "test-token"  # load_dotenv는 기존 env를 덮지 않는다

    ZIP = b"PK\x03\x04fakezip"
    polls = {"n": 0}

    def ok_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/file-urls/batch"):
            # 1단계: 토큰·vlm 명시를 여기서 검증
            assert request.headers["authorization"] == "Bearer test-token"
            body = json.loads(request.content)
            assert body["model_version"] == "vlm"
            assert body["files"][0]["name"] == "t.pdf"
            return httpx.Response(200, json={
                "code": 0,
                "data": {"batch_id": "b1", "file_urls": ["https://oss.example/u1"]},
            })
        if url == "https://oss.example/u1":
            # 2단계: raw bytes, Content-Type 헤더 금지 (PLAN.md)
            assert "content-type" not in request.headers
            assert request.content == b"%PDF-1.4 fake"
            return httpx.Response(200)
        if "extract-results/batch/b1" in url:
            # 3단계: pending 을 한 번 거쳐 done — 폴링 루프를 실제로 태운다
            polls["n"] += 1
            if polls["n"] == 1:
                return httpx.Response(200, json={
                    "code": 0, "data": {"extract_result": [{"state": "pending"}]},
                })
            return httpx.Response(200, json={
                "code": 0,
                "data": {"extract_result": [
                    {"state": "done", "full_zip_url": "https://oss.example/z1"},
                ]},
            })
        if url == "https://oss.example/z1":
            return httpx.Response(200, content=ZIP)
        raise AssertionError(f"예상 밖 요청: {url}")

    # 정상 경로: ZIP 바이트가 그대로 돌아온다
    got = fetch_zip(tmp_pdf, poll_interval=0, transport=httpx.MockTransport(ok_handler))
    assert got == ZIP
    assert polls["n"] == 2  # pending 1회 후 done

    # 401: httpx 타입이 아니라 MineruApiError, 메시지에 14일 만료 힌트
    try:
        fetch_zip(tmp_pdf, poll_interval=0,
                  transport=httpx.MockTransport(lambda r: httpx.Response(401)))
        raise AssertionError("401인데 에러가 안 났다")
    except MineruApiError as e:
        assert "14일" in str(e)

    # API 거부(code != 0): 한도 초과 힌트가 붙는다
    try:
        fetch_zip(tmp_pdf, poll_interval=0, transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"code": -500, "msg": "file too large"})))
        raise AssertionError("거부인데 에러가 안 났다")
    except MineruApiError as e:
        assert "한도" in str(e) and "file too large" in str(e)

    # failed 상태: err_msg 가 메시지에 나온다
    def failed_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/file-urls/batch"):
            return httpx.Response(200, json={
                "code": 0,
                "data": {"batch_id": "b2", "file_urls": ["https://oss.example/u2"]},
            })
        if str(request.url) == "https://oss.example/u2":
            return httpx.Response(200)
        return httpx.Response(200, json={
            "code": 0,
            "data": {"extract_result": [{"state": "failed", "err_msg": "parse blew up"}]},
        })

    try:
        fetch_zip(tmp_pdf, poll_interval=0, transport=httpx.MockTransport(failed_handler))
        raise AssertionError("failed인데 에러가 안 났다")
    except MineruApiError as e:
        assert "parse blew up" in str(e)

    # 네트워크 예외: httpx.ConnectError 가 새지 않고 MineruApiError 로 감싸인다
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    try:
        fetch_zip(tmp_pdf, poll_interval=0, transport=httpx.MockTransport(boom))
        raise AssertionError("접속 실패인데 에러가 안 났다")
    except MineruApiError as e:
        assert "boom" in str(e)

    # 200MB 초과: 업로드 전에 걸러진다 (sparse 파일이라 디스크는 안 먹는다)
    fat_pdf = tmp_pdf.parent / "fat.pdf"
    with open(fat_pdf, "wb") as f:
        f.truncate(MAX_FILE_BYTES + 1)
    try:
        fetch_zip(fat_pdf, poll_interval=0, transport=httpx.MockTransport(boom))
        raise AssertionError("200MB 초과인데 에러가 안 났다")
    except MineruApiError as e:
        assert "200" in str(e)

    # 없는 파일: 요청이 나가기 전에 걸러진다
    try:
        fetch_zip(tmp_pdf.parent / "no-such.pdf", poll_interval=0,
                  transport=httpx.MockTransport(boom))
        raise AssertionError("없는 파일인데 에러가 안 났다")
    except MineruApiError:
        pass

    print("mineru_api.py self-check passed")
