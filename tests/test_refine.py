"""Phase 3 정제 규칙 R1~R3 검증 (PLAN.md Phase 3).

원칙: 절대 내용을 잃지 않는다 — 확신 없는 변환은 원본 유지 + 경고,
수식은 어떤 규칙으로도 건드리지 않는다.
"""

from __future__ import annotations

from pdf2md.refine import refine


# ---------- R1: HTML 표 → GFM 파이프 테이블 ----------

def test_simple_table_becomes_pipe():
    md, notes = refine('<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>')
    assert notes == []
    lines = md.strip().splitlines()
    assert lines[0] == "| A | B |"
    assert set(lines[1].replace("|", "").strip()) <= {"-", " "}  # 구분선
    assert lines[2] == "| 1 | 2 |"


def test_rowspan_colspan_expand_without_losing_content():
    # Table 2 실측 축소판: rowspan 헤더 + colspan 그룹 헤더
    html = ('<table><tr><td rowspan="2">Model</td><td colspan="2">BLEU</td></tr>'
            "<tr><td>EN-DE</td><td>EN-FR</td></tr>"
            "<tr><td>Base</td><td>27.3</td><td>38.1</td></tr></table>")
    md, notes = refine(html)
    assert notes == []
    lines = md.strip().splitlines()
    assert lines[0] == "| Model | BLEU | BLEU |"  # colspan 복제 전개
    assert lines[2] == "| Model | EN-DE | EN-FR |"  # rowspan 복제 전개
    assert lines[3] == "| Base | 27.3 | 38.1 |"


def test_unparseable_table_kept_as_is_with_warning():
    html = "<table>깨진 표, 행이 없다</table>"
    md, notes = refine(html)
    assert html in md  # 원본 무손실
    assert len(notes) == 1 and "table" in notes[0]


def test_cell_pipe_escaped_and_entities_unescaped():
    html = "<table><tr><td>a|b</td><td>x &amp; y</td></tr><tr><td>1</td><td>2</td></tr></table>"
    md, _ = refine(html)
    assert "a\\|b" in md and "x & y" in md


def test_cell_inline_math_survives():
    html = "<table><tr><td>c</td></tr><tr><td> $O(n^{2} \\cdot d)$ </td></tr></table>"
    md, _ = refine(html)
    assert "$O(n^{2} \\cdot d)$" in md


# ---------- R2: 참조 앵커 + 인용 링크 ----------

REFS = "\n\n## References\n\n[1] First paper.\n\n[2] Second paper.\n"


def test_citation_linked_and_reference_anchored():
    md, _ = refine("As shown in [1], attention works." + REFS)
    assert "[[1](#ref-1)]" in md
    assert '<a id="ref-1"></a>[1] First paper.' in md
    assert '<a id="ref-2"></a>[2] Second paper.' in md


def test_citation_group_linked_individually():
    md, _ = refine("such as [1, 2]." + REFS)
    assert "[[1](#ref-1), [2](#ref-2)]" in md


def test_unknown_number_untouched():
    md, _ = refine("array index [9] is not a citation." + REFS)
    assert "[9]" in md and "#ref-9" not in md


def test_reference_entries_themselves_not_linked():
    md, _ = refine("body [1]." + REFS)
    assert "[[1](#ref-1)] First paper." not in md


def test_no_references_section_means_no_linking():
    md, notes = refine("just text with [1] and no refs.")
    assert "#ref-" not in md


# ---------- 수식 불가침 ----------

def test_math_is_never_touched():
    math_md = ("$$\n\\operatorname{FFN}(x) = \\max(0, x W_{1} + b_{1}) W_{2} + b_{2}\\tag{2}\n$$\n"
               "inline $q \\cdot k = \\sum_{i=1}^{d_k} q_i k_i$ stays.\n")
    md, _ = refine(math_md + REFS)
    assert math_md in md  # 수식 구간은 바이트 단위로 그대로


def test_citation_like_text_inside_math_untouched():
    md, _ = refine("$$\nW [1] X\n$$\n" + REFS)
    assert "W [1] X" in md and "[[1](#ref-1)] X" not in md


# ---------- R3: 헤딩 깊이 ----------

def test_heading_depth_follows_section_numbering():
    src = "## 1 Introduction\n\n## 3.1 Encoder\n\n## 3.2.1 Scaled Dot-Product Attention\n\n## Abstract\n"
    md, _ = refine(src)
    assert "## 1 Introduction" in md
    assert "### 3.1 Encoder" in md
    assert "#### 3.2.1 Scaled Dot-Product Attention" in md
    assert "\n## Abstract" in md  # 번호 없는 헤딩은 그대로
