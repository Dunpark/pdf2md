"""Gate A — content_list.json에서 조용한 인식 실패를 감지한다.

md로 내려오면 원리적으로 감지 불가능한 손실(빈 블록·사라진 페이지)을
content_list 1회 순회로 찾아 list[Violation]으로 보고한다. 감지·보고만 하고
절대 고치지 않는다 — 틀린 수식은 없는 수식보다 나쁘다 (CLAUDE.md §3).

markdown을 함께 주면 커버리지 검사가 켜진다 (#36): content_list에는 있는데
md에는 없는 텍스트를 찾는다. 이것은 "md로 내려오면 감지 불가"와 모순되지
않는다 — 그 말은 MinerU의 *인식* 단계 손실 이야기고, 이 검사는 JSON을
정답으로 삼아 MinerU의 *md 생성* 단계 손실을 잡는다. 실측으로 두 논문 모두
page_footnote·footer·aside_text가 md에서 통째로 사라져 있었다.

# ponytail: 빈값 검사(조건 1~5)는 열려 있는 MinerU 이슈 #4311(표 소실)·
# #3849(페이지 소실) 때문에 존재한다. 두 이슈가 닫히면 그 부분은 지운다.
"""

from __future__ import annotations

import re

from pdf2md.strict import Violation

# 실측 2편(2026-08-22 Attention, 2026-08-23 AiScientist)에서 나온 타입 전부 +
# PLAN.md가 예고한 미출현 타입 2개. 여기 없는 타입은 스키마가 바뀐 것이므로
# 조용히 통과시키지 않는다 (CLAUDE.md §11.8 — chart 타입 미기재로 오탐 5건).
_KNOWN_TYPES = frozenset({
    "text", "ref_text", "header", "footer", "page_number", "page_footnote",
    "aside_text", "image", "chart", "equation", "table", "list", "code",
})

# md 생성이 버리는 것이 정상인 타입 — 커버리지 검사에서 뺀다. 쪽번호까지
# 경고하면 리포트가 소음에 덮여 진짜 손실을 못 보게 된다.
_FURNITURE_TYPES = frozenset({"page_number"})

# 셀 텍스트가 "글자 + 하이픈"으로 끝남 = 단어가 셀 경계에서 잘렸다는 신호.
# 실측: "Paper Comprehension"이 <td>Paper sion</td><td>Comprehen-</td>가 됐다.
# 숫자 부호(-0.5)·단어 사이 하이픈(adaptive-pruning)은 걸리지 않는다.
_SPLIT_CELL_RE = re.compile(r">\s*([^<>]*[^\W\d_]-)\s*<")

# 문서가 스스로 서식을 가리키는 어휘 (#40). MinerU 응답 어디에도 스타일 정보가
# 없으므로(PLAN Phase 2 P6, 2026-08-23 재확인) 복원은 불가능하고, 독자는 파일이
# 보여줄 수 없는 것을 찾으라는 안내를 읽게 된다. 실측: 신규 논문 표 캡션 2곳에서
# 5건 적중, Attention 논문 0건 — 말뭉치 기준 오탐 없음.
_STYLE_REF_RE = re.compile(
    r"\b(bold|bolded|underlined|italic|italics)\b|\b(?:red|blue|green) values?\b"
    r"|\bin (?:red|blue|green)\b", re.IGNORECASE)

# 커버리지 프로브 길이. 짧을수록 오탐(우연히 md 어딘가와 일치)이 늘고,
# 길수록 md의 재조판(줄바꿈·하이픈 제거)에 걸려 미탐이 는다. 실측 두 논문에서
# 40자가 오탐 0·미탐 0이었다.
_PROBE_LEN = 40


def _blank(block: dict, key: str) -> bool:
    """외부 입력이라 키가 없거나 None일 수 있다 — 전부 빈 것으로 취급한다."""
    return not str(block.get(key) or "").strip()


def _scannable_text(block: dict) -> str:
    """블록이 담은 사람이 읽는 텍스트 전부 — 본문 text + 캡션·각주 리스트."""
    parts = [str(block.get("text") or "")]
    for key in ("table_caption", "table_footnote", "image_caption",
                "image_footnote", "chart_caption", "chart_footnote"):
        value = block.get(key)
        if isinstance(value, list):
            parts += [str(x) for x in value]
        elif value:
            parts.append(str(value))
    return " ".join(parts)


def _alnum(text: str) -> str:
    """영숫자만 남긴다 — md의 이스케이프·공백·줄바꿈 차이를 무시하기 위해."""
    return "".join(c for c in text.lower() if c.isalnum())


