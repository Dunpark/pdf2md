"""refined markdown → Notion 블록 JSON (#16).

to_blocks(md, image_dir) -> NotionDoc — 순수 변환, 네트워크 0.
strict 외에는 프로젝트 안의 무엇도 임포트하지 않는다 (PLAN.md "파일 구조").

Notion이 강제하는 모든 한도를 여기서 검사한다. 그래야 업로드(#17)가 내용
때문에 실패하는 일이 없다 — append 시점에 남는 실패는 네트워크·권한·429뿐.

LaTeX는 절대 정규화하지 않는다: $와 $ 사이를 바이트 그대로 복사한다.
틀린 수식은 없는 수식보다 나쁘다.

# ponytail: 입력 계약은 refine.py R1~R3의 출력이다 — R2의 ###### [N] 미니 헤딩과
# [[N](#N)] 인용 마커를 그대로 파싱한다. R2가 바뀌면 이 모듈도 바뀐다.
"""

from __future__ import annotations

import re
from pathlib import Path

from pdf2md.strict import NotionDoc, Pdf2mdError

_TEXT_LIMIT = 2000  # rich_text content 한도 — 초과분은 분할, 절대 자르지 않는다
_EQ_LIMIT = 1000    # equation expression 한도 — 자르면 틀린 수식이므로 halt
_ARRAY_LIMIT = 100  # rich_text 배열 한도 — 실측 최대 17, 넘으면 분할기 대신 halt

_IMAGE_RE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")
_HEADING_RE = re.compile(r"^(#{1,6}) (.*)$")
# R2가 세운 참조 미니 헤딩. 번호형 `[18]`과 author-year형 `Starace et al. 2025`가
# 둘 다 온다 — 어느 쪽이든 슬러그를 열쇠로 삼는다 (#44)
# 형태는 R2가 만드는 두 가지로 좁힌다 — 본문에 진짜 h6가 오면 조용히
# 문단으로 삼켜지면 안 된다
_REF_HEADING_RE = re.compile(r"^###### (\[\d+\]|.+\s\d{4}[a-z]?)\s*$")
_NUMBER_LABEL_RE = re.compile(r"^\[(\d+)\]$")
_UNESCAPED_DOLLAR_RE = re.compile(r"(?<!\\)\$")
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$[^$\n]*\$")  # `\$`는 본문의 달러다 (#44)
# 마크다운 이스케이프(`\*`·`\_`·`\$`)는 Notion에선 백슬래시째 보인다 — 실측:
# 저자 줄 "Guoxin Chen\*". CommonMark의 이스케이프 가능 구두점 집합 (#44)
_MD_ESCAPE_RE = re.compile(r"""\\([!"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])""")
_LINK_RE = re.compile(r"\[([^\][]*)\]\(([^)\s]+)\)")  # [[N](#N)]의 바깥 [는 label이 아니다
_SUP_RE = re.compile(r"<sup>(.*?)</sup>")
_SUP_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")  # R1은 |를 오직 \|로만 이스케이프한다
_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")


