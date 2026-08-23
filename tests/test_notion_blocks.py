"""to_blocks (#16) — 완전 오프라인.

픽스처 파일 없음: output/은 gitignore라 실물 md를 커밋할 수 없다.
테스트 상수는 전부 인라인 문자열 (티켓 #16 Verification).
"""

import pytest

from pdf2md.notion_blocks import to_blocks
from pdf2md.strict import Pdf2mdError


def _texts(block):
    """블록 하나에서 rich_text 텍스트 content를 전부 뽑는다 (표 셀 포함)."""
    out = []
    btype = block["type"]
    if btype == "table":
        for row in block["table"]["children"]:
            for cell in row["table_row"]["cells"]:
                out += [e["text"]["content"] for e in cell if e["type"] == "text"]
    elif btype in ("equation", "image"):
        pass
    else:
        out += [e["text"]["content"] for e in block[btype]["rich_text"]
                if e["type"] == "text"]
    return out


# ---------- 헤딩 ----------

def test_headings_map_and_clamp(tmp_path):
    doc = to_blocks("# T\n\n## A\n\n### B\n\n#### C\n", tmp_path)
    assert [b["type"] for b in doc.blocks] == [
        "heading_1", "heading_2", "heading_3", "heading_3"]
    assert doc.blocks[3]["heading_3"]["rich_text"][0]["text"]["content"] == "C"
    assert any("clamp" in w for w in doc.warnings)  # ####는 경고와 함께 강등


# ---------- 문단·불릿 ----------

def test_paragraph_and_bullet(tmp_path):
    doc = to_blocks("hello world\n\n• item one\n", tmp_path)
    assert doc.blocks[0]["type"] == "paragraph"
    assert doc.blocks[0]["paragraph"]["rich_text"] == [
        {"type": "text", "text": {"content": "hello world"}}]
    assert doc.blocks[1]["type"] == "bulleted_list_item"
    assert doc.blocks[1]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "item one"


def test_2500_char_paragraph_splits_lossless(tmp_path):
    # reference/가 content[:2000]으로 잘라먹던 바로 그 지점 — 분할이며 무손실이어야 한다
    text = "ab" * 1250
    doc = to_blocks(text, tmp_path)
    rt = doc.blocks[0]["paragraph"]["rich_text"]
    assert len(rt) == 2
    assert all(len(e["text"]["content"]) <= 2000 for e in rt)
    assert "".join(e["text"]["content"] for e in rt) == text


# ---------- 수식 ----------

def test_display_equation_bytes_identical(tmp_path):
    expr = (r"\operatorname{Attention} (Q, K, V) = \operatorname{softmax} "
            r"(\frac {Q K ^ {T}}{\sqrt {d _ {k}}}) V\tag{1}")
    doc = to_blocks(f"$$\n{expr}\n$$\n", tmp_path)
    assert doc.blocks == [{"type": "equation", "equation": {"expression": expr}}]


def test_multiline_display_equation_preserves_backslashes(tmp_path):
    expr = "a \\\\\nb"  # 두 줄 수식, 행바꿈 \\ 포함 — 바이트 그대로
    doc = to_blocks(f"$$\n{expr}\n$$\n", tmp_path)
    assert doc.blocks[0]["equation"]["expression"] == expr


def test_inline_equation_verbatim(tmp_path):
    # MinerU 잔재($d _ { k } ,$)를 정리하지 않는다 — $ 사이 바이트 그대로
    doc = to_blocks("dim $d _ { k } ,$ , stays", tmp_path)
    rt = doc.blocks[0]["paragraph"]["rich_text"]
    assert rt == [
        {"type": "text", "text": {"content": "dim "}},
        {"type": "equation", "equation": {"expression": "d _ { k } ,"}},
        {"type": "text", "text": {"content": " , stays"}},
    ]


def test_equation_1000_limit(tmp_path):
    ok = "x" * 999
    doc = to_blocks(f"$$\n{ok}\n$$", tmp_path)
    assert doc.blocks[0]["equation"]["expression"] == ok
    with pytest.raises(Pdf2mdError):
        to_blocks("$$\n" + "x" * 1001 + "\n$$", tmp_path)


def test_odd_dollar_is_plain_text(tmp_path):
    # 수식 경계를 추정하지 않는다 — 홀수 $는 줄 전체 평문.
    # $가 하나면 짝지을 수식이 없어 평문이 정답이므로 경고하지 않는다 (#44)
    doc = to_blocks("price is $5 today", tmp_path)
    assert doc.blocks[0]["paragraph"]["rich_text"] == [
        {"type": "text", "text": {"content": "price is $5 today"}}]
    assert not any("odd" in w for w in doc.warnings)


