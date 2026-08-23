"""Phase 3 정제 — 실제로 깨진 것만 고친다 (PLAN.md Phase 3, 규칙 R1~R5).

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
_FIRST_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
_INLINE_MATH_RE = re.compile(r"\$[^$\n]*\$")
_CITATION_RE = re.compile(r"\[(\d+(?:,\s*\d+)*)\]")
_REF_HEADING_RE = re.compile(r"^#{1,6}\s+References\s*$")
_REF_ENTRY_RE = re.compile(r"^\[(\d+)\]\s")
_SECTION_HEADING_RE = re.compile(r"^## ")
# author-year 인용 (#40): `(Starace et al., 2025)`·`(A, 2025; B, 2026b)`
_AY_CITE_RE = re.compile(r"\(([^()]{0,300}?\d{4}[a-z]?)\)")
_AY_PART_RE = re.compile(r"^(.+?),\s*(\d{4}[a-z]?)$")
_INITIALS_RE = re.compile(r"^(?:[A-Z]\.(?:-[A-Z]\.)?\s+)+")  # "G. ", "J. S. ", "W.-C. "
_AUTHOR_STOP_RE = re.compile(r",|\.\s|\s+and\s+|\s+et al")
_AND_OR_ETAL_RE = re.compile(r"\s+and\s+|\s+et al")
_YEAR_RE = re.compile(r"\b(\d{4}[a-z]?)\b")
# 논문마다 번호 서식이 다르다 (#36): "3.1"·"3.1."(끝점)·"A.1."(부록 문자).
_NUMBERED_HEADING_RE = re.compile(r"^## ((?:\d+|[A-Z])(?:\.\d+)*\.?)( .*)$")
_SUP_RE = re.compile(r"<sup>(.*?)</sup>")
_SUP_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_HTML_TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)(?:\s[^<>]*)?/?>")


def refine(markdown: str, table_images: list[str] | None = None,
           table_bodies: list[str] | None = None) -> tuple[str, list[str]]:
    """R1(표) → R2(참조 링크) → R3(헤딩 깊이) → R4(위첨자) → R5(잔존 HTML) 순.

    table_images는 content_list의 표 블록 순서대로인 `img_path` 목록이다 (#42).
    주면 표를 그 렌더 이미지로 바꾸고, 없으면 종전대로 파이프 테이블로 만든다
    (md 직접 입력(#31)에는 content_list가 없다). table_bodies를 함께 주면
    각 표의 첫 셀을 대조해 짝이 맞는지 확인한다.
    """
    notes: list[str] = []
    md = _convert_tables(markdown, notes, table_images, table_bodies)
    md = _link_citations(md, notes)
    md = _fix_heading_depth(md)
    md = _unwrap_superscripts(md, notes)
    _warn_leftover_html(md, notes)  # 마지막 — 모든 규칙이 끝난 상태를 본다
    return md, notes


# ---------- 수식 바깥에만 손대기 (R2·R4·R5 공용) ----------

def _sub_outside_math(text: str, sub) -> str:
    """줄마다 수식 구간을 빼고 나머지 조각에만 sub(str)->str 을 적용한다.

    `$$` 블록은 통째로, 인라인 `$…$`는 구간만 원본 그대로 둔다 — 수식은 어떤
    규칙으로도 건드리지 않는다. 조각을 읽기만 하고 그대로 돌려주면 스캐너로도 쓴다.
    """
    out: list[str] = []
    in_display_math = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "$$" or (stripped.startswith("$$") ^ stripped.endswith("$$")):
            in_display_math = not in_display_math
            out.append(line)
            continue
        if in_display_math or (stripped.startswith("$$") and stripped.endswith("$$")):
            out.append(line)
            continue
        parts = [sub(p) for p in _INLINE_MATH_RE.split(line)]
        maths = _INLINE_MATH_RE.findall(line)
        rebuilt = parts[0]
        for math, part in zip(maths, parts[1:]):
            rebuilt += math + part
        out.append(rebuilt)
    return "\n".join(out)


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
    """병합 셀은 값을 앵커 칸에만 두고, 다중 행 헤더는 한 행으로 합친다 (#40).

    값을 병합 범위 전체에 복제하면 그 열들이 저마다 그 값을 가진 것처럼 읽힌다
    (실측: Table 1 헤더의 `Gemini-3-Flash`가 4열 반복, Table 2 구간 구분 행이
    8번 반복). 마크다운은 병합을 표현할 수 없으므로 시각적 병합만 포기하고
    내용은 전부 남긴다 — 모든 값이 최소 한 번은 나온다.
    """
    parser = _TableGrid()
    parser.feed(html)
    if not parser.rows or not any(parser.rows):
        raise ValueError("no rows")

    # 두 벌을 만든다: spanned는 헤더 합치기용(그룹 라벨이 각 열에 필요),
    # anchored는 본문용(값은 앵커 칸에만)
    spanned: list[list[str | None]] = []
    anchored: list[list[str | None]] = []

    def _put(grid: list[list[str | None]], r: int, c: int, text: str) -> None:
        while len(grid) <= r:
            grid.append([])
        row = grid[r]
        while len(row) <= c:
            row.append(None)
        row[c] = text

    for r, cells in enumerate(parser.rows):
        c = 0
        for text, rspan, cspan in cells:
            while r < len(spanned) and c < len(spanned[r]) and spanned[r][c] is not None:
                c += 1  # 위 행의 rowspan이 이미 차지한 칸은 건너뛴다
            for dr in range(rspan):
                for dc in range(cspan):
                    _put(spanned, r + dr, c + dc, text)
                    _put(anchored, r + dr, c + dc, text if (dr, dc) == (0, 0) else "")
            c += cspan

    width = max(len(row) for row in spanned)

    def _pad(row: list[str | None]) -> list[str]:
        return [(x or "") for x in row] + [""] * (width - len(row))

    def _line(cells: list[str]) -> str:
        return "| " + " | ".join(x.replace("|", "\\|") for x in cells) + " |"

    # 0행 셀의 최대 rowspan = 헤더 행 수. 첫 행의 rowspan은 "이 아래 행까지가
    # 헤더"라는 뜻이다. GFM 헤더는 한 행뿐이라 열별로 이어붙인다.
    header_rows = min(max((rspan for _, rspan, _ in parser.rows[0]), default=1),
                      len(spanned))
    # 그룹 라벨 행(마지막 헤더 행 위)만 복제본을 쓴다 — 그래야 각 열이
    # "Gemini-3-Flash IterAgent"처럼 스스로를 설명한다. 마지막 헤더 행은 본문과
    # 같은 앵커 규칙이라 단일 헤더 행의 colspan은 반복되지 않는다 (Table 3 실측).
    header = []
    for c in range(width):
        seen: list[str] = []
        for r in range(header_rows):
            value = _pad(spanned[r] if r < header_rows - 1 else anchored[r])[c]
            if value and value not in seen:
                seen.append(value)
        header.append(" ".join(seen))

    out = [_line(header), "|" + "---|" * width]  # GFM은 헤더 구분선이 필수다
    out += [_line(_pad(row)) for row in anchored[header_rows:]]
    return "\n".join(out)


def _first_cell(html: str) -> str | None:
    """표의 첫 셀 텍스트 — md의 표와 content_list의 표가 같은 표인지 대조하는 열쇠."""
    m = _FIRST_CELL_RE.search(html)
    return " ".join(re.sub(r"<[^>]+>", "", m.group(1)).split()) if m else None


def _convert_tables(md: str, notes: list[str], images: list[str] | None = None,
                    bodies: list[str] | None = None) -> str:
    images, bodies = images or [], bodies or []
    order = 0
    as_image = 0

    def _pipe(html: str) -> str:
        try:
            return _table_to_pipe(html)
        except Exception as e:  # 확신 없는 변환은 하지 않는다 — 원본 유지 + 경고
            notes.append(f"table left as HTML (could not convert: {e})")
            return html

    def _sub(m: re.Match) -> str:
        nonlocal order, as_image
        html, i = m.group(0), order
        order += 1
        if i >= len(images) or not images[i]:
            return _pipe(html)  # 짝이 없다 — 종전 경로
        if i < len(bodies) and _first_cell(html) != _first_cell(bodies[i]):
            # 엉뚱한 그림이 표 자리에 박히는 것은 조용한 오답이다 — 순서를 믿지 않는다
            notes.append(f"table {i + 1}: the render image does not match the table "
                         "(first cell differs) — kept as a pipe table")
            return _pipe(html)
        as_image += 1
        return f"![]({images[i]})"

    result = _TABLE_RE.sub(_sub, md)
    if as_image:
        # 마크다운은 병합도 볼드도 못 그리므로 원본 렌더를 쓴다. 대신 셀 텍스트가
        # md에서 빠진다 — 검색·복사가 안 되고 Notion에도 그림으로 올라간다.
        # 값은 cache/에 남아 있으니 규칙이 바뀌면 API 없이 되살릴 수 있다.
        notes.append(f"{as_image} table(s) rendered as an image — merges and "
                     "bold/underline/colour survive, but the cell text is not "
                     "in the markdown")
    return result


# ---------- R2: References 미니 헤딩 + 본문 인용 링크 ----------
#
# 점프 메커니즘은 Orca 디폴트 뷰 실측(2026-08-22)으로 정했다:
# HTML <a id> 앵커는 점프하지 않고, 각주 문법([^N]:)은 파일 전체를 코드 모드로
# 강제하며, GitHub식 헤딩 슬러그 링크만 동작한다. 그래서 항목마다 번호만 든
# 미니 헤딩(###### [18] → 슬러그 "18")을 세운다 — 항목 전문을 헤딩으로 만들면
# 슬러그 계산이 뷰어 구현마다 달라질 수 있어 번호만 쓴다.

def _link_citations(md: str, notes: list[str]) -> str:
    lines = md.split("\n")
    ref_start = next((i for i, l in enumerate(lines) if _REF_HEADING_RE.match(l)), None)
    if ref_start is None:
        return md  # References 섹션이 없으면 링크할 대상이 없다

    # References는 자기 헤딩부터 다음 `## `까지다. 그 뒤(부록)는 다시 본문이라
    # 인용을 링크해야 한다 — 실측 논문은 인용 84개 중 49개가 부록에 있다 (#40)
    ref_end = next((i for i in range(ref_start + 1, len(lines))
                    if _SECTION_HEADING_RE.match(lines[i])), len(lines))

    linked = _link_numbered(lines, ref_start, ref_end, notes)
    if linked is None:  # 항목에 번호가 없다 = author-year 서식 논문
        linked = _link_author_year(lines, ref_start, ref_end, notes)
    return linked


def _body_sub(lines: list[str], ref_start: int, ref_end: int, sub) -> str:
    """References 블록만 빼고 본문 전체(앞·뒤)에 sub를 적용해 다시 합친다."""
    head = _sub_outside_math("\n".join(lines[:ref_start]), sub).split("\n") if ref_start else []
    tail = (_sub_outside_math("\n".join(lines[ref_end:]), sub).split("\n")
            if ref_end < len(lines) else [])
    return "\n".join(head + lines[ref_start:ref_end] + tail)


def _link_numbered(lines: list[str], ref_start: int, ref_end: int,
                   notes: list[str]) -> str | None:
    """`[1] First paper.` 서식. 번호 항목이 하나도 없으면 None을 돌려준다."""
    known: set[str] = set()
    out = list(lines)
    for i in range(ref_start + 1, ref_end):
        m = _REF_ENTRY_RE.match(lines[i])
        if m:
            known.add(m.group(1))
            out[i] = f"###### [{m.group(1)}]\n{lines[i][m.end():]}"
    if not known:
        return None

    count = 0

    def _link(m: re.Match) -> str:
        nonlocal count
        nums = [n.strip() for n in m.group(1).split(",")]
        if not all(n in known for n in nums):
            return m.group(0)  # 목록에 없는 번호는 인용이 아니다 — 건드리지 않는다
        count += len(nums)
        return "[" + ", ".join(f"[{n}](#{n})" for n in nums) + "]"

    result = _body_sub(out, ref_start, ref_end,
                       lambda part: _CITATION_RE.sub(_link, part))
    if not count:
        notes.append(f"citations: 0 linked — {len(known)} numbered reference(s) "
                     "but no citation in the body matched one")
    return result


# author-year 서식. 항목의 (제1저자 성, 연도)로 색인하고, 인용의 저자 문구를
# 그대로 미니 헤딩으로 세워 슬러그를 유일하게 만든다 (`Starace et al. 2025` →
# `#starace-et-al-2025`). 하나로 좁혀지지 않으면 평문으로 두고 센다 —
# 엉뚱한 참조로 뛰는 링크는 뛰지 않는 링크보다 나쁘다.

def _first_author(entry: str) -> str:
    """앞머리 이니셜을 떼고 첫 구분자 앞까지 — 기관명도 같은 규칙으로 잡힌다."""
    return _AUTHOR_STOP_RE.split(_INITIALS_RE.sub("", entry))[0].strip().rstrip(".")


def _is_two_author(entry: str, second: str | None) -> bool:
    """`Schmidgall and M. Moor.` 처럼 저자가 정확히 둘인가. second=None이면 이름 무시."""
    rest = _INITIALS_RE.sub("", entry)
    if second is None:
        return bool(re.match(r"^[^,]+?\s+and\s+", rest))
    return bool(re.match(rf"^{re.escape(_first_author(entry))}\s+and\s+"
                         rf"(?:[A-Z]\.\s*)*{re.escape(second)}[.,]", rest))


def _slug(heading: str) -> str:
    """GitHub식 헤딩 슬러그 — 소문자화, 구두점 제거, 공백은 하이픈."""
    kept = "".join(c for c in heading.lower() if c.isalnum() or c in " -")
    return "-".join(kept.split())


def _link_author_year(lines: list[str], ref_start: int, ref_end: int,
                      notes: list[str]) -> str:
    index: dict[tuple[str, str], list[int]] = {}
    for i in range(ref_start + 1, ref_end):
        if not lines[i].strip():
            continue
        who = _first_author(lines[i])
        for year in set(_YEAR_RE.findall(lines[i])):
            index.setdefault((who, year), []).append(i)
    if not index:
        return "\n".join(lines)

    anchors: dict[int, str] = {}  # 항목 줄 번호 → 미니 헤딩 문구
    linked = unresolved = 0

    def _resolve(phrase: str, year: str) -> int | None:
        who = _AND_OR_ETAL_RE.split(phrase)[0].strip().rstrip(".")
        cands = index.get((who, year), [])
        if len(cands) > 1:  # 같은 성·같은 해 — 인용의 저자 수 신호로 가른다
            pair = re.search(r"\s+and\s+(\S+)$", phrase)
            if pair:
                cands = [i for i in cands if _is_two_author(lines[i], pair.group(1))]
            elif "et al" in phrase:
                cands = [i for i in cands if not _is_two_author(lines[i], None)]
        return cands[0] if len(cands) == 1 else None

    def _one(part: str, record: bool) -> str:
        """인용 하나(`Starace et al., 2025`)를 링크로 바꾸거나 원문 그대로 둔다."""
        nonlocal linked, unresolved
        m = _AY_PART_RE.match(part.strip())
        if m:
            target = _resolve(m.group(1).strip(), m.group(2))
            if target is not None:
                heading = f"{m.group(1).strip()} {m.group(2)}"
                if record:
                    anchors[target] = heading
                    linked += 1
                return part.replace(part.strip(),
                                    f"[{part.strip()}]({'#' + _slug(heading)})")
        if record and m:
            unresolved += 1
        return part

    def _cite(m: re.Match, record: bool) -> str:
        parts = m.group(1).split(";")
        return "(" + ";".join(_one(p, record) for p in parts) + ")"

    # 1차: 어떤 인용이 어느 항목으로 가는지만 확정한다 (치환 결과는 버린다)
    _body_sub(lines, ref_start, ref_end,
              lambda part: _AY_CITE_RE.sub(lambda m: _cite(m, True), part))
    # 2차: 확정된 항목에 앵커 헤딩을 세우고 본문 인용을 링크로 바꾼다
    out = list(lines)
    for i, heading in anchors.items():
        out[i] = f"###### {heading}\n{lines[i]}"
    result = _body_sub(out, ref_start, ref_end,
                       lambda part: _AY_CITE_RE.sub(lambda m: _cite(m, False), part))

    if unresolved or not linked:
        notes.append(f"citations: {linked} linked, {unresolved} left as plain text "
                     "(no single matching References entry)")
    return result


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


# ---------- R4: <sup> 해제 ----------
#
# 마크다운에는 위첨자 문법이 없고, 뷰어는 HTML이 한 줄이라도 있으면 파일 전체를
# 코드 모드로 강제한다 (CLAUDE.md §11.9). 그래서 태그를 벗긴다.
# notion_blocks가 md 직접 입력(#31)을 위해 같은 변환을 따로 갖고 있다 — 그쪽은
# refine을 거치지 않은 손편집 md도 받으므로 사본이 제 몫을 한다.

def _unwrap_superscripts(md: str, notes: list[str]) -> str:
    """<sup>4</sup> → ⁴. 유니코드 위첨자 자형이 없는 ∗ † ‡ 는 문자만 남는다."""
    count = 0

    def _sup(m: re.Match) -> str:
        nonlocal count
        count += 1
        return m.group(1).translate(_SUP_DIGITS)

    out = _sub_outside_math(md, lambda part: _SUP_RE.sub(_sup, part))
    if count:
        # 태그마다 한 줄이면 실측 11줄 — 리포트가 소음에 덮인다. 실행당 한 줄.
        notes.append(f"unwrapped {count} <sup> tag(s) to unicode superscript "
                     "(markdown has no superscript markup)")
    return out


# ---------- R5: 남은 HTML 경고 ----------

def _warn_leftover_html(md: str, notes: list[str]) -> None:
    """규칙이 다 돌고도 남은 태그를 알린다 — 고치지는 않는다.

    오늘은 <sup>이었고 다음 논문은 <br>·<i>일 것이다. 특정 태그만 처리하고
    일반 경고를 두지 않으면 같은 고장이 또 조용히 사용자에게 간다 (#38).
    """
    tags: set[str] = set()

    def _scan(part: str) -> str:
        tags.update(m.group(1).lower() for m in _HTML_TAG_RE.finditer(part))
        return part

    _sub_outside_math(md, _scan)  # 수식 안의 부등호를 태그로 오인하지 않는다
    if tags:
        found = ", ".join(f"<{t}>" for t in sorted(tags))
        notes.append(f"markdown still contains HTML ({found}) — some viewers "
                     "force code mode on a file containing HTML")