def to_blocks(md: str, image_dir: Path) -> NotionDoc:
    """정제된 마크다운을 Notion 1단계 블록 목록으로 바꾼다. 표현 불가 → Pdf2mdError."""
    if re.search(r"<table\b", md, re.IGNORECASE):
        # R1이 변환하지 못하고 남긴 HTML 표 — Notion에 텍스트로 박히면 표가
        # 사라진 것과 같다 (티켓 #16 Design Decisions)
        raise Pdf2mdError(
            "HTML <table> survived refine — it would upload as literal text. "
            "Fix the table (refine R1) before uploading to Notion.")

    doc = NotionDoc(blocks=[], images=[], citations=[], ref_targets={}, warnings=[])
    lines = md.split("\n")
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].rstrip()  # hard break의 끝 2공백은 문법이지 내용이 아니다
        if not line:
            i += 1
            continue

        # display 수식 — $$ 단독 줄 사이를 바이트 그대로
        if line == "$$":
            j = i + 1
            while j < n and lines[j].rstrip() != "$$":
                j += 1
            if j >= n:  # 닫히지 않음 — 수식 경계를 추정하지 않는다
                doc.warnings.append("unclosed $$ left as plain text")
                _append_plain(doc, line)
                i += 1
                continue
            _append_equation(doc, "\n".join(lines[i + 1:j]))
            i = j + 1
            continue
        if line.startswith("$$") and line.endswith("$$") and len(line) > 4:
            _append_equation(doc, line[2:-2])  # 한 줄짜리 $$…$$
            i += 1
            continue

        # 파이프 표 — 연속된 | 줄 한 덩어리
        if line.startswith("|"):
            j = i
            while j < n and lines[j].rstrip().startswith("|"):
                j += 1
            _append_table(doc, [lines[k].rstrip() for k in range(i, j)])
            i = j
            continue

        m = _REF_HEADING_RE.match(line)
        if m:
            # R2의 미니 헤딩 + 다음 줄 항목 전문 → 문단 한 블록으로 병합.
            # md의 h6 수십 개가 heading_3으로 뭉개지는 문제도 같이 사라진다 (플랜)
            label = m.group(1)
            entry = ""
            if i + 1 < n and lines[i + 1].strip():
                entry = lines[i + 1].rstrip()
                i += 1
            doc.ref_targets[_slug(label)] = len(doc.blocks)
            # 번호형은 R2가 항목 텍스트에서 번호를 떼어 헤딩으로 옮겼으므로 되돌린다.
            # author-year형은 항목이 저자명으로 시작해 그대로 온전하다 (#44)
            prefix = f"{label} " if _NUMBER_LABEL_RE.match(label) else ""
            _append_text_block(doc, "paragraph", f"{prefix}{entry}".rstrip())
            i += 1
            continue

        m = _HEADING_RE.match(line)
        if m:
            depth = len(m.group(1))
            if depth == 1 and not doc.title:
                doc.title = m.group(2)  # 첫 h1 = 논문 제목 — 페이지 제목 설정용 (#25)
            if depth > 3:
                doc.warnings.append(
                    f"clamped {'#' * depth} heading to heading_3: {m.group(2)[:40]}")
                depth = 3
            _append_text_block(doc, f"heading_{depth}", m.group(2))
            i += 1
            continue

        m = _IMAGE_RE.match(line)
        if m:
            # 문단 한가운데 이미지 줄도 여기로 온다 — 줄 단위 처리라 문단이
            # 자연히 앞/이미지/뒤 3분할된다 (reference/의 리터럴 텍스트 버그 방지)
            path = image_dir / Path(m.group(1)).name
            if not path.is_file():
                # 업로드 중간 실패를 막는다 — 모든 내용 검사는 네트워크 이전에
                raise Pdf2mdError(f"image referenced in markdown not found: {path}")
            doc.images.append((len(doc.blocks), path))
            doc.blocks.append({"type": "image", "image": {
                "type": "file_upload", "file_upload": {"id": ""}}})
            i += 1
            continue

        if line.startswith("• "):
            _append_text_block(doc, "bulleted_list_item", line[2:])
            i += 1
            continue

        _append_text_block(doc, "paragraph", line)
        i += 1
    return doc


# ---------- 블록 조립 ----------

def _slug(heading: str) -> str:
    """GitHub식 헤딩 슬러그. R2가 링크에 쓴 것과 같은 계산이어야 한다 (#44).

    # ponytail: refine.py에 같은 함수가 있지만 이 모듈은 strict 외에는 아무것도
    # 임포트하지 않는다 (PLAN.md "파일 구조"). 두 줄이라 사본이 더 싸다.
    """
    kept = "".join(c for c in heading.lower() if c.isalnum() or c in " -")
    return "-".join(kept.split())


