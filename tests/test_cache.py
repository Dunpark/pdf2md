"""cache.py 동작 테스트 — 손으로 만든 ZIP 픽스처만 쓴다. 네트워크 없음 (CLAUDE.md §7)."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from pdf2md.cache import assemble_output, cache_dir, extract_zip, is_cached, load_result
from pdf2md.strict import ParseResult, Pdf2mdError

# ---- 픽스처 빌더 (프레임워크 픽스처 대신 평범한 함수) ----

MD = "# Attention\n\n본문이다. ![fig](images/fig1.png)\n"
CONTENT_LIST = [{"type": "text", "text": "본문이다.", "page_idx": 0}]


def build_zip(md_name="full.md", with_images=True, with_json=True) -> bytes:
    """MinerU 결과 ZIP 흉내 — auto/ 아래 md·json, images/ 아래 그림."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"auto/{md_name}", MD)
        if with_json:
            z.writestr("auto/abc_content_list.json", json.dumps(CONTENT_LIST))
        if with_images:
            z.writestr("images/fig1.png", b"\x89PNG-fake")
    return buf.getvalue()


# ---- cache_dir: sha256 키 ----

def test_cache_dir_is_sha256_of_bytes(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 hello")
    d = cache_dir(pdf, root=tmp_path / "cache")
    assert d.parent == tmp_path / "cache"
    assert len(d.name) == 64 and all(c in "0123456789abcdef" for c in d.name)
    # 같은 내용 → 같은 키 (파일명 무관)
    pdf2 = tmp_path / "b.pdf"
    pdf2.write_bytes(b"%PDF-1.4 hello")
    assert cache_dir(pdf2, root=tmp_path / "cache").name == d.name
    # 내용이 바뀌면 → 새 키
    pdf.write_bytes(b"%PDF-1.4 edited")
    assert cache_dir(pdf, root=tmp_path / "cache").name != d.name


# ---- extract_zip + load_result ----

def test_extract_and_load(tmp_path):
    d = tmp_path / "entry"
    extract_zip(build_zip(), d)
    r = load_result(d)
    assert isinstance(r, ParseResult)
    assert r.markdown == MD
    assert r.content_list == CONTENT_LIST
    assert r.image_dir.is_dir() and (r.image_dir / "fig1.png").exists()


def test_renamed_markdown_still_resolves(tmp_path):
    # PLAN.md 미확인 사항 1 — md 파일명이 바뀌어도 glob으로 찾는다
    d = tmp_path / "entry"
    extract_zip(build_zip(md_name="2308.99999_v2_output.md"), d)
    assert load_result(d).markdown == MD


def test_no_images_dir_is_tolerated(tmp_path):
    d = tmp_path / "entry"
    extract_zip(build_zip(with_images=False), d)
    r = load_result(d)
    assert r.markdown == MD  # 그림 없는 문서도 정상


def test_missing_content_list_raises(tmp_path):
    d = tmp_path / "entry"
    extract_zip(build_zip(with_json=False), d)
    with pytest.raises(Pdf2mdError):
        load_result(d)


def test_ambiguous_markdown_raises(tmp_path):
    # md가 2개면 조용히 하나를 고르지 않는다 — 침묵 실패 금지가 이 프로젝트의 존재 이유
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("auto/a.md", MD)
        z.writestr("auto/b.md", MD)
        z.writestr("auto/x_content_list.json", "[]")
    d = tmp_path / "entry"
    extract_zip(buf.getvalue(), d)
    with pytest.raises(Pdf2mdError):
        load_result(d)


def test_bad_zip_raises(tmp_path):
    with pytest.raises(Pdf2mdError):
        extract_zip(b"this is not a zip", tmp_path / "entry")


def test_content_list_not_a_list_raises(tmp_path):
    # 외부 입력 경계 검증 — JSON이 list가 아니면 거부
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("auto/full.md", MD)
        z.writestr("auto/x_content_list.json", '{"not": "a list"}')
    d = tmp_path / "entry"
    extract_zip(buf.getvalue(), d)
    with pytest.raises(Pdf2mdError):
        load_result(d)


# ---- 캐시 히트 (호출 생략 판단 자체는 #6 소관 — 여기선 판단 근거만 제공) ----

def test_cache_hit_second_run_needs_no_zip(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 hello")
    d = cache_dir(pdf, root=tmp_path / "cache")
    assert not is_cached(d)  # 첫 실행: 미스 → API를 불러야 함
    extract_zip(build_zip(), d)
    assert is_cached(d)  # 두 번째 실행: 히트 → ZIP 바이트 없이 로드만으로 끝
    assert load_result(d).markdown == MD


def test_partial_cache_is_not_a_hit(tmp_path):
    # md만 있고 content_list가 없는 반쪽 캐시는 히트가 아니다
    d = tmp_path / "cache" / "deadbeef"
    d.mkdir(parents=True)
    (d / "auto").mkdir()
    (d / "auto" / "full.md").write_text(MD, encoding="utf-8")
    assert not is_cached(d)


# ---- output 조립: 복사만, 가공 없음 ----

def test_assemble_output(tmp_path):
    d = tmp_path / "entry"
    extract_zip(build_zip(), d)
    r = load_result(d)
    md_path = assemble_output(r, pdf_stem="Attention is all you need", out_root=tmp_path / "output")
    assert md_path == tmp_path / "output" / "Attention is all you need.md"
    assert md_path.read_text(encoding="utf-8") == MD  # 무가공 복사
    assert (tmp_path / "output" / "images" / "fig1.png").read_bytes() == b"\x89PNG-fake"


def test_assemble_output_without_images(tmp_path):
    d = tmp_path / "entry"
    extract_zip(build_zip(with_images=False), d)
    md_path = assemble_output(load_result(d), pdf_stem="x", out_root=tmp_path / "output")
    assert md_path.exists()


def test_assemble_output_overwrites_stale(tmp_path):
    # 재실행이 전제인 설계 — 이전 산출물이 있어도 실패하지 않고 덮어쓴다
    d = tmp_path / "entry"
    extract_zip(build_zip(), d)
    r = load_result(d)
    assemble_output(r, pdf_stem="x", out_root=tmp_path / "output")
    md_path = assemble_output(r, pdf_stem="x", out_root=tmp_path / "output")
    assert md_path.read_text(encoding="utf-8") == MD