# ---------- 이미지 ----------

def test_image_splits_paragraph_in_three(tmp_path):
    # 실물 410행 형태: hard break로 이어진 한 덩어리 안에 이미지가 낀다
    (tmp_path / "f3.jpg").write_bytes(b"x")
    md = "Attention Visualizations  \n![](images/f3.jpg)  \nFigure 3: caption here\n"
    doc = to_blocks(md, tmp_path)
    assert [b["type"] for b in doc.blocks] == ["paragraph", "image", "paragraph"]
    assert doc.images == [(1, tmp_path / "f3.jpg")]
    assert doc.blocks[1]["image"] == {
        "type": "file_upload", "file_upload": {"id": ""}}
    # hard break의 끝 2공백은 문법이지 내용이 아니다
    assert doc.blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == \
        "Attention Visualizations"


def test_missing_image_file_raises(tmp_path):
    with pytest.raises(Pdf2mdError):
        to_blocks("![](images/nope.jpg)", tmp_path)


# ---------- References 병합 ----------

def test_references_merge_and_targets(tmp_path):
    md = ("## References\n\n"
          "###### [1]\nJimmy Lei Ba, layer norm.\n\n"
          "###### [2]\nBahdanau, translate.\n")
    doc = to_blocks(md, tmp_path)
    assert doc.blocks[0]["type"] == "heading_2"
    assert doc.blocks[1]["type"] == "paragraph"  # h6이 아니라 문단으로 병합
    assert doc.blocks[1]["paragraph"]["rich_text"][0]["text"]["content"] == \
        "[1] Jimmy Lei Ba, layer norm."
    assert doc.ref_targets == {"1": 1, "2": 2}


# ---------- 인용 ----------

def test_citations_recorded_and_plain(tmp_path):
    doc = to_blocks("structure [[5](#5), [2](#2)].", tmp_path)
    rt = doc.blocks[0]["paragraph"]["rich_text"]
    # 패치 전이므로 전부 평문 — 읽으면 [5, 2]
    assert "".join(e["text"]["content"] for e in rt) == "structure [5, 2]."
    assert all("link" not in e["text"] for e in rt)
    assert doc.citations == [(0, 1, "5"), (0, 3, "2")]


def test_http_link_kept_citation_absent(tmp_path):
    doc = to_blocks("see [site](https://example.com) now", tmp_path)
    rt = doc.blocks[0]["paragraph"]["rich_text"]
    assert rt[1] == {"type": "text",
                     "text": {"content": "site", "link": {"url": "https://example.com"}}}
    assert doc.citations == []


# ---------- 표 ----------

def test_pipe_table_with_escape_and_cell_math(tmp_path):
    md = ("| Layer | Cost |\n"
          "|---|---|\n"
          "| Self-Attention | $O(n^{2} \\cdot d)$ |\n"
          "| a \\| b | plain |\n")
    doc = to_blocks(md, tmp_path)
    t = doc.blocks[0]
    assert t["type"] == "table"
    assert t["table"]["table_width"] == 2
    assert t["table"]["has_column_header"] is True
    rows = t["table"]["children"]
    assert len(rows) == 3  # 헤더 + 데이터 2 (구분선 행은 표기일 뿐)
    # probe 실측(2026-08-23): 셀 안 equation은 생존·렌더 — 폴백 없이 그대로 넣는다
    assert rows[1]["table_row"]["cells"][1] == [
        {"type": "equation", "equation": {"expression": "O(n^{2} \\cdot d)"}}]
    # R1의 \| 이스케이프 왕복
    assert rows[2]["table_row"]["cells"][0] == [
        {"type": "text", "text": {"content": "a | b"}}]


def test_cell_citation_not_recorded(tmp_path):
    # table_row는 2단계 블록이라 #19가 패치할 수 없다 — 평문 유지 + 경고
    md = "| Model | Ref |\n|---|---|\n| ByteNet | [[15](#15)] |\n"
    doc = to_blocks(md, tmp_path)
    assert doc.citations == []
    cell = doc.blocks[0]["table"]["children"][1]["table_row"]["cells"][1]
    assert "".join(e["text"]["content"] for e in cell) == "[15]"
    assert any("table cell" in w for w in doc.warnings)


def test_two_row_header_warns(tmp_path):
    # Table 2 형태: rowspan 전개로 1행 값이 0행에 반복된다
    md = ("| Model | BLEU | BLEU |\n"
          "|---|---|---|\n"
          "| Model | EN-DE | EN-FR |\n"
          "| ByteNet | 23.75 | 39.2 |\n")
    doc = to_blocks(md, tmp_path)
    assert any("two-row header" in w for w in doc.warnings)


