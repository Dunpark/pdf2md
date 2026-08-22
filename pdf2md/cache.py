"""cache/{sha256(pdf)}/ 관리, ZIP 해제, output/ 조립 — 디스크만 만진다.

네트워크를 모른다. 캐시 히트 시 API를 건너뛰는 판단은 __main__.py(#6)가
is_cached()를 보고 한다 (PLAN.md "파일 구조" — cache가 mineru_api를 임포트하면
wave 2 병렬성이 무너진다).

ZIP 내부 파일명은 1차 출처로 확정된 적이 없어(PLAN.md 미확인 사항 1) 하드코딩하지
않고 glob으로 찾는다. 후보가 0개거나 2개 이상이면 조용히 고르지 않고 멈춘다 —
침묵 실패 금지가 이 프로젝트의 존재 이유다.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

from pdf2md.strict import ParseResult, Pdf2mdError


def cache_dir(pdf_path: Path, root: Path = Path("cache")) -> Path:
    """PDF 바이트의 sha256을 키로 하는 캐시 디렉터리 경로. 만들지는 않는다."""
    try:
        with open(pdf_path, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
    except OSError as e:
        raise Pdf2mdError(f"PDF를 읽을 수 없다: {pdf_path} — {e}") from e
    return root / digest


def extract_zip(zip_bytes: bytes, entry_dir: Path) -> None:
    """MinerU 결과 ZIP을 캐시 디렉터리에 해제한다.

    # ponytail: 원본 ZIP 바이트는 따로 저장하지 않는다 — 해제본이 곧 캐시다.
    # 해제 도중 죽으면 반쪽 캐시가 남지만 is_cached()가 md·json 존재를 검사해 걸러낸다.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            entry_dir.mkdir(parents=True, exist_ok=True)
            # zipfile.extractall은 절대경로·'..' 성분을 제거하므로 경로 탈출 없음
            z.extractall(entry_dir)
    except zipfile.BadZipFile as e:
        raise Pdf2mdError(f"MinerU 응답이 유효한 ZIP이 아니다: {e}") from e
    except OSError as e:
        raise Pdf2mdError(f"캐시 디렉터리에 쓸 수 없다: {entry_dir} — {e}") from e


def _find_one(entry_dir: Path, pattern: str, what: str) -> Path:
    """glob으로 정확히 하나를 찾는다. 0개·2개 이상이면 멈춘다."""
    hits = sorted(p for p in entry_dir.rglob(pattern) if p.is_file())
    if len(hits) != 1:
        found = ", ".join(str(p.relative_to(entry_dir)) for p in hits) or "없음"
        raise Pdf2mdError(
            f"캐시에서 {what}({pattern})이 정확히 하나여야 하는데 {len(hits)}개다: {found} "
            f"— MinerU 출력 구조가 바뀌었거나 캐시가 손상됐다. {entry_dir} 삭제 후 재실행."
        )
    return hits[0]


def is_cached(entry_dir: Path) -> bool:
    """유효한 캐시 히트인가 — md·content_list가 하나씩 있어야 한다."""
    if not entry_dir.is_dir():
        return False
    try:
        _find_one(entry_dir, "*.md", "markdown")
        _find_one(entry_dir, "*_content_list.json", "content_list")
    except Pdf2mdError:
        return False
    return True


def load_result(entry_dir: Path) -> ParseResult:
    """해제된 캐시에서 ParseResult를 조립한다. 파일명은 전부 glob으로 찾는다."""
    md_path = _find_one(entry_dir, "*.md", "markdown")
    json_path = _find_one(entry_dir, "*_content_list.json", "content_list")

    markdown = md_path.read_text(encoding="utf-8")
    try:
        content_list = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise Pdf2mdError(f"content_list JSON을 읽을 수 없다: {json_path} — {e}") from e
    if not isinstance(content_list, list):
        raise Pdf2mdError(
            f"content_list가 배열이 아니라 {type(content_list).__name__}이다: {json_path}"
        )

    # images/ 디렉터리 — 그림 없는 문서엔 없을 수 있다. 없으면 존재하지 않는 경로를 그대로 준다.
    image_dirs = sorted(p for p in entry_dir.rglob("images") if p.is_dir())
    if len(image_dirs) > 1:
        raise Pdf2mdError(f"images/ 디렉터리가 {len(image_dirs)}개다: {entry_dir}")
    image_dir = image_dirs[0] if image_dirs else entry_dir / "images"

    return ParseResult(markdown=markdown, content_list=content_list, image_dir=image_dir)


def assemble_output(result: ParseResult, pdf_stem: str, out_root: Path = Path("output")) -> Path:
    """output/{stem}.md + output/images/ 를 만든다. 복사만, 가공 없음 (정제는 Phase 2·3)."""
    try:
        out_root.mkdir(parents=True, exist_ok=True)
        md_path = out_root / f"{pdf_stem}.md"
        md_path.write_text(result.markdown, encoding="utf-8")
        if result.image_dir.is_dir():
            shutil.copytree(result.image_dir, out_root / "images", dirs_exist_ok=True)
    except OSError as e:
        raise Pdf2mdError(f"output을 조립할 수 없다: {out_root} — {e}") from e
    return md_path
