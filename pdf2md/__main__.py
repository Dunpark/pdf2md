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


def main(argv: list[str]) -> int:
    # cp949 콘솔에서 리포트의 비인코딩 문자(em-dash, MinerU가 준 임의 유니코드)로
    # CLI가 죽는 것을 실측함 — 깨진 글자 하나는 '?'로 대체하고 리포트는 살린다
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")

    if len(argv) != 1:
        print("usage: python -m pdf2md <pdf-path>", file=sys.stderr)
        return 2
    pdf_path = Path(argv[0])
    if not pdf_path.is_file():  # 외부 입력은 경계에서 검증한다 (CLAUDE.md §7)
        # 런타임 메시지는 영어로 — 리포트(format_report)와 언어를 맞추고,
        # UTF-8이 아닌 콘솔에서도 항상 온전히 읽히게 한다
        print(f"not a PDF file: {pdf_path}", file=sys.stderr)
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
        md_path = cache.assemble_output(
            dataclasses.replace(result, markdown=refined_md), pdf_path.stem)
        print(f"-> {md_path}")
        return 0
    except Pdf2mdError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