def test_ragged_table_raises(tmp_path):
    with pytest.raises(Pdf2mdError):
        to_blocks("| a | b |\n|---|---|\n| only-one |\n", tmp_path)


def test_empty_cell_is_empty_array(tmp_path):
    doc = to_blocks("| a |  |\n|---|---|\n| b | c |\n", tmp_path)
    assert doc.blocks[0]["table"]["children"][0]["table_row"]["cells"][1] == []


# ---------- HTML 잔존 ----------

def test_html_table_raises(tmp_path):
    # R1 변환 실패분이 텍스트로 박히면 표가 사라진 것과 같다 — halt
    with pytest.raises(Pdf2mdError):
        to_blocks("<table><tr><td>x</td></tr></table>", tmp_path)


# ---------- <sup> ----------

def test_sup_digits_translate_and_symbols_kept(tmp_path):
    doc = to_blocks("gradients <sup>4</sup>. Vaswani<sup>∗</sup>", tmp_path)
    content = doc.blocks[0]["paragraph"]["rich_text"][0]["text"]["content"]
    assert content == "gradients ⁴. Vaswani∗"
    assert any("sup" in w for w in doc.warnings)


# ---------- 한도 ----------

def test_rich_text_array_over_100_raises(tmp_path):
    # 수식 51개 + 사이 텍스트 50개 = 101 요소 — 분할기를 만들지 않고 halt
    md = " ".join("$x$" for _ in range(51))
    with pytest.raises(Pdf2mdError):
        to_blocks(md, tmp_path)


# ---------- 종합: 마크다운 문법이 텍스트로 살아남지 않는다 ----------

def test_no_markdown_syntax_survives(tmp_path):
    (tmp_path / "x.jpg").write_bytes(b"x")
    md = ("Provided proper attribution is provided.\n"
          "\n"
          "# Attention Is All You Need\n"
          "\n"
          "## 3 Model Architecture\n"
          "\n"
          "models [[5](#5)]. maps $( x _ { 1 } , . . . , x _ { n } )$ to z.\n"
          "\n"
          "intro  \n![](images/x.jpg)  \nFigure 1: caption\n"
          "\n"
          "$$\nE = m c ^ { 2 } \\tag{1}\n$$\n"
          "\n"
          "• bullet [[2](#2)]\n"
          "\n"
          "| h | h2 |\n|---|---|\n| $a$ | b |\n"
          "\n"
          "## References\n"
          "\n"
          "###### [2]\nBahdanau.\n"
          "\n"
          "###### [5]\nSutskever.\n")
    doc = to_blocks(md, tmp_path)
    for b in doc.blocks:
        for t in _texts(b):
            assert "![" not in t and "](#" not in t and "$$" not in t \
                and "######" not in t and "<sup>" not in t
    assert doc.ref_targets.keys() == {"2", "5"}
    # 본문 인용은 전부 실재하는 참조 번호를 가리킨다
    assert {n for _, _, n in doc.citations} <= doc.ref_targets.keys()
    assert sum(1 for b in doc.blocks if b["type"] == "image") == 1
    assert sum(1 for b in doc.blocks if b["type"] == "equation") == 1
    assert sum(1 for b in doc.blocks if b["type"] == "table") == 1


# ---------- 페이지 제목 (#25) ----------

def test_first_h1_becomes_doc_title(tmp_path):
    doc = to_blocks("preamble text\n\n# My Paper Title\n\nbody\n\n# Second H1\n", tmp_path)
    assert doc.title == "My Paper Title"  # 첫 h1만 — 뒤의 h1은 제목이 아니다
    # h1 블록 자체는 그대로 업로드된다 (무손실 원칙, 제목은 메타데이터일 뿐)
    assert any(b["type"] == "heading_1" for b in doc.blocks)


def test_no_h1_leaves_title_empty(tmp_path):
    doc = to_blocks("just a paragraph\n\n## section\n", tmp_path)
    assert doc.title == ""


# ---------- author-year 인용 경로 (#44) ----------