def _append_text_block(doc: NotionDoc, btype: str, text: str) -> None:
    idx = len(doc.blocks)
    elements, cites = _rich_text(text, doc.warnings)
    doc.citations.extend((idx, rt_idx, num) for rt_idx, num in cites)
    doc.blocks.append({"type": btype, btype: {"rich_text": elements}})


def _append_plain(doc: NotionDoc, text: str) -> None:
    """마크다운 해석 없이 문자 그대로 문단으로 넣는다 (2000자 분할만 적용)."""
    doc.blocks.append({"type": "paragraph", "paragraph": {
        "rich_text": [{"type": "text", "text": {"content": c}} for c in _chunks(text)]}})


def _append_equation(doc: NotionDoc, expr: str) -> None:
    if not expr.strip():
        doc.warnings.append("empty $$ block left as plain text")
        _append_plain(doc, "$$" + expr + "$$")
        return
    _check_equation(expr)
    doc.blocks.append({"type": "equation", "equation": {"expression": expr}})


def _append_table(doc: NotionDoc, rows: list[str]) -> None:
    parsed: list[list[str]] = []
    for r, row in enumerate(rows):
        pieces = _CELL_SPLIT_RE.split(row)
        pieces = pieces[1:]  # 여는 |의 왼쪽은 항상 빈 조각
        if pieces and not pieces[-1].strip():
            pieces = pieces[:-1]  # 닫는 |의 오른쪽
        cells = [p.strip().replace("\\|", "|") for p in pieces]
        if r == 1 and cells and all(_SEPARATOR_CELL_RE.match(c) for c in cells):
            continue  # GFM 헤더 구분선은 표기일 뿐
        parsed.append(cells)

    width = len(parsed[0])
    for cells in parsed:
        if len(cells) != width:
            raise Pdf2mdError(
                f"table row has {len(cells)} cells, expected {width} — "
                "refusing to guess the layout")

    # ponytail: 인접 두 행의 동일 셀 = rowspan 전개 흔적 휴리스틱. 오탐해도
    # 경고일 뿐 내용은 무손실. Notion의 has_column_header는 1행뿐이다 (플랜)
    if len(parsed) >= 2 and any(a and a == b for a, b in zip(parsed[0], parsed[1])):
        doc.warnings.append(
            "table may have a two-row header (rowspan expansion); "
            "Notion marks only the first row as header")

    cell_cites = 0
    children = []
    for cells in parsed:
        row_cells = []
        for cell in cells:
            elements, cites = _rich_text(cell, doc.warnings)
            cell_cites += len(cites)  # table_row는 2단계 블록 — #19가 패치 불가
            row_cells.append(elements)
        children.append({"type": "table_row", "table_row": {"cells": row_cells}})
    if cell_cites:
        doc.warnings.append(
            f"{cell_cites} citation(s) in table cells stay plain text "
            "(row ids are absent from the append response)")

    doc.blocks.append({"type": "table", "table": {
        "table_width": width, "has_column_header": True,
        "has_row_header": False, "children": children}})


# ---------- rich_text ----------

