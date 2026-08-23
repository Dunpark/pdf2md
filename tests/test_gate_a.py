# Gate A 테스트 — PLAN.md Phase 1의 5개 조건 + 정상 입력 오탐 없음.
# 픽스처는 손으로 만든 파이썬 리터럴이다 (CLAUDE.md §7 — API 호출은 테스트하지 않는다).

from pdf2md.gate_a import gate_a


def _clean():
    """정상적인 content_list — 실측 VLM 스키마 (2026-08-22, 실제 응답 기준)."""
    return [
        {"type": "text", "page_idx": 0, "text": "Attention Is All You Need", "text_level": 1},
        {"type": "text", "page_idx": 0, "text": "본문 문단."},
        {"type": "image", "page_idx": 1, "img_path": "images/fig1.jpg",
         "image_caption": ["Figure 1"], "content": ""},
        {"type": "equation", "page_idx": 1, "text": "$$E = mc^2$$", "text_format": "latex"},
        {"type": "table", "page_idx": 2, "table_body": "<table><tr><td>1</td></tr></table>",
         "img_path": "images/tbl1.jpg"},
        {"type": "chart", "page_idx": 2, "img_path": "images/chart.jpg", "content": "csv,here"},
        {"type": "ref_text", "page_idx": 2, "text": "[1] some paper"},
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
    # 조건 4: equation인데 내용 빔. 실측 VLM은 LaTeX를 text 키에 담는다 —
    # text·content 둘 다 비어야 소실이다
    blocks = [{"type": "equation", "page_idx": 0, "text": "", "text_format": "latex"}]
    (v,) = gate_a(blocks)
    assert v.severity == "violation"
    assert v.condition == "equation lost"
    assert (v.page_idx, v.block_index) == (0, 0)


def test_equation_with_text_key_is_not_lost():
    # 실측 스키마 오탐 재발 방지 — text에 LaTeX가 있으면 content가 없어도 정상
    blocks = [{"type": "equation", "page_idx": 0, "text": "$$x$$", "text_format": "latex"}]
    assert gate_a(blocks) == []


def test_equation_with_legacy_content_key_is_not_lost():
    # PLAN 구스키마(content 키)도 계속 정상으로 취급한다
    blocks = [{"type": "equation", "page_idx": 0, "content": "x^2"}]
    assert gate_a(blocks) == []


def test_chart_lost_is_violation():
    # 실측에서 발견된 chart 타입 — image와 같은 손실 모드 (img_path 빔)
    blocks = [{"type": "chart", "page_idx": 0, "img_path": "", "content": ""}]
    (v,) = gate_a(blocks)
    assert v.severity == "violation"
    assert v.condition == "chart lost"


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


# ---------- 조건 6: md 커버리지 — content_list에는 있는데 md에 없는 텍스트 (#36) ----------

def test_text_present_in_json_but_missing_from_markdown_is_warning():
    # 실측: MinerU의 md 생성이 page_footnote·footer·aside_text를 통째로 버린다.
    # 블록은 전부 비어 있지 않으므로 기존 빈값 검사로는 원리적으로 안 잡힌다.
    blocks = [
        {"type": "text", "page_idx": 0, "text": "본문은 살아남았다."},
        {"type": "page_footnote", "page_idx": 0,
         "text": "<sup>4</sup>To illustrate why the dot products get large, assume that"},
    ]
    (v,) = gate_a(blocks, "본문은 살아남았다.")
    assert v.severity == "warning"
    assert v.condition == "text dropped from markdown"
    assert (v.page_idx, v.block_index) == (0, 1)
    assert "dot products" in v.detail


def test_coverage_ignores_formatting_differences():
    # md는 이스케이프·줄바꿈·공백을 바꾼다 — 영숫자만 비교해 오탐을 만들지 않는다
    blocks = [{"type": "page_footnote", "page_idx": 0,
               "text": "<sup>∗</sup>Equal Contributions. Corresponding authors."}]
    md = "text before\n\n<sup>\\*</sup>Equal   Contributions.\nCorresponding authors.\n"
    assert gate_a(blocks, md) == []


def test_page_number_is_never_reported_as_dropped():
    # 쪽번호는 md에서 빠지는 것이 정상이다 — 경고를 내면 리포트가 소음으로 덮인다
    blocks = [{"type": "page_number", "page_idx": 0, "text": "7"}]
    assert gate_a(blocks, "") == []
    assert gate_a(blocks, "본문") == []


def test_coverage_check_off_when_markdown_not_given():
    # markdown 인자가 없으면 검사 자체를 하지 않는다 (기존 호출부 호환)
    blocks = [{"type": "page_footnote", "page_idx": 0, "text": "사라진 각주 " * 10}]
    assert gate_a(blocks) == []


# ---------- 조건 7: 표 셀이 단어 중간에서 잘림 (#36) ----------

def test_table_cell_split_mid_word_is_warning():
    # 실측: "Paper Comprehension"이 <td>Paper sion</td><td>Comprehen-</td>로 쪼개졌다.
    # 격자는 직사각형이고 값도 비어 있지 않아 기존 조건은 하나도 걸리지 않는다.
    blocks = [{"type": "table", "page_idx": 4, "img_path": "images/t.jpg",
               "table_body": "<table><tr><td>Paper sion</td><td>Comprehen-</td></tr></table>"}]
    (v,) = [x for x in gate_a(blocks) if x.condition == "table cell split mid-word"]
    assert v.severity == "warning"
    assert v.condition == "table cell split mid-word"
    assert (v.page_idx, v.block_index) == (4, 0)
    assert "Comprehen-" in v.detail


def test_table_cell_split_reported_once_per_table():
    # 한 표에서 같은 절단이 10번 나와도 리포트는 표 하나에 한 줄이다
    row = "<tr><td>a</td><td>Comprehen-</td></tr>"
    blocks = [{"type": "table", "page_idx": 0, "img_path": "i.jpg",
               "table_body": f"<table>{row * 5}</table>"}]
    assert [v.condition for v in gate_a(blocks)] == ["table cell split mid-word"]


def test_hyphen_in_normal_cells_is_not_a_split():
    # 하이픈이 단어 사이나 숫자 부호로 쓰인 것은 절단이 아니다 — 오탐 금지
    body = ("<table><tr><td>adaptive-pruning</td><td>-</td><td>-0.5</td>"
            "<td>Gemini-3-Flash</td><td></td></tr></table>")
    blocks = [{"type": "table", "page_idx": 0, "img_path": "i.jpg", "table_body": body}]
    assert gate_a(blocks) == []


# ---------- 조건 8: 미지의 블록 타입 (#36) ----------

def test_unknown_block_type_is_warning():
    # §11.8 함정 재발 방지 — 스키마가 늘면 조용히 통과시키지 않고 알린다
    blocks = [{"type": "formula_caption", "page_idx": 0, "text": "..."}]
    (v,) = gate_a(blocks)
    assert v.severity == "warning"
    assert v.condition == "unknown block type"
    assert "formula_caption" in v.detail


def test_unknown_block_type_reported_once_per_type():
    blocks = [{"type": "widget", "page_idx": 0, "text": "x"} for _ in range(4)]
    assert len(gate_a(blocks)) == 1


def test_all_measured_types_are_known():
    # 실측 2편(2026-08-22·23)에서 나온 타입 전부 — 하나라도 미지로 잡히면 안 된다
    measured = ["text", "ref_text", "header", "footer", "page_number", "page_footnote",
                "aside_text", "image", "chart", "equation", "table", "list", "code"]
    blocks = [{"type": t, "page_idx": 0, "text": "x", "img_path": "i.jpg",
               "content": "c", "table_body": "<table><tr><td>c</td></tr></table>"}
              for t in measured]
    assert [v for v in gate_a(blocks) if v.condition == "unknown block type"] == []
