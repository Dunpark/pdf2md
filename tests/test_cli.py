"""#6 CLI 통합 — parse_pdf 조립 순서와 Gate A halt 정책을 검증한다.

네트워크 금지: fetch 주입(parse_pdf)이나 미리 채운 캐시(main)로만 태운다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pdf2md.__main__ import main, parse_pdf

CLEAN = [
    {"type": "text", "page_idx": 0, "text": "hello", "text_level": 1},
    {"type": "equation", "page_idx": 1, "content": "E=mc^2"},
]
LOSSY = [
    {"type": "text", "page_idx": 0, "text": "hello"},
    {"type": "equation", "page_idx": 1, "content": ""},  # 수식 소실 → 위반
]
WARN_ONLY = [
    {"type": "table", "page_idx": 0, "table_body": "", "img_path": "images/t.jpg"},  # 이미지 폴백 → 경고
]


def _seed_cache(entry_dir: Path, content_list: list[dict], with_image: bool = False) -> None:
    """MinerU ZIP을 해제한 모양 그대로 캐시 디렉터리를 손으로 만든다."""
    entry_dir.mkdir(parents=True)
    (entry_dir / "paper.md").write_text("# fake md", encoding="utf-8")
    (entry_dir / "paper_content_list.json").write_text(json.dumps(content_list), encoding="utf-8")
    if with_image:
        (entry_dir / "images").mkdir()
        (entry_dir / "images" / "t.jpg").write_bytes(b"jpg")


def _fake_zip(content_list: list[dict]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("full/paper.md", "# fake md")
        z.writestr("full/paper_content_list.json", json.dumps(content_list))
    return buf.getvalue()


def test_parse_pdf_fetches_once_then_hits_cache(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF fake")
    calls = {"n": 0}

    def fetch(path):
        calls["n"] += 1
        return _fake_zip(CLEAN)

    r1 = parse_pdf(pdf, cache_root=tmp_path / "cache", fetch=fetch)
    r2 = parse_pdf(pdf, cache_root=tmp_path / "cache", fetch=fetch)  # 재실행 → 캐시 히트
    assert calls["n"] == 1  # AC: 같은 PDF 재실행 시 네트워크 호출 없음
    assert r1.markdown == r2.markdown == "# fake md"
    assert r1.content_list == CLEAN


def _run_main_in(tmp_path: Path, content_list: list[dict], with_image: bool = False,
                 argv_tail: list[str] | None = None, **kw) -> int:
    """tmp_path를 cwd로 삼아, 캐시를 미리 채워 네트워크 없이 main을 태운다.

    #18에서 플래그 없는 실행이 대화형이 되어, 기존 시나리오는 --md로 태운다
    (--md는 종전의 무플래그 동작과 동일해야 한다는 AC 그대로).
    """
    import pdf2md.cache as cache

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    _seed_cache(cache.cache_dir(pdf, tmp_path / "cache"), content_list, with_image)
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        return main([str(pdf)] + (argv_tail if argv_tail is not None else ["--md"]), **kw)
    finally:
        os.chdir(old)


def test_violation_halts_and_writes_nothing(tmp_path):
    code = _run_main_in(tmp_path, LOSSY)
    assert code == 1
    assert not (tmp_path / "output").exists()  # AC: 위반 시 output에 아무것도 안 쓴다


def test_clean_run_assembles_output(tmp_path):
    code = _run_main_in(tmp_path, CLEAN, with_image=True)
    assert code == 0
    assert (tmp_path / "output" / "paper.md").read_text(encoding="utf-8") == "# fake md"
    assert (tmp_path / "output" / "images" / "t.jpg").is_file()


def test_warning_only_reports_but_proceeds(tmp_path):
    # 경고(이미지 폴백)는 내용이 남아 있으므로 halt하지 않는다 — 리포트만 찍고 출력한다
    code = _run_main_in(tmp_path, WARN_ONLY)
    assert code == 0
    assert (tmp_path / "output" / "paper.md").is_file()


def test_output_is_refined(tmp_path):
    # 정제(#13)가 파이프라인 상시 단계인지 — 캐시의 HTML 표가 output에서는 파이프 표다
    import pdf2md.cache as cache

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    entry = cache.cache_dir(pdf, tmp_path / "cache")
    entry.mkdir(parents=True)
    (entry / "paper.md").write_text(
        "<table><tr><td>A</td></tr><tr><td>1</td></tr></table>", encoding="utf-8")
    (entry / "paper_content_list.json").write_text(json.dumps(CLEAN), encoding="utf-8")
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert main([str(pdf), "--md"]) == 0
    finally:
        os.chdir(old)
    out = (tmp_path / "output" / "paper.md").read_text(encoding="utf-8")
    assert "| A |" in out and "<table>" not in out
    cached = (entry / "paper.md").read_text(encoding="utf-8")
    assert "<table>" in cached  # 캐시는 원본 그대로 — 정제는 output에만


def test_missing_pdf_is_usage_error(tmp_path):
    assert main([str(tmp_path / "no-such.pdf")]) == 2
    assert main([]) == 2


# ---------- #18: 출력 대상 선택 (Notion 경로) ----------

from pdf2md.strict import NotionApiError, NotionDoc  # noqa: E402


def _fake_doc(warnings: list[str] | None = None) -> NotionDoc:
    return NotionDoc(blocks=[{"type": "paragraph"}], images=[], citations=[],
                     ref_targets={}, warnings=warnings or [])


def test_unknown_flag_is_usage_error(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    assert main([str(pdf), "--bogus"]) == 2
    assert main(["--md"]) == 2  # PDF 없이 플래그만 → usage


def test_no_flag_with_closed_stdin_exits_2(tmp_path):
    # 파이프·CI에서 input()이 즉시 실패하면 traceback 없이 usage error(2)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    assert main([str(pdf)]) == 2  # pytest의 stdin은 읽기 즉시 예외를 낸다


def test_notion_flag_uploads_after_writing_md(tmp_path, capsys):
    calls = {}

    def fake_to_blocks(md, image_dir):
        calls["md"] = md
        return _fake_doc(warnings=["clamped heading"])

    def fake_upload(doc, page_url, **kw):
        # 업로드 시점에 output/ md가 이미 존재해야 한다 — md 먼저, Notion은 그다음
        assert (Path("output") / "paper.md").is_file()
        calls["page_url"] = page_url
        return page_url

    code = _run_main_in(tmp_path, CLEAN, with_image=True,
                        argv_tail=["--notion", "https://notion.so/x"],
                        to_blocks=fake_to_blocks, upload=fake_upload,
                        count_children=lambda url, **kw: 0)
    assert code == 0
    assert calls["page_url"] == "https://notion.so/x"
    assert calls["md"] == "# fake md"  # 정제본이 변환기 입력이다
    assert (tmp_path / "output" / "paper.md").is_file()  # --notion에서도 md는 생성
    assert "notion: clamped heading" in capsys.readouterr().err


def test_notion_upload_failure_keeps_markdown(tmp_path):
    def fake_upload(doc, page_url, **kw):
        raise NotionApiError("appended 1 of 3 blocks")

    code = _run_main_in(tmp_path, CLEAN,
                        argv_tail=["--notion", "https://notion.so/x"],
                        to_blocks=lambda md, image_dir: _fake_doc(),
                        upload=fake_upload,
                        count_children=lambda url, **kw: 0)
    assert code == 1
    assert (tmp_path / "output" / "paper.md").is_file()  # md는 부수 피해가 아니다


def test_notion_flag_warns_but_proceeds_on_existing_children(tmp_path, capsys):
    # 플래그 실행은 스크립트를 막지 않는다 — 경고 한 줄 후 진행
    uploaded = {}
    code = _run_main_in(tmp_path, CLEAN,
                        argv_tail=["--notion", "https://notion.so/x"],
                        to_blocks=lambda md, image_dir: _fake_doc(),
                        upload=lambda doc, url, **kw: uploaded.setdefault("url", url),
                        count_children=lambda url, **kw: 3)
    assert code == 0
    assert uploaded["url"] == "https://notion.so/x"
    assert "3" in capsys.readouterr().err


def test_interactive_destination_md(tmp_path, monkeypatch):
    # 대화형에서 1(markdown)을 고르면 Notion 코드는 아예 타지 않는다
    monkeypatch.setattr("builtins.input", lambda prompt="": "1")
    code = _run_main_in(tmp_path, CLEAN, argv_tail=[],
                        to_blocks=None, upload=None, count_children=None)
    assert code == 0
    assert (tmp_path / "output" / "paper.md").is_file()


def test_notion_flag_without_url_asks_url_only(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr("builtins.input",
                        lambda prompt="": asked.append(prompt) or "https://notion.so/x")
    uploaded = {}
    code = _run_main_in(tmp_path, CLEAN, argv_tail=["--notion"],
                        to_blocks=lambda md, image_dir: _fake_doc(),
                        upload=lambda doc, url, **kw: uploaded.setdefault("url", url),
                        count_children=lambda url, **kw: 0)
    assert code == 0
    assert len(asked) == 1  # URL만 묻는다 — 출력 대상은 이미 정해져 있다
    assert uploaded["url"] == "https://notion.so/x"


# ---------- #31: md 입력 → 바로 Notion 업로드 ----------

def _run_main_md_in(tmp_path: Path, argv_tail: list[str], **kw) -> tuple[int, dict]:
    """output/ 레이아웃 그대로 md+images를 만들어 md 입력으로 main을 태운다."""
    md = tmp_path / "out" / "paper.md"
    md.parent.mkdir()
    md.write_text("# edited md\n\n![](images/t.jpg)\n", encoding="utf-8")
    (md.parent / "images").mkdir()
    (md.parent / "images" / "t.jpg").write_bytes(b"jpg")
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        return main([str(md)] + argv_tail, **kw), {"md": md}
    finally:
        os.chdir(old)


def test_md_input_uploads_without_parsing(tmp_path):
    # 파싱·Gate A·정제·output 조립 없이 파일 내용이 그대로 변환기로 들어간다
    calls = {}

    def fake_to_blocks(md_text, image_dir):
        calls["md"] = md_text
        calls["image_dir"] = image_dir
        return _fake_doc()

    code, paths = _run_main_md_in(
        tmp_path, ["--notion", "https://notion.so/x"],
        to_blocks=fake_to_blocks,
        upload=lambda doc, url, **kw: calls.setdefault("url", url),
        count_children=lambda url, **kw: 0)
    assert code == 0
    assert calls["md"] == paths["md"].read_text(encoding="utf-8")  # 편집본 그대로
    assert calls["image_dir"] == paths["md"].parent / "images"  # md 옆 images/
    assert calls["url"] == "https://notion.so/x"
    assert not (tmp_path / "cache").exists()  # MinerU·캐시는 안 탄다
    assert not (tmp_path / "output").exists()  # 재조립도 없다


def test_md_input_with_md_flag_is_usage_error(tmp_path):
    code, _ = _run_main_md_in(tmp_path, ["--md"])
    assert code == 2  # md→md는 무의미 — usage로 알려준다


def test_md_input_interactive_asks_url_only(tmp_path, monkeypatch):
    # md 입력은 갈 곳이 Notion뿐 — 대상 질문 없이 URL만 묻는다
    asked = []
    monkeypatch.setattr("builtins.input",
                        lambda prompt="": asked.append(prompt) or "https://notion.so/x")
    uploaded = {}
    code, _ = _run_main_md_in(
        tmp_path, [],
        to_blocks=lambda md, image_dir: _fake_doc(),
        upload=lambda doc, url, **kw: uploaded.setdefault("url", url),
        count_children=lambda url, **kw: 0)
    assert code == 0
    assert len(asked) == 1
    assert uploaded["url"] == "https://notion.so/x"


def test_md_input_usage_mentions_md_form(capsys):
    main([])
    assert "<file.md>" in capsys.readouterr().err  # usage만 보고도 md→notion 여정이 보인다


# ---------- #28: 자기설명적 CLI 여정 ----------

def test_usage_block_lists_all_forms(capsys):
    assert main([]) == 2
    err = capsys.readouterr().err
    assert "--md" in err and "--notion" in err  # 네 형태가 전부 보인다
    assert "markdown" in err.lower()  # 플래그 이름만이 아니라 뜻도 한 줄씩


def test_interactive_shows_destination_menu(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "1")
    _run_main_in(tmp_path, CLEAN, argv_tail=[])
    out = capsys.readouterr().out
    assert "output/" in out or "output\\" in out  # 1번이 무엇을 만드는지 미리 보여준다
    assert "Notion" in out  # 2번의 의미도


def test_parse_progress_line_appears(tmp_path, capsys):
    _run_main_in(tmp_path, CLEAN)
    out = capsys.readouterr().out
    assert "parsing" in out.lower()  # 긴 단계가 무엇인지 화면만 보고 알 수 있다
