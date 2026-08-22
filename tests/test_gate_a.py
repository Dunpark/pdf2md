# Gate A 테스트 — PLAN.md Phase 1의 5개 조건 + 정상 입력 오탐 없음.
# 픽스처는 손으로 만든 파이썬 리터럴이다 (CLAUDE.md §7 — API 호출은 테스트하지 않는다).

from pdf2md.gate_a import gate_a


def _clean():
    """정상적인 content_list — 모든 타입이 내용을 갖고 페이지가 이어진다."""
    return [
        {"type": "text", "page_idx": 0, "text": "Attention Is All You Need", "text_level": 1},
        {"type": "text", "page_idx": 0, "text": "본문 문단.", "text_level": 0},
        {"type": "image", "page_idx": 1, "img_path": "images/fig1.jpg", "img_caption": ["Figure 1"]},
        {"type": "equation", "page_idx": 1, "content": "E = mc^2"},
        {"type": "table", "page_idx": 2, "table_body": "<table><tr><td>1</td></tr></table>",
         "img_path": "images/tbl1.jpg"},
    ]


def test_clean_input_no_false_positives():
    assert gate_a(_clean()) == []


def test_table_lost_is_violation():
    # 조건 1: table_body 빔 + img_path 빔 → 표 전체 소실 (MinerU #4311 유형)
    blocks = [{"type": "table", "page_idx": 0, "table_body": "", "img_path": ""}]
    (v,) = gate_a(blocks)
    assert v.severity == "violation"
    assert v.condition == "table lost"
    assert (v.page_idx, v.block_index) == (0, 0)


def test_table_image_fallback_is_warning():
    # 조건 2: table_body 빔이지만 img_path 있음 → 이미지 폴백, 내용은 남음
    blocks = [{"type": "table", "page_idx": 0, "table_body": "", "img_path": "images/t.jpg"}]
    (v,) = gate_a(blocks)
    assert v.severity == "warning"
    assert v.condition == "table fell back to image"
    assert (v.page_idx, v.block_index) == (0, 0)


def test_image_lost_is_violation():
    # 조건 3: image인데 img_path 빔
    blocks = [{"type": "image", "page_idx": 0, "img_path": ""}]
    (v,) = gate_a(blocks)
    assert v.severity == "violation"
    assert v.condition == "image lost"
    assert (v.page_idx, v.block_index) == (0, 0)


def test_equation_lost_is_violation():
    # 조건 4: equation인데 content 빔
    blocks = [{"type": "equation", "page_idx": 0, "content": ""}]
    (v,) = gate_a(blocks)
    assert v.severity == "violation"
    assert v.condition == "equation lost"
    assert (v.page_idx, v.block_index) == (0, 0)


def test_page_gap_is_violation():
    # 조건 5: page_idx 연속성 끊김 → 페이지 통째 소실 (MinerU #3849 유형)
    blocks = [
        {"type": "text", "page_idx": 0, "text": "p0"},
        {"type": "text", "page_idx": 3, "text": "p3"},  # 1·2 증발
    ]
    (v,) = gate_a(blocks)
    assert v.severity == "violation"
    assert v.condition == "page lost"
    assert v.page_idx == 1  # 사라진 첫 페이지를 가리킨다
    assert v.block_index == 1  # 간극 직후 블록


def test_missing_first_page_is_violation():
    # 첫 블록이 page_idx 0이 아니면 앞 페이지가 통째로 사라진 것
    blocks = [{"type": "text", "page_idx": 2, "text": "starts late"}]
    (v,) = gate_a(blocks)
    assert v.severity == "violation"
    assert v.condition == "page lost"
    assert (v.page_idx, v.block_index) == (0, 0)


def test_missing_field_counts_as_empty():
    # 신뢰할 수 없는 외부 입력 — 키 자체가 없어도 빈 것으로 취급한다 (CLAUDE.md §7)
    blocks = [{"type": "equation", "page_idx": 0}]
    (v,) = gate_a(blocks)
    assert v.condition == "equation lost"


def test_multiple_violations_all_reported():
    # 여러 손실이 있으면 전부 나온다 — 첫 건에서 멈추지 않는다
    blocks = [
        {"type": "table", "page_idx": 0, "table_body": "", "img_path": ""},
        {"type": "image", "page_idx": 0, "img_path": ""},
        {"type": "equation", "page_idx": 0, "content": ""},
    ]
    assert [v.condition for v in gate_a(blocks)] == ["table lost", "image lost", "equation lost"]