def gate_a(content_list: list[dict], markdown: str = "") -> list[Violation]:
    """content_list를 한 번 순회해 손실 흔적을 전부 보고한다 (PLAN.md Gate A 표).

    markdown이 비어 있으면 커버리지 검사(조건 6)는 건너뛴다.
    """
    violations: list[Violation] = []
    prev_page = -1  # 문서는 page_idx 0에서 시작해야 한다 — 아니면 앞 페이지 소실
    md_alnum = _alnum(markdown)
    seen_unknown: set[str] = set()

    for i, block in enumerate(content_list):
        btype = block.get("type")
        # 키가 없으면 직전 페이지로 간주한다 — 간극 오탐을 만들지 않는 쪽으로
        page = block.get("page_idx", max(prev_page, 0))

        # 조건 5: page_idx 연속성 — 간극은 페이지 통째 소실 (#3849 유형)
        if page > prev_page + 1:
            missing = list(range(prev_page + 1, page))
            violations.append(Violation(
                "page lost", page_idx=missing[0], block_index=i,
                detail=f"page_idx jumps {prev_page} -> {page}; missing {missing}",
            ))
        prev_page = max(prev_page, page)

        # 조건 8: 미지의 타입 — 타입당 한 번만. 아래 검사들이 이 블록의 손실
        # 모드를 모른다는 뜻이므로, 통과했다고 안심하면 안 된다는 신호다
        if btype not in _KNOWN_TYPES and btype not in seen_unknown:
            seen_unknown.add(str(btype))
            violations.append(Violation(
                "unknown block type", page_idx=page, block_index=i, severity="warning",
                detail=f"{btype!r} is not in the measured schema — "
                       "no loss check knows this type",
            ))

        # 조건 1·2: 표 — body와 폴백 이미지가 둘 다 비면 소실 (#4311 유형)
        if btype == "table" and _blank(block, "table_body"):
            if _blank(block, "img_path"):
                violations.append(Violation(
                    "table lost", page_idx=page, block_index=i,
                    detail="table_body and img_path both empty",
                ))
            else:
                violations.append(Violation(
                    "table fell back to image", page_idx=page, block_index=i,
                    severity="warning", detail=str(block.get("img_path")),
                ))
        # 조건 7: 표는 살아 있지만 셀 하나가 단어 중간에서 잘림. 격자는 멀쩡하고
        # 값도 비어 있지 않아 위의 빈값 검사로는 원리적으로 안 잡힌다. 표당 한 줄.
        elif btype == "table":
            m = _SPLIT_CELL_RE.search(str(block.get("table_body") or ""))
            if m:
                violations.append(Violation(
                    "table cell split mid-word", page_idx=page, block_index=i,
                    severity="warning",
                    detail=f"cell ends mid-word: {m.group(1)!r} "
                           "— check the cell against the PDF",
                ))
        # 조건 3: 이미지 경로 빔. chart는 실측(2026-08-22)에서 발견된 이미지형 타입 —
        # 같은 손실 모드지만 content(데이터 텍스트)가 남아 있으면 소실이 아니다
        elif btype == "image" and _blank(block, "img_path"):
            violations.append(Violation("image lost", page_idx=page, block_index=i))
        elif btype == "chart" and _blank(block, "img_path") and _blank(block, "content"):
            violations.append(Violation("chart lost", page_idx=page, block_index=i))
        # 조건 4: 수식 내용 빔 — 실측 VLM은 LaTeX를 text 키에 담는다
        # (PLAN 구스키마의 content 키도 계속 인정. 둘 다 비어야 소실)
        elif btype == "equation" and _blank(block, "content") and _blank(block, "text"):
            violations.append(Violation("equation lost", page_idx=page, block_index=i))

        # 조건 9: 문서가 서식을 가리키지만 마크다운은 그것을 보여줄 수 없다 (#40).
        # 실측에서 이 안내는 전부 표 캡션에 있었다 — text 키만 보면 놓친다.
        found = {m.group(0).lower()
                 for m in _STYLE_REF_RE.finditer(_scannable_text(block))}
        if found:
            violations.append(Violation(
                "styling not preserved", page_idx=page, block_index=i,
                severity="warning",
                detail=f"text refers to {', '.join(sorted(found))} — MinerU discards "
                       "bold/italic/underline/colour, so the markdown cannot show it",
            ))

        # 조건 6: JSON에는 있는데 md에는 없는 텍스트 (#36)
        if md_alnum and btype not in _FURNITURE_TYPES:
            probe = _alnum(str(block.get("text") or ""))[:_PROBE_LEN]
            if probe and probe not in md_alnum:
                text = " ".join(str(block["text"]).split())
                violations.append(Violation(
                    "text dropped from markdown", page_idx=page, block_index=i,
                    severity="warning",
                    detail=f"{btype}: {text[:80]}",
                ))

    return violations
