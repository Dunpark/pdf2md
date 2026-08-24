"""Phase 3 정제 규칙 R1~R5 검증 (PLAN.md Phase 3).

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


def test_rowspan_colspan_merge_into_one_header_row():
    # Table 2 실측 축소판: rowspan 헤더 + colspan 그룹 헤더.
    # 값 복제는 각 열이 그 값을 가진 것처럼 읽혀 #40에서 폐기했다.
    html = ('<table><tr><td rowspan="2">Model</td><td colspan="2">BLEU</td></tr>'
            "<tr><td>EN-DE</td><td>EN-FR</td></tr>"
            "<tr><td>Base</td><td>27.3</td><td>38.1</td></tr></table>")
    md, notes = refine(html)
    assert notes == []
    lines = md.strip().splitlines()
    assert lines[0] == "| Model | BLEU EN-DE | BLEU EN-FR |"  # 헤더 2행을 열별로 합침
    assert lines[2] == "| Base | 27.3 | 38.1 |"
    assert len(lines) == 3


def test_unparseable_table_kept_as_is_with_warning():
    html = "<table>깨진 표, 행이 없다</table>"
    md, notes = refine(html)
    assert html in md  # 원본 무손실
    (table_note,) = [n for n in notes if n.startswith("table left as HTML")]
    assert "could not convert" in table_note
    # R5도 함께 운다 — 변환 못 한 표는 HTML로 남아 뷰어를 코드 모드로 만든다 (#38)
    assert [n for n in notes if "HTML (<table>)" in n]


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


def test_citation_linked_and_reference_gets_heading():
    # Orca 실측(2026-08-22): HTML 앵커 점프 미지원, 헤딩 슬러그 링크만 동작.
    # 번호만 든 미니 헤딩이라 슬러그(#18)가 뷰어 구현과 무관하게 결정적이다.
    md, _ = refine("As shown in [1], attention works." + REFS)
    assert "[[1](#1)]" in md
    assert "###### [1]\nFirst paper." in md
    assert "###### [2]\nSecond paper." in md
    assert "<a id=" not in md  # HTML 앵커는 쓰지 않는다


def test_citation_group_linked_individually():
    md, _ = refine("such as [1, 2]." + REFS)
    assert "[[1](#1), [2](#2)]" in md


def test_unknown_number_untouched():
    md, _ = refine("array index [9] is not a citation." + REFS)
    assert "[9]" in md and "(#9)" not in md


def test_reference_entries_themselves_not_linked():
    md, _ = refine("body [1]." + REFS)
    assert "[[1](#1)]\nFirst paper." not in md
    assert "###### [[1](#1)]" not in md


def test_no_footnote_syntax_ever_emitted():
    # Orca는 각주 정의([^N]:)가 있으면 파일 전체를 코드 모드로 강제한다 — 금지
    md, _ = refine("cite [1] and [2]." + REFS)
    assert "[^" not in md


def test_no_references_section_means_no_linking():
    md, notes = refine("just text with [1] and no refs.")
    assert "(#1)" not in md


# ---------- 수식 불가침 ----------

def test_math_is_never_touched():
    math_md = ("$$\n\\operatorname{FFN}(x) = \\max(0, x W_{1} + b_{1}) W_{2} + b_{2}\\tag{2}\n$$\n"
               "inline $q \\cdot k = \\sum_{i=1}^{d_k} q_i k_i$ stays.\n")
    md, _ = refine(math_md + REFS)
    assert math_md in md  # 수식 구간은 바이트 단위로 그대로


def test_citation_like_text_inside_math_untouched():
    md, _ = refine("$$\nW [1] X\n$$\n" + REFS)
    assert "W [1] X" in md and "[[1](#1)] X" not in md


# ---------- R3: 헤딩 깊이 ----------

def test_heading_depth_follows_section_numbering():
    src = "## 1 Introduction\n\n## 3.1 Encoder\n\n## 3.2.1 Scaled Dot-Product Attention\n\n## Abstract\n"
    md, _ = refine(src)
    assert "## 1 Introduction" in md
    assert "### 3.1 Encoder" in md
    assert "#### 3.2.1 Scaled Dot-Product Attention" in md
    assert "\n## Abstract" in md  # 번호 없는 헤딩은 그대로


def test_heading_depth_handles_trailing_dot_and_appendix_letters():
    # 논문마다 번호 서식이 다르다 (#36): "3.1." 처럼 끝에 점을 찍거나
    # 부록을 "A.1." 처럼 문자로 매긴다. 둘 다 평탄화되면 안 된다.
    src = ("## 1. Introduction\n\n## 3.1. Overview\n\n## 3.2.1. Detail\n\n"
           "## A. Additional Related Work\n\n## A.1. Automating AI Research\n")
    md, _ = refine(src)
    assert "## 1. Introduction" in md and "### 1. Introduction" not in md
    assert "### 3.1. Overview" in md
    assert "#### 3.2.1. Detail" in md
    assert "## A. Additional Related Work" in md and "### A. Additional" not in md
    assert "### A.1. Automating AI Research" in md


def test_unnumbered_heading_with_a_dot_is_left_alone():
    # "Fig. 1" 같은 평문 헤딩을 번호로 오인하지 않는다
    src = "## References\n\n## Acknowledgements\n"
    md, _ = refine(src)
    assert md == src


# ---------- R4: <sup> 해제 (#38) ----------

def test_superscript_digits_become_unicode():
    md, notes = refine("See footnote<sup>4</sup> and note<sup>12</sup>.")
    assert md == "See footnote⁴ and note¹².", md
    assert "<sup>" not in md


def test_superscript_symbols_keep_the_bare_character():
    # ∗ † ‡ 는 유니코드 위첨자 자형이 없다 — 문자만 남기고 태그만 벗긴다
    md, _ = refine("Ashish Vaswani<sup>∗</sup> Aidan Gomez<sup>∗</sup> <sup>†</sup>")
    assert md == "Ashish Vaswani∗ Aidan Gomez∗ †"


def test_superscript_conversion_is_one_aggregated_note():
    # 태그마다 한 줄이면 11줄 소음이 된다 — 실행당 한 줄로 모은다
    md, notes = refine("a<sup>1</sup>b<sup>2</sup>c<sup>3</sup>")
    assert md == "a¹b²c³"
    assert len(notes) == 1 and "3" in notes[0] and "superscript" in notes[0]


def test_no_superscript_means_no_note():
    _, notes = refine("plain text\n")
    assert notes == []


def test_superscript_inside_math_is_untouched():
    # 수식은 어떤 규칙으로도 건드리지 않는다 (Attention 논문 79행에 <sup>과 $가 공존)
    src = "value $a<sup>4</sup>b$ and outside<sup>4</sup>\n"
    md, _ = refine(src)
    assert "$a<sup>4</sup>b$" in md
    assert "outside⁴" in md


def test_superscript_inside_display_math_is_untouched():
    src = "$$\nx<sup>2</sup>\n$$\n\ntext<sup>2</sup>\n"
    md, _ = refine(src)
    assert "x<sup>2</sup>" in md
    assert "text²" in md


# ---------- R5: 남은 HTML 경고 (#38) ----------

def test_leftover_html_is_warned_once_per_tag():
    md, notes = refine("line<br>one<br>two<i>three</i>\n")
    assert "<br>" in md  # 내용은 그대로 둔다 — 확신 없는 변환은 하지 않는다
    html_notes = [n for n in notes if "HTML" in n]
    assert len(html_notes) == 1
    assert "br" in html_notes[0] and "i" in html_notes[0]
    assert "code mode" in html_notes[0]


def test_clean_markdown_gets_no_html_warning():
    md, notes = refine("# Title\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n$a < b$ and 3<4\n")
    assert [n for n in notes if "HTML" in n] == []


def test_converted_table_leaves_no_html_warning():
    _, notes = refine("<table><tr><td>A</td></tr><tr><td>1</td></tr></table>")
    assert notes == []


# ---------- R2 author-year 경로 (#40) ----------

AY_REFS = (
    "\n\n## References\n\n"
    "G. Starace, O. Jaffe, and T. Patwardhan. Paperbench. In ICML, 2025.\n\n"
    "S. Schmidgall and M. Moor. AgentRxiv. arXiv preprint arXiv:2503.18102, 2025.\n\n"
    "S. Schmidgall, Y. Su, Z. Wang, and E. Barsoum. Agent laboratory. In EMNLP, 2025.\n\n"
    "G. Chen, F. Meng, and X. Zhao. Beyondswe. arXiv preprint arXiv:2603.03194, 2026a.\n\n"
    "J. Chen, B. D. Mishra, and J. Yoon. Mars. arXiv preprint arXiv:2602.02660, 2026b.\n\n"
    "OpenAI. Introducing upgrades to codex. https://openai.com/index/x, 2025.\n"
)


def test_author_year_citation_becomes_a_slug_link():
    md, _ = refine("On PaperBench (Starace et al., 2025) we see." + AY_REFS)
    assert "([Starace et al., 2025](#starace-et-al-2025))" in md
    assert "###### Starace et al. 2025" in md


def test_author_year_group_linked_individually():
    md, _ = refine("prior work (Starace et al., 2025; OpenAI, 2025)." + AY_REFS)
    assert "[Starace et al., 2025](#starace-et-al-2025)" in md
    assert "[OpenAI, 2025](#openai-2025)" in md


def test_year_suffix_distinguishes_same_surname():
    md, _ = refine("see (Chen et al., 2026a) and (Chen et al., 2026b)." + AY_REFS)
    assert "[Chen et al., 2026a](#chen-et-al-2026a)" in md
    assert "[Chen et al., 2026b](#chen-et-al-2026b)" in md
    assert "###### Chen et al. 2026a" in md and "###### Chen et al. 2026b" in md


def test_two_author_and_et_al_resolve_to_different_entries():
    # 실측 충돌: Schmidgall 2025 항목이 둘이다. 저자 수 신호로 갈라야 하고,
    # 틀린 곳으로 점프하는 링크는 점프 안 하는 링크보다 나쁘다.
    md, _ = refine("(Schmidgall and Moor, 2025) vs (Schmidgall et al., 2025)." + AY_REFS)
    assert "[Schmidgall and Moor, 2025](#schmidgall-and-moor-2025)" in md
    assert "[Schmidgall et al., 2025](#schmidgall-et-al-2025)" in md
    body, refs = md.split("## References")
    assert "###### Schmidgall and Moor 2025\nS. Schmidgall and M. Moor." in refs
    assert "###### Schmidgall et al. 2025\nS. Schmidgall, Y. Su," in refs


def test_unresolvable_citation_stays_plain_and_is_counted():
    md, notes = refine("nobody wrote (Nonesuch et al., 1999) here." + AY_REFS)
    assert "(Nonesuch et al., 1999)" in md and "](#" not in md.split("## References")[0]
    (note,) = [n for n in notes if "citation" in n]
    assert "1" in note


def test_citations_in_an_appendix_after_references_are_linked():
    # 이 논문은 부록이 References 뒤에 온다 — 거기 인용도 본문이다 (#40)
    md, _ = refine("intro (OpenAI, 2025)." + AY_REFS
                   + "\n## A. Appendix\n\nmore (Starace et al., 2025).\n")
    appendix = md.split("## A. Appendix")[1]
    assert "[Starace et al., 2025](#starace-et-al-2025)" in appendix


def test_reference_entries_are_not_linked_to_themselves():
    md, _ = refine("body (OpenAI, 2025)." + AY_REFS)
    refs = md.split("## References")[1]
    assert "](#openai-2025)" not in refs


def test_references_with_no_linked_citation_warns():
    # 이 논문에서 실제로 벌어진 일 — R2가 조용히 아무것도 안 했다
    _, notes = refine("no citations at all here." + AY_REFS)
    assert [n for n in notes if "citation" in n and "0" in n]


def test_numbered_path_still_wins_when_entries_are_numbered():
    md, notes = refine("As shown in [1], attention works." + REFS)
    assert "[[1](#1)]" in md and "###### [1]\nFirst paper." in md
    assert "-et-al-" not in md


# ---------- R1 병합 셀 표현 (#40) ----------

def test_two_row_header_is_joined_into_one():
    # Table 1 실측 축소판: rowspan 헤더 + colspan 그룹 헤더
    html = ('<table><tr><td rowspan="2">Task Name</td><td>GPT-5.5</td>'
            '<td colspan="2">Gemini-3-Flash</td></tr>'
            "<tr><td>Codex</td><td>BasicAgent</td><td>IterAgent</td></tr>"
            "<tr><td>bam</td><td>56.65</td><td>48.46</td><td>45.04</td></tr></table>")
    md, _ = refine(html)
    lines = md.strip().splitlines()
    assert lines[0] == ("| Task Name | GPT-5.5 Codex | Gemini-3-Flash BasicAgent "
                        "| Gemini-3-Flash IterAgent |")
    assert lines[2] == "| bam | 56.65 | 48.46 | 45.04 |"
    assert len(lines) == 3  # 헤더 1행 + 구분선 + 본문 1행


def test_body_colspan_value_appears_once_not_repeated():
    # Table 2 실측: 구간 구분 행이 8번 반복돼 보였다
    html = ('<table><tr><td>Agent</td><td>Model</td><td>Any Medal</td></tr>'
            '<tr><td colspan="3">Official Leaderboard Results</td></tr>'
            "<tr><td>MARS</td><td>Gemini</td><td>74.24</td></tr></table>")
    md, _ = refine(html)
    lines = md.strip().splitlines()
    assert lines[2] == "| Official Leaderboard Results |  |  |"
    assert lines[2].count("Official") == 1


def test_body_rowspan_value_appears_once():
    html = ('<table><tr><td>Group</td><td>Value</td></tr>'
            '<tr><td rowspan="2">A</td><td>1</td></tr>'
            "<tr><td>2</td></tr></table>")
    md, _ = refine(html)
    lines = md.strip().splitlines()
    assert lines[2] == "| A | 1 |"
    assert lines[3] == "|  | 2 |"


def test_merged_cells_lose_no_content():
    html = ('<table><tr><td rowspan="2">Model</td><td colspan="2">BLEU</td></tr>'
            "<tr><td>EN-DE</td><td>EN-FR</td></tr>"
            "<tr><td>Base</td><td>27.3</td><td>38.1</td></tr></table>")
    md, _ = refine(html)
    for value in ("Model", "BLEU", "EN-DE", "EN-FR", "Base", "27.3", "38.1"):
        assert value in md


def test_single_header_row_colspan_is_not_repeated():
    # Table 3 실측: 헤더가 한 행이고 colspan="2"라 "Writer | Writer"로 반복됐다
    html = ('<table><tr><td>Artifact</td><td colspan="2">Writer</td><td>Readers</td></tr>'
            "<tr><td>a.md</td><td>Paper</td><td>Comp</td><td>All</td></tr></table>")
    md, _ = refine(html)
    lines = md.strip().splitlines()
    assert lines[0] == "| Artifact | Writer |  | Readers |"
    assert lines[2] == "| a.md | Paper | Comp | All |"


# ---------- R1 표: 병합이 있는 표만 렌더 이미지로 (#42) ----------

# 병합이 있다 = 마크다운이 표현할 수 없다 -> 이미지로 낸다
T_MERGED = ('<table><tr><td rowspan="2">Task Name</td>'
            '<td colspan="2">Gemini-3-Flash</td></tr>'
            "<tr><td>BasicAgent</td><td>IterAgent</td></tr>"
            "<tr><td>bam</td><td>48.46</td><td>45.04</td></tr></table>")
T2_MERGED = ('<table><tr><td colspan="2">Agent</td></tr>'
             "<tr><td>MARS</td><td>74.24</td></tr></table>")
# 병합이 없다 = 파이프 테이블로 충분하다. 검색·복사·셀 수식 렌더가 살아 있으므로
# 이미지로 바꾸면 얻는 것 없이 셀 텍스트만 잃는다
T_PLAIN = ("<table><tr><td>Layer Type</td><td>Complexity</td></tr>"
           "<tr><td>Self-Attention</td><td> $O(n^{2})$ </td></tr></table>")


def test_merged_table_gets_its_render_image_above_the_table():
    md, notes = refine(T_MERGED, table_images=["images/t1.jpg"])
    assert md.strip().splitlines()[0] == "![](images/t1.jpg)"
    assert "<table" not in md  # HTML은 남지 않는다 (#38)
    assert "| Task Name |" in md  # 표는 그대로 — 셀 텍스트를 잃지 않는다 (#44)
    assert [n for n in notes if "image" in n]


def test_plain_table_stays_a_pipe_table_even_when_an_image_exists():
    # 병합이 없으면 파이프 테이블이 더 낫다 — 검색·복사되고 셀 수식이 렌더된다
    md, notes = refine(T_PLAIN, table_images=["images/plain.jpg"])
    assert "images/plain.jpg" not in md
    assert "| Layer Type | Complexity |" in md
    assert "$O(n^{2})$" in md  # 셀 안 수식이 md에 그대로 남는다
    assert notes == []


def test_mixed_document_splits_by_merge():
    md, notes = refine(T_MERGED + "\n\ntext\n\n" + T_PLAIN,
                       table_images=["images/t1.jpg", "images/plain.jpg"])
    assert "![](images/t1.jpg)" in md
    assert "| Layer Type | Complexity |" in md
    assert "images/plain.jpg" not in md
    (note,) = [n for n in notes if "image" in n]
    assert "1 of 2" in note


def test_image_index_stays_aligned_when_a_plain_table_is_skipped():
    # 짝은 content_list의 표 순서다 — 표로 남긴 표도 자리를 차지한다
    md, _ = refine(T_PLAIN + "\n\n" + T_MERGED,
                   table_images=["images/plain.jpg", "images/t2.jpg"])
    assert "![](images/t2.jpg)" in md
    assert "images/plain.jpg" not in md


def test_each_merged_table_gets_its_own_image_in_order():
    md, _ = refine(T_MERGED + "\n\ntext\n\n" + T2_MERGED,
                   table_images=["images/t1.jpg", "images/t2.jpg"])
    assert md.index("images/t1.jpg") < md.index("text") < md.index("images/t2.jpg")


def test_wrong_image_order_falls_back_to_pipe_table():
    # 표 밑에 엉뚱한 그림이 붙는 것은 조용한 오답이다 — 첫 셀을 대조해 막는다
    md, notes = refine(T_MERGED, table_images=["images/t1.jpg"],
                       table_bodies=["<table><tr><td>Different</td></tr></table>"])
    assert "images/t1.jpg" not in md
    assert "| Task Name | Gemini-3-Flash BasicAgent |" in md
    assert [n for n in notes if "does not match" in n]


def test_matching_first_cell_passes_the_guard():
    md, _ = refine(T_MERGED, table_images=["images/t1.jpg"], table_bodies=[T_MERGED])
    assert md.strip().splitlines()[0] == "![](images/t1.jpg)"


def test_without_images_the_pipe_table_is_unchanged():
    # md 직접 입력(#31)에는 content_list가 없다 — 종전 동작 그대로여야 한다
    md, notes = refine(T_MERGED)
    lines = md.strip().splitlines()
    assert lines[0] == "| Task Name | Gemini-3-Flash BasicAgent | Gemini-3-Flash IterAgent |"
    assert lines[2] == "| bam | 48.46 | 45.04 |"
    assert notes == []


def test_fewer_images_than_tables_leaves_the_rest_as_pipe():
    md, _ = refine(T_MERGED + "\n\n" + T2_MERGED, table_images=["images/t1.jpg"])
    assert "images/t1.jpg" in md
    assert "| Agent |" in md  # 두 번째 표는 짝이 없어 파이프로


def test_merged_table_emits_image_and_table(tmp_path=None):
    # 이미지는 Notion·뷰어에서 폭에 맞춰 축소돼 24행짜리 표는 글자가 7px가 된다.
    # 그림은 배치의 진실을, 표는 읽을 수 있는 값을 맡는다 (#44).
    md, notes = refine(T_MERGED, table_images=["images/t1.jpg"])
    lines = md.strip().splitlines()
    assert lines[0] == "![](images/t1.jpg)"
    assert lines[2] == "| Task Name | Gemini-3-Flash BasicAgent | Gemini-3-Flash IterAgent |"
    assert "| bam | 48.46 | 45.04 |" in md


def test_plain_table_gets_no_image(tmp_path=None):
    md, _ = refine(T_PLAIN, table_images=["images/plain.jpg"])
    assert "images/plain.jpg" not in md
    assert "| Layer Type | Complexity |" in md


def test_table_cell_math_and_citations_survive_the_image(tmp_path=None):
    # #42에서 이미지로만 내면서 잃었던 것 — 셀 텍스트·수식·인용 링크가 돌아온다
    html = ('<table><tr><td colspan="2">Model</td></tr>'
            "<tr><td> $O(n^{2})$ </td><td>see [1]</td></tr></table>")
    md, _ = refine(html + REFS, table_images=["images/t.jpg"])
    assert "![](images/t.jpg)" in md
    assert "$O(n^{2})$" in md
    assert "[[1](#1)]" in md


# ---------- R2 author-year: 저자 서식 편차 (#46) ----------

# 3편째 논문(서베이) 실측 서식. #40 논문은 앞머리 이니셜(`S. Schmidgall`)이었고
# 이 논문은 이름을 통째로 쓴다(`Sahar Abdelnabi`) — 항목을 제1저자 전체 문구로
# 색인하면 인용의 성만으로는 605건 중 4건만 맞았다.
FULLNAME_REFS = (
    "\n\n## References\n\n"
    "Sahar Abdelnabi, Amr Gomaa, and Mario Fritz. LLM-deliberation. In ICLR, 2024.\n\n"
    "Andres M. Bran, Sam Cox, and Philippe Schwaller. Augmenting llms. In Nature, 2024.\n\n"
    "Michael Wooldridge and Nicholas R. Jennings. Intelligent agents. KER, 1995.\n\n"
    "Rik van den Berg and Max Welling. Sylvester flows. In UAI, 2018.\n\n"
    "Jürgen Schmidhuber. What is interesting?, 1997.\n\n"
    "Jürgen Schmidhuber, Jieyu Zhao, and Marco Wiering. Shifting inductive bias, 1997.\n\n"
    "OpenAI. Introducing upgrades to codex. https://openai.com/index/x, 2025.\n"
)


def test_full_given_names_are_indexed_by_surname():
    md, _ = refine("as shown (Abdelnabi et al., 2024)." + FULLNAME_REFS)
    assert "[Abdelnabi et al., 2024](#abdelnabi-et-al-2024)" in md
    assert "###### Abdelnabi et al. 2024" in md


def test_middle_initial_does_not_truncate_the_author():
    # `Andres M. Bran` 의 `M.` 에서 잘리면 성이 `M` 이 되어 인용이 영원히 안 맞는다
    md, _ = refine("tools (M. Bran et al., 2024)." + FULLNAME_REFS)
    assert "[M. Bran et al., 2024](#m-bran-et-al-2024)" in md


def test_ampersand_is_an_author_separator():
    md, _ = refine("agents (Wooldridge & Jennings, 1995)." + FULLNAME_REFS)
    assert "[Wooldridge & Jennings, 1995](#wooldridge-jennings-1995)" in md


def test_multi_word_surname_matches_on_both_sides():
    md, _ = refine("flows (van den Berg & Welling, 2018)." + FULLNAME_REFS)
    assert "[van den Berg & Welling, 2018](#van-den-berg-welling-2018)" in md


def test_single_author_citation_prefers_the_single_author_entry():
    # 같은 성·같은 해 항목이 둘 — 하나는 단독 저자, 하나는 3인. 인용에 et al이
    # 없으면 단독 저자 항목이고, 있으면 3인 항목이다.
    md, _ = refine("(Schmidhuber, 1997) and (Schmidhuber et al., 1997)."
                   + FULLNAME_REFS)
    refs = md.split("## References")[1]
    assert "###### Schmidhuber 1997\nJürgen Schmidhuber. What is interesting?" in refs
    assert ("###### Schmidhuber et al. 1997\n"
            "Jürgen Schmidhuber, Jieyu Zhao, and Marco Wiering.") in refs


def test_ampersand_two_author_form_resolves_the_collision():
    md, _ = refine("(Schmidgall & Moor, 2025) vs (Schmidgall et al., 2025)." + AY_REFS)
    body, refs = md.split("## References")
    assert "[Schmidgall & Moor, 2025](#schmidgall-moor-2025)" in body
    assert "###### Schmidgall & Moor 2025\nS. Schmidgall and M. Moor." in refs
    assert "###### Schmidgall et al. 2025\nS. Schmidgall, Y. Su," in refs


# ---------- R4: <sub> 해제 (#46) ----------

def test_subscript_letters_and_symbols_become_unicode():
    md, notes = refine("signal S<sub>t</sub> and b<sub>t</sub>")
    assert md == "signal Sₜ and bₜ", md
    assert "<sub>" not in md


def test_subscript_without_a_unicode_form_keeps_the_bare_text():
    # MinerU가 표 캡션의 평범한 단어를 <sub>로 잘못 감싼 실측 — 아래첨자 자형이
    # 없으므로 태그만 벗기고 글자는 그대로 둔다
    md, _ = refine("a <sub>mechanism</sub> <sub>as</sub> <sub>primary</sub>")
    assert md == "a mechanism as primary"


def test_sub_and_sup_share_one_aggregated_note():
    md, notes = refine("a<sup>1</sup>b<sub>t</sub>")
    assert md == "a¹bₜ"
    assert len(notes) == 1 and "2" in notes[0]


def test_subscript_inside_math_is_untouched():
    md, _ = refine("value $a<sub>t</sub>b$ and outside<sub>t</sub>\n")
    assert "$a<sub>t</sub>b$" in md
    assert "outsideₜ" in md


# ---------- R6: MinerU code 블록의 HTML 껍데기 → 코드 펜스 (#46) ----------

ALGO = (r'<div class="mineru-algorithm" style="white-space: pre-wrap; '
        'font-family:monospace;">\n'
        "Algorithm 1: Improvement\n"
        r"for $t \leftarrow 0$ to $T - 1$ do" "\n"
        "    // step\n"
        "</div>\n")


def test_mineru_algorithm_div_becomes_a_code_fence():
    md, notes = refine(ALGO)
    assert "<div" not in md and "</div>" not in md
    lines = md.strip().splitlines()
    assert lines[0] == "```" and lines[-1] == "```"
    assert lines[1] == "Algorithm 1: Improvement"
    assert lines[3] == "    // step"  # 들여쓰기가 뜻을 나르므로 그대로 남는다


def test_code_fence_conversion_is_warned_once():
    md, notes = refine(ALGO + "\n" + ALGO)
    fence_notes = [n for n in notes if "code" in n]
    assert len(fence_notes) == 1 and "2" in fence_notes[0]


def test_code_fence_leaves_no_leftover_html_warning():
    _, notes = refine(ALGO)
    assert [n for n in notes if "HTML" in n] == []