def test_author_year_reference_merges_and_targets_by_slug(tmp_path):
    # 실측: 숫자형만 인식해서 author-year 미니 헤딩 43개가 heading_3으로 뭉개졌고
    # ref_targets가 비어 인용이 갈 곳을 잃었다 (#44)
    md = ("## References\n\n"
          "###### Starace et al. 2025\nG. Starace, O. Jaffe. Paperbench. 2025.\n\n"
          "###### Schmidgall and Moor 2025\nS. Schmidgall and M. Moor. AgentRxiv. 2025.\n")
    doc = to_blocks(md, tmp_path)
    assert [b["type"] for b in doc.blocks] == ["heading_2", "paragraph", "paragraph"]
    assert doc.ref_targets == {"starace-et-al-2025": 1, "schmidgall-and-moor-2025": 2}
    # 항목 전문은 그대로 — 숫자형과 달리 앞에 라벨을 덧붙이지 않는다
    assert doc.blocks[1]["paragraph"]["rich_text"][0]["text"]["content"] == \
        "G. Starace, O. Jaffe. Paperbench. 2025."
    assert not [w for w in doc.warnings if "clamped" in w]


def test_author_year_citation_recorded_not_dropped(tmp_path):
    doc = to_blocks("prior work ([Starace et al., 2025](#starace-et-al-2025)).", tmp_path)
    rt = doc.blocks[0]["paragraph"]["rich_text"]
    assert "".join(e["text"]["content"] for e in rt) == \
        "prior work (Starace et al., 2025)."
    assert doc.citations == [(0, 1, "starace-et-al-2025")]
    assert not [w for w in doc.warnings if "dropped unsupported link" in w]


def test_numeric_reference_path_unchanged(tmp_path):
    md = "## References\n\n###### [1]\nJimmy Lei Ba, layer norm.\n"
    doc = to_blocks(md, tmp_path)
    assert doc.ref_targets == {"1": 1}
    assert doc.blocks[1]["paragraph"]["rich_text"][0]["text"]["content"] == \
        "[1] Jimmy Lei Ba, layer norm."


def test_citation_and_reference_keys_meet(tmp_path):
    md = ("body ([Chen et al., 2026a](#chen-et-al-2026a)).\n\n## References\n\n"
          "###### Chen et al. 2026a\nG. Chen. Beyondswe. 2026a.\n")
    doc = to_blocks(md, tmp_path)
    (_, _, key), = doc.citations
    assert key in doc.ref_targets  # 이게 어긋나면 링크가 갈 곳이 없다


def test_unknown_anchor_still_dropped_with_warning(tmp_path):
    doc = to_blocks("see [x](mailto:a@b.c) now", tmp_path)
    assert doc.citations == []
    assert [w for w in doc.warnings if "dropped unsupported link" in w]


# ---------- 이스케이프된 달러 (#44) ----------

def test_escaped_dollar_is_not_a_math_delimiter(tmp_path):
    # 실측: "costs approximately \$832" 한 줄이 통째로 평문으로 떨어졌다
    doc = to_blocks(r"a full evaluation costs approximately \$832, which limits it.",
                    tmp_path)
    rt = doc.blocks[0]["paragraph"]["rich_text"]
    assert not [w for w in doc.warnings if "odd number of" in w]
    assert "".join(e["text"]["content"] for e in rt) == \
        "a full evaluation costs approximately $832, which limits it."


def test_escaped_dollar_beside_real_math(tmp_path):
    doc = to_blocks(r"cost \$832 with $d_k$ dims", tmp_path)
    rt = doc.blocks[0]["paragraph"]["rich_text"]
    assert [e["type"] for e in rt] == ["text", "equation", "text"]
    assert rt[0]["text"]["content"] == "cost $832 with "
    assert rt[1]["equation"]["expression"] == "d_k"


def test_genuinely_odd_dollar_still_warns(tmp_path):
    # $가 셋이면 짝지으려던 수식이 실재한다 — 그건 알린다
    doc = to_blocks("broken $a$ and $b here", tmp_path)
    assert [w for w in doc.warnings if "odd number of" in w]


def test_lone_dollar_is_currency_not_a_warning(tmp_path):
    # 실측: 표의 금액 칸 `$33.05` 7건이 경고를 냈다. 짝지을 수식이 없으므로
    # 평문이 정답이고, 경고는 리포트를 덮는 소음일 뿐이다 (#44)
    doc = to_blocks("| Avg Cost |\n|---|\n| $33.05 |\n", tmp_path)
    assert not [w for w in doc.warnings if "odd number of" in w]
    cells = doc.blocks[0]["table"]["children"][1]["table_row"]["cells"]
    assert cells[0][0]["text"]["content"] == "$33.05"


def test_plain_h6_in_the_body_stays_a_heading(tmp_path):
    # R2의 참조 앵커 형태가 아니면 문단으로 삼키지 않는다 — 조용한 구조 손실 금지
    doc = to_blocks("###### Implementation notes\nsome prose\n", tmp_path)
    assert doc.blocks[0]["type"] == "heading_3"
    assert doc.blocks[1]["type"] == "paragraph"
    assert doc.ref_targets == {}
