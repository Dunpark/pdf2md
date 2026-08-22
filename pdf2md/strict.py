"""공유 타입과 strict 리포트.

이 모듈은 프로젝트 안의 무엇도 임포트하지 않는다 (PLAN.md "파일 구조").
mineru_api · cache · gate_a 는 이 모듈만 임포트하고 서로를 임포트하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class Pdf2mdError(Exception):
    """프로젝트 소유 에러의 뿌리. 외부(플랫폼·SDK) 예외는 경계에서 이것으로 감싼다."""


class MineruApiError(Pdf2mdError):
    """MinerU API 경계 전용 — httpx 예외·API 오류 응답을 이 타입으로 감싼다 (#3)."""


@dataclass
class Violation:
    """Gate A가 감지한 손실 하나. 사용자가 원본 PDF에서 찾아갈 수 있어야 한다."""

    condition: str  # 어떤 검사가 걸렸는가 (예: "table lost")
    page_idx: int  # content_list의 page_idx (0부터 센다)
    block_index: int  # content_list 배열 안에서의 블록 인덱스
    severity: str = "violation"  # "violation" | "warning" — PLAN.md Gate A 표의 두 단계
    detail: str = ""  # 사람이 읽을 부가 설명 (선택)


@dataclass
class ParseResult:
    """PLAN.md Phase 1이 고정한 파싱 결과의 모양. 세 필드 외에는 더하지 않는다."""

    markdown: str
    content_list: list[dict]
    image_dir: Path


def format_report(violations: list[Violation]) -> str:
    """위반 목록을 사람이 읽을 리포트 한 덩어리로 만든다."""
    if not violations:
        return "Gate A: OK — no violations"

    n_viol = sum(1 for v in violations if v.severity != "warning")
    n_warn = len(violations) - n_viol
    lines = [f"Gate A: {n_viol} violation(s), {n_warn} warning(s)"]
    for v in violations:
        tag = "WARNING" if v.severity == "warning" else "VIOLATION"
        # page_idx는 0부터 세므로 사람에게는 +1해서 보여준다
        line = f"  [{tag}] page {v.page_idx + 1} (block {v.block_index}): {v.condition}"
        if v.detail:
            line += f" — {v.detail}"
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    # 자체 점검 — 프레임워크·픽스처 없이 assert만 (CLAUDE.md §7)

    # 에러 타입: MineruApiError는 Pdf2mdError로 잡을 수 있어야 한다
    assert issubclass(MineruApiError, Pdf2mdError)
    try:
        raise MineruApiError("boom")
    except Pdf2mdError as e:
        assert "boom" in str(e)

    # ParseResult: PLAN.md가 고정한 세 필드
    r = ParseResult(markdown="# hi", content_list=[{"type": "text"}], image_dir=Path("images"))
    assert (r.markdown, r.content_list, r.image_dir) == ("# hi", [{"type": "text"}], Path("images"))

    # 빈 목록 → 위반 없음이 명시된 한 줄
    ok = format_report([])
    assert "no violations" in ok

    # 위반 1 + 경고 1 → 개수·조건 이름·페이지가 전부 리포트에 나온다
    vs = [
        Violation("table lost", page_idx=3, block_index=12,
                  detail="table_body and img_path both empty"),
        Violation("table fell back to image", page_idx=5, block_index=20, severity="warning"),
    ]
    report = format_report(vs)
    assert "1 violation" in report and "1 warning" in report
    assert "table lost" in report and "table fell back to image" in report
    assert "page 4" in report and "page 6" in report  # page_idx는 0부터 → 사람에게는 +1
    assert "block 12" in report and "block 20" in report
    assert "table_body and img_path both empty" in report

    print("strict.py self-check passed")
