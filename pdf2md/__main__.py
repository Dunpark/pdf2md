"""CLI — 유일한 진입점. 인자 파싱 → parse_pdf() 조립 → Gate A → 출력 (#6).

조립 순서의 판단은 전부 여기서 한다: 캐시 히트면 API를 건너뛰고(cache가
mineru_api를 모르는 이유), Gate A 위반이면 output/을 만들기 전에 멈춘다 —
멀쩡해 보이는 파일을 경고와 나란히 써 주는 것이 바로 이 프로젝트가 막으려는
실패 모드다.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

from pdf2md import cache, mineru_api
from pdf2md.gate_a import gate_a
from pdf2md.refine import refine
from pdf2md.strict import ParseResult, Pdf2mdError, format_report

USAGE = "usage: python -m pdf2md <pdf-path> [--md | --notion [page-url]]"


def parse_pdf(
    pdf_path: Path,
    *,
    cache_root: Path = Path("cache"),
    fetch=mineru_api.fetch_zip,  # 테스트 주입구 — 실전에서는 넘기지 않는다
) -> ParseResult:
    """캐시 조회 → 미스면 API → 해제 → ParseResult (PLAN.md Phase 1)."""
    entry = cache.cache_dir(pdf_path, cache_root)
    if not cache.is_cached(entry):
        cache.extract_zip(fetch(pdf_path), entry)
    return cache.load_result(entry)


def _ask(prompt: str) -> str | None:
    """input() 한 번. 파이프·CI(EOF, pytest의 캡처 stdin)면 None — 호출자가 usage 처리."""
    try:
        return input(prompt).strip()
    except (EOFError, OSError):
        return None


def main(
    argv: list[str],
    *,
    # 테스트 주입구 (parse_pdf의 fetch와 같은 무늬). None이면 실제 모듈을 lazy 임포트
    # 한다 — notion_blocks/notion_upload는 #16/#17 소유라 이 브랜치에는 아직 없고,
    # 임포트를 Notion 경로 안으로 미뤄야 --md 경로가 병합 전에도 온전히 돈다.
    to_blocks=None,
    upload=None,
    count_children=None,
) -> int:
    # cp949 콘솔에서 리포트의 비인코딩 문자(em-dash, MinerU가 준 임의 유니코드)로
    # CLI가 죽는 것을 실측함 — 깨진 글자 하나는 '?'로 대체하고 리포트는 살린다
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")

    # 인자: PDF가 첫 위치 인자, 그 뒤에 대상 플래그 (전 형태가 PLAN "CLI" 절에 있다)
    if not argv or argv[0].startswith("--"):
        print(USAGE, file=sys.stderr)
        return 2
    pdf_path, rest = Path(argv[0]), argv[1:]
    if rest == []:
        mode, notion_url = None, None  # 대화형 — 아래에서 묻는다
    elif rest == ["--md"]:
        mode, notion_url = "md", None
    elif rest == ["--notion"]:
        mode, notion_url = "notion", None  # URL만 묻는다
    elif len(rest) == 2 and rest[0] == "--notion":
        mode, notion_url = "notion", rest[1]
    else:
        print(USAGE, file=sys.stderr)
        return 2
    if not pdf_path.is_file():  # 외부 입력은 경계에서 검증한다 (CLAUDE.md §7)
        # 런타임 메시지는 영어로 — 리포트(format_report)와 언어를 맞추고,
        # UTF-8이 아닌 콘솔에서도 항상 온전히 읽히게 한다
        print(f"not a PDF file: {pdf_path}", file=sys.stderr)
        return 2

    # 물을 것은 파이프라인을 태우기 전에 전부 묻는다 — 파싱 후에 EOF로 죽지 않도록
    interactive = mode is None or (mode == "notion" and notion_url is None)
    if mode is None:
        ans = _ask("Output destination? [1] markdown only  [2] Notion + markdown: ")
        if ans == "1":
            mode = "md"
        elif ans == "2":
            mode = "notion"
        else:  # EOF 포함 — 스크립트는 플래그를 쓰라는 뜻이다
            print(USAGE, file=sys.stderr)
            return 2
    if mode == "notion" and not notion_url:
        notion_url = _ask("Notion page URL: ")
        if not notion_url:
            print(USAGE, file=sys.stderr)
            return 2

    try:
        result = parse_pdf(pdf_path)
        violations = gate_a(result.content_list)
        print(format_report(violations))
        if any(v.severity != "warning" for v in violations):
            # 위반 = 내용 소실. output/을 쓰지 않고 멈춘다. 경고(이미지 폴백)는
            # 내용이 남아 있으므로 리포트만 찍고 진행한다.
            print("halt: recognition loss detected — nothing written to output/. "
                  "To retry MinerU, delete the cache entry and rerun.", file=sys.stderr)
            return 1
        # 정제(PLAN.md Phase 3)는 output에만 적용한다 — 캐시는 MinerU 원본 그대로,
        # 그래야 정제 규칙이 바뀌어도 API를 다시 태우지 않고 재생성할 수 있다
        refined_md, notes = refine(result.markdown)
        for note in notes:
            print(f"refine: {note}", file=sys.stderr)
        # output/ md를 Notion보다 먼저 쓴다 — 업로드가 실패해도 결과물은 온전히 남는다
        md_path = cache.assemble_output(
            dataclasses.replace(result, markdown=refined_md), pdf_path.stem)
        print(f"-> {md_path}")

        if mode == "notion":
            if to_blocks is None:
                from pdf2md.notion_blocks import to_blocks
            if upload is None or count_children is None:
                from pdf2md import notion_upload
                upload = upload or notion_upload.upload
                count_children = count_children or notion_upload.count_children

            # 한도 검사는 전부 to_blocks 안 — 여기서 실패하면 네트워크는 안 탄 것
            doc = to_blocks(refined_md, result.image_dir)
            for w in doc.warnings:
                print(f"notion: {w}", file=sys.stderr)

            existing = count_children(notion_url)
            if existing > 0:
                if interactive:
                    ans = _ask(f"Page already has {existing} block(s). New blocks are "
                               "appended after them. Continue? [y/N]: ")
                    if (ans or "").lower() != "y":
                        print("notion: aborted before upload; markdown is complete.",
                              file=sys.stderr)
                        return 0
                else:  # 플래그 실행은 스크립트를 막지 않는다 — 경고 한 줄 후 진행
                    print(f"notion: page already has {existing} block(s); "
                          "appending after them.", file=sys.stderr)

            page = upload(doc, notion_url)
            print(f"-> {page}")
        return 0
    except Pdf2mdError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
