"""Phase 3 정제 — 실제로 깨진 것만 고친다 (PLAN.md Phase 3, 규칙 R1~R3).

refine(markdown) -> (정제된 markdown, 경고 목록). 순수 문자열 변환이고
프로젝트 안의 무엇도 임포트하지 않는다.

원칙 (Gate B 잔재에 대한 판단):
- 절대 halt하지 않는다. 확신할 수 없는 구조는 원본을 그대로 두고 경고만 낸다.
- 수식($…$, $$…$$)은 어떤 규칙으로도 건드리지 않는다 — 틀린 수식은 없는
  수식보다 나쁘다.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_TABLE_RE = re.compile(r"<table\b.*?</table>", re.DOTALL | re.IGNORECASE)
_INLINE_MATH_RE = re.compile(r"\$[^$\n]*\$")
_CITATION_RE = re.compile(r"\[(\d+(?:,\s*\d+)*)\]")
_REF_HEADING_RE = re.compile(r"^#{1,6}\s+References\s*$")
_REF_ENTRY_RE = re.compile(r"^\[(\d+)\]\s")
# 논문마다 번호 서식이 다르다 (#36): "3.1"·"3.1."(끝점)·"A.1."(부록 문자).
_NUMBERED_HEADING_RE = re.compile(r"^## ((?:\d+|[A-Z])(?:\.\d+)*\.?)( .*)$")


def refine(markdown: str) -> tuple[str, list[str]]:
    """R1(표) → R2(참조 링크) → R3(헤딩 깊이) 순서로 적용한다."""
    notes: list[str] = []
    md = _convert_tables(markdown, notes)
    md = _link_citations(md)
    md = _fix_heading_depth(md)
    return md, notes


# ---------- R1: HTML 표 → GFM 파이프 테이블 ----------

class _TableGrid(HTMLParser):
    """<table> 하나를 (텍스트, rowspan, colspan) 행렬로 모은다."""

    def __init__(self) -> None:
        super().__init__()  # convert_charrefs=True 기본값 — 엔티티는 여기서 복원된다
        self.rows: list[list[tuple[str, int, int]]] = []
        self._cell: list[str] | None = None
        self._span = (1, 1)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        d = dict(attrs)
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            self._cell = []
            self._span = (int(d.get("rowspan", 1)), int(d.get("colspan", 1)))

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self.rows:
            text = " ".join("".join(self._cell).split())
            self.rows[-1].append((text, *self._span))
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _table_to_pipe(html: str) -> str:
    """rowspan/colspan은 값을 해당 칸 전체에 복제해 전개한다 — 내용 무손실."""
    parser = _TableGrid()
    parser.feed(html)
    if not parser.rows or not any(parser.rows):
        raise ValueError("no rows")

    # 점유 행렬을 채워가며 병합 셀을 전개한다
    grid: list[list[str | None]] = []

    def _put(r: int, c: int, text: str) -> None:
        while len(grid) <= r:
            grid.append([])
        row = grid[r]
        while len(row) <= c:
            row.append(None)
        row[c] = text

    for r, cells in enumerate(parser.rows):
        c = 0
        for text, rspan, cspan in cells:
            while r < len(grid) and c < len(grid[r]) and grid[r][c] is not None:
                c += 1  # 위 행의 rowspan이 이미 차지한 칸은 건너뛴다
            for dr in range(rspan):
                for dc in range(cspan):
                    _put(r + dr, c + dc, text)
            c += cspan

    width = max(len(row) for row in grid)
    out = []
    for i, row in enumerate(grid):
        cells = [(x or "").replace("|", "\\|") for x in row] + [""] * (width - len(row))
        out.append("| " + " | ".join(cells) + " |")
        if i == 0:  # GFM은 헤더 구분선이 필수다
            out.append("|" + "---|" * width)
    return "\n".join(out)


def _convert_tables(md: str, notes: list[str]) -> str:
    def _sub(m: re.Match) -> str:
        try:
            return _table_to_pipe(m.group(0))
        except Exception as e:  # 확신 없는 변환은 하지 않는다 — 원본 유지 + 경고
            notes.append(f"table left as HTML (could not convert: {e})")
            return m.group(0)

    return _TABLE_RE.sub(_sub, md)


# ---------- R2: References 미니 헤딩 + 본문 인용 링크 ----------
#
# 점프 메커니즘은 Orca 디폴트 뷰 실측(2026-08-22)으로 정했다:
# HTML <a id> 앵커는 점프하지 않고, 각주 문법([^N]:)은 파일 전체를 코드 모드로
# 강제하며, GitHub식 헤딩 슬러그 링크만 동작한다. 그래서 항목마다 번호만 든
# 미니 헤딩(###### [18] → 슬러그 "18")을 세운다 — 항목 전문을 헤딩으로 만들면
# 슬러그 계산이 뷰어 구현마다 달라질 수 있어 번호만 쓴다.

def _link_citations(md: str) -> str:
    lines = md.split("\n")
    ref_start = next((i for i, l in enumerate(lines) if _REF_HEADING_RE.match(l)), None)
    if ref_start is None:
        return md  # References 섹션이 없으면 링크할 대상이 없다

    # References 항목마다 번호 미니 헤딩을 세우고, 실재하는 번호 집합을 모은다
    known: set[str] = set()
    for i in range(ref_start + 1, len(lines)):
        m = _REF_ENTRY_RE.match(lines[i])
        if m:
            known.add(m.group(1))
            lines[i] = f"###### [{m.group(1)}]\n{lines[i][m.end():]}"
    if not known:
        return md

    def _link(m: re.Match) -> str:
        nums = [n.strip() for n in m.group(1).split(",")]
        if not all(n in known for n in nums):
            return m.group(0)  # 목록에 없는 번호는 인용이 아니다 — 건드리지 않는다
        return "[" + ", ".join(f"[{n}](#{n})" for n in nums) + "]"

    in_display_math = False
    for i in range(ref_start):  # 본문에만 적용. References 자신은 제외
        stripped = lines[i].strip()
        if stripped == "$$" or (stripped.startswith("$$") ^ stripped.endswith("$$")):
            in_display_math = not in_display_math
            continue
        if in_display_math or (stripped.startswith("$$") and stripped.endswith("$$")):
            continue
        # 인라인 수식 구간은 잘라내고 바깥 조각에만 적용한다
        parts = _INLINE_MATH_RE.split(lines[i])
        maths = _INLINE_MATH_RE.findall(lines[i])
        parts = [_CITATION_RE.sub(_link, p) for p in parts]
        rebuilt = parts[0]
        for math, part in zip(maths, parts[1:]):
            rebuilt += math + part
        lines[i] = rebuilt
    return "\n".join(lines)


# ---------- R3: 번호 헤딩 깊이 ----------

def _fix_heading_depth(md: str) -> str:
    def _deepen(m: re.Match) -> str:
        label = m.group(1)
        # 끝점은 구분자가 아니다 — "3.1."도 "3.1"과 같은 2단계다
        depth = 2 + label.rstrip(".").count(".")
        return "#" * depth + f" {label}{m.group(2)}"

    return "\n".join(
        _NUMBERED_HEADING_RE.sub(_deepen, line) for line in md.split("\n")
    )
