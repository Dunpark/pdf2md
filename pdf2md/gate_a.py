"""Gate A — content_list.json에서 조용한 인식 실패를 감지한다.

md로 내려오면 원리적으로 감지 불가능한 손실(빈 블록·사라진 페이지)을
content_list 1회 순회로 찾아 list[Violation]으로 보고한다. 감지·보고만 하고
절대 고치지 않는다 — 틀린 수식은 없는 수식보다 나쁘다 (CLAUDE.md §3).

# ponytail: 이 검사는 열려 있는 MinerU 이슈 #4311(표 소실)·#3849(페이지 소실)
# 때문에 존재한다. 두 이슈가 닫히면 이 모듈도 지운다.
"""

from __future__ import annotations

from pdf2md.strict import Violation


def _blank(block: dict, key: str) -> bool:
    """외부 입력이라 키가 없거나 None일 수 있다 — 전부 빈 것으로 취급한다."""
    return not str(block.get(key) or "").strip()


def gate_a(content_list: list[dict]) -> list[Violation]:
    """content_list를 한 번 순회해 손실 흔적을 전부 보고한다 (PLAN.md Gate A 표)."""
    violations: list[Violation] = []
    prev_page = -1  # 문서는 page_idx 0에서 시작해야 한다 — 아니면 앞 페이지 소실

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
        # 조건 3: 이미지 경로 빔
        elif btype == "image" and _blank(block, "img_path"):
            violations.append(Violation("image lost", page_idx=page, block_index=i))
        # 조건 4: 수식 내용 빔
        elif btype == "equation" and _blank(block, "content"):
            violations.append(Violation("equation lost", page_idx=page, block_index=i))

    return violations
