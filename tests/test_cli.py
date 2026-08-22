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


def _run_main_in(tmp_path: Path, content_list: list[dict], with_image: bool = False) -> int:
    """tmp_path를 cwd로 삼아, 캐시를 미리 채워 네트워크 없이 main을 태운다."""
    import pdf2md.cache as cache

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    _seed_cache(cache.cache_dir(pdf, tmp_path / "cache"), content_list, with_image)
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        return main([str(pdf)])
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


def test_missing_pdf_is_usage_error(tmp_path):
    assert main([str(tmp_path / "no-such.pdf")]) == 2
    assert main([]) == 2