def _rich_text(text: str, warnings: list[str]) -> tuple[list[dict], list[tuple[int, str]]]:
    """한 줄의 텍스트 → (rich_text 배열, [(배열 인덱스, 인용 번호)])."""
    if not text:
        return [], []
    # 이스케이프된 `\$`는 본문의 달러 기호지 수식 구분자가 아니다 — 실측:
    # "costs approximately \$832" 한 줄이 통째로 평문으로 떨어졌다 (#44)
    dollars = len(_UNESCAPED_DOLLAR_RE.findall(text))
    if dollars % 2:
        # 수식 경계를 추정하지 않는다 — 줄 전체를 평문으로.
        # $가 하나뿐이면 짝지을 수식이 애초에 없다 (실측: 표의 금액 `$33.05`
        # 7건) — 평문이 정답이므로 경고하지 않는다 (#44)
        if dollars > 1:
            warnings.append(f"odd number of $ — line left as plain text: {text[:60]}")
        return [{"type": "text", "text": {"content": c}} for c in _chunks(text)], []

    elements: list[dict] = []
    cites: list[tuple[int, str]] = []
    parts = _INLINE_MATH_RE.split(text)
    maths = _INLINE_MATH_RE.findall(text)
    for k, part in enumerate(parts):
        _emit_text(part, elements, cites, warnings)
        if k < len(maths):
            expr = maths[k][1:-1]  # $ 사이 바이트 그대로 — 트림·정규화 금지
            if not expr:
                warnings.append("empty $$ in text left as plain")
                _emit_text(maths[k], elements, cites, warnings)
                continue
            _check_equation(expr)
            elements.append({"type": "equation", "equation": {"expression": expr}})
    if len(elements) > _ARRAY_LIMIT:
        # Notion이 validation_error로 거부한다 — 침묵 손실이 아니므로 분할기
        # 대신 halt (티켓 #16 Design Decisions, 실측 최대 17개)
        raise Pdf2mdError(
            f"rich_text array has {len(elements)} elements, over Notion's "
            f"{_ARRAY_LIMIT} limit: {text[:60]}")
    return elements, cites


def _emit_text(part: str, elements: list[dict], cites: list[tuple[int, str]],
               warnings: list[str]) -> None:
    """수식 바깥 조각에서 링크·인용을 뽑고 나머지는 평문으로 쌓는다."""
    pos = 0
    for m in _LINK_RE.finditer(part):
        _emit_plain(part[pos:m.start()], elements, warnings)
        label, url = m.group(1), m.group(2)
        if url.startswith("#") and len(url) > 1:
            # R2의 인용 마커 — 번호형 [N](#N)과 author-year형
            # [Starace et al., 2025](#starace-et-al-2025)이 둘 다 온다 (#44).
            # 블록 id는 아직 없으므로 평문으로 넣고 위치만 기록한다.
            # #19가 append 후 링크를 패치하고, 앵커를 못 찾으면 거기서 경고한다
            cites.append((len(elements), url[1:]))
            elements.append({"type": "text", "text": {"content": label}})
        elif url.startswith(("http://", "https://")):
            for chunk in _chunks(label):
                elements.append({"type": "text",
                                 "text": {"content": chunk, "link": {"url": url}}})
        else:
            warnings.append(f"dropped unsupported link target {url!r}, kept text")
            _emit_plain(label, elements, warnings)
        pos = m.end()
    _emit_plain(part[pos:], elements, warnings)


def _emit_plain(s: str, elements: list[dict], warnings: list[str]) -> None:
    if not s:
        return

    def _sup(m: re.Match) -> str:
        inner = m.group(1)
        if any(c.isdigit() for c in inner):
            # 숫자가 문장에 섞여 읽히면 의미가 왜곡된다 (플랜: "gradients 4.")
            warnings.append(f"<sup>{inner}</sup> converted to unicode superscript")
            return inner.translate(_SUP_DIGITS)
        return inner  # ∗ † ‡ — 위첨자 자형이 없어 문자만 남긴다

    s = _MD_ESCAPE_RE.sub(r"\1", _SUP_RE.sub(_sup, s))
    for chunk in _chunks(s):
        elements.append({"type": "text", "text": {"content": chunk}})


def _chunks(s: str) -> list[str]:
    """2000자 초과는 분할한다 — 절대 자르지 않는다 (reference/의 실수 반복 금지)."""
    return [s[k:k + _TEXT_LIMIT] for k in range(0, len(s), _TEXT_LIMIT)] or [""]


def _check_equation(expr: str) -> None:
    if len(expr) > _EQ_LIMIT:
        raise Pdf2mdError(
            f"equation expression is {len(expr)} chars, over Notion's "
            f"{_EQ_LIMIT} limit — refusing to truncate a formula")
