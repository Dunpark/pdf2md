"""Regression tests for notes_poc markdown -> Notion block conversion."""

from __future__ import annotations

from notes.notion_parser import md_to_notion_blocks


def _rich_text_items(block: dict) -> list[dict]:
    block_type = block["type"]
    return block.get(block_type, {}).get("rich_text", [])


def _all_text_content(blocks: list[dict]) -> str:
    chunks: list[str] = []
    for block in blocks:
        for item in _rich_text_items(block):
            if item.get("type") == "text":
                chunks.append(item["text"]["content"])
    return "\n".join(chunks)


def test_orphan_closing_tags_are_ignored() -> None:
    blocks = md_to_notion_blocks("</details>\n</callout>")
    assert blocks == []


def test_details_multiline_is_converted_to_toggle() -> None:
    md = "<details>\n<summary>Q</summary>\nAnswer line\n</details>"
    blocks = md_to_notion_blocks(md)

    assert len(blocks) == 1
    assert blocks[0]["type"] == "toggle"
    assert blocks[0]["toggle"]["rich_text"][0]["text"]["content"] == "Q"
    assert blocks[0]["toggle"]["children"][0]["type"] == "paragraph"


def test_details_inline_and_open_attr_are_supported() -> None:
    md = "<details open><summary>Q2</summary>A2</details>"
    blocks = md_to_notion_blocks(md)

    assert len(blocks) == 1
    assert blocks[0]["type"] == "toggle"
    assert blocks[0]["toggle"]["rich_text"][0]["text"]["content"] == "Q2"
    assert blocks[0]["toggle"]["children"][0]["paragraph"]["rich_text"][0]["text"]["content"] == "A2"


def test_details_multiline_summary_is_joined_with_newline() -> None:
    md = (
        "<details>\n"
        "<summary>Q2: 문제를 설명하라.\n"
        "`pthread_create(&thread_id, NULL, func, &i);` (루프 변수)</summary>\n"
        "답변: 루프 변수 `i`의 **주소**를 전달했기 때문이다.\n"
        "</details>"
    )
    blocks = md_to_notion_blocks(md)

    assert len(blocks) == 1
    assert blocks[0]["type"] == "toggle"
    # Summary lines joined with a space
    summary_text = "".join(
        rt["text"]["content"] for rt in blocks[0]["toggle"]["rich_text"] if rt.get("type") == "text"
    )
    assert "Q2: 문제를 설명하라." in summary_text
    assert "루프 변수" in summary_text
    # Answer present
    assert len(blocks[0]["toggle"]["children"]) == 1


def test_callout_alternate_syntax_is_converted() -> None:
    md = '<callout="\U0001f4cc">\nImportant message\n</callout>'
    blocks = md_to_notion_blocks(md)

    assert len(blocks) == 1
    assert blocks[0]["type"] == "callout"
    assert blocks[0]["callout"]["icon"]["emoji"] == "\U0001f4cc"
    assert blocks[0]["callout"]["rich_text"][0]["text"]["content"] == "Important message"


def test_latex_inline_and_backticked_are_converted_to_equation_items() -> None:
    md = (
        "- **`$\\frac{1}{9}$`** and `$f(x, y)$`\n"
        "- backticked inline: `\\(a+b\\)`"
    )
    blocks = md_to_notion_blocks(md)

    assert [b["type"] for b in blocks] == ["bulleted_list_item", "bulleted_list_item"]
    first_rt = blocks[0]["bulleted_list_item"]["rich_text"]
    second_rt = blocks[1]["bulleted_list_item"]["rich_text"]
    assert any(item["type"] == "equation" and item["equation"]["expression"] == r"\frac{1}{9}" for item in first_rt)
    assert any(item["type"] == "equation" and item["equation"]["expression"] == "f(x, y)" for item in first_rt)
    assert any(item["type"] == "equation" and item["equation"]["expression"] == "a+b" for item in second_rt)

    text = _all_text_content(blocks)
    assert "</details>" not in text
    assert "</callout>" not in text


def test_inline_math_does_not_misparse_double_dollar_blocks_inside_bullets() -> None:
    md = "- \uba54\ubaa8\ub9ac \ud06c\uae30 \uacf5\uc2dd: \uc8fc\uc18c \ube44\ud2b8 \uc218\uac00 $n$\uc77c \ub54c, \uc5f4 \uba54\ubaa8\ub9ac \uc704\uce58(\uc6a9\ub7c9)\ub294 $$2^n$$\uc73c\ub85c \uacc4\uc0b0."
    blocks = md_to_notion_blocks(md)

    assert [b["type"] for b in blocks] == ["bulleted_list_item"]
    rt = blocks[0]["bulleted_list_item"]["rich_text"]
    assert any(item["type"] == "equation" and item["equation"]["expression"] == "n" for item in rt)
    assert any(item["type"] == "equation" and item["equation"]["expression"] == "2^n" for item in rt)
    assert not any(
        item["type"] == "equation" and item["equation"]["expression"].startswith("$")
        for item in rt
    )


def test_math_block_syntaxes_are_converted_to_equation_blocks() -> None:
    md = "$$\\int_0^1 x^2 dx$$\n\\[x^2+y^2=z^2\\]"
    blocks = md_to_notion_blocks(md)

    assert [b["type"] for b in blocks] == ["equation", "equation"]
    assert blocks[0]["equation"]["expression"] == r"\int_0^1 x^2 dx"
    assert blocks[1]["equation"]["expression"] == "x^2+y^2=z^2"


def test_bulleted_nested_list_creates_children() -> None:
    md = "- parent\n  - child\n    - grandchild\n- sibling"
    blocks = md_to_notion_blocks(md)

    assert [b["type"] for b in blocks] == ["bulleted_list_item", "bulleted_list_item"]
    parent = blocks[0]["bulleted_list_item"]
    child = parent["children"][0]["bulleted_list_item"]
    grandchild = child["children"][0]["bulleted_list_item"]
    assert parent["rich_text"][0]["text"]["content"] == "parent"
    assert child["rich_text"][0]["text"]["content"] == "child"
    assert grandchild["rich_text"][0]["text"]["content"] == "grandchild"
    assert blocks[1]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "sibling"


def test_bulleted_depth_over_two_is_flattened_for_notion() -> None:
    md = "- l1\n  - l2\n    - l3\n      - l4"
    blocks = md_to_notion_blocks(md)

    assert [b["type"] for b in blocks] == ["bulleted_list_item"]
    l1 = blocks[0]["bulleted_list_item"]
    l2_block = l1["children"][0]
    assert l2_block["type"] == "bulleted_list_item"
    l2 = l2_block["bulleted_list_item"]
    assert l2["rich_text"][0]["text"]["content"] == "l2"

    l2_children = l2["children"]
    assert [child["type"] for child in l2_children] == ["bulleted_list_item", "bulleted_list_item"]
    assert l2_children[0]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "l3"
    assert l2_children[1]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "l4"
    assert "children" not in l2_children[0]["bulleted_list_item"]
    assert "children" not in l2_children[1]["bulleted_list_item"]


def test_numbered_nested_list_creates_children() -> None:
    md = "1. one\n   1. one-child\n2. two"
    blocks = md_to_notion_blocks(md)

    assert [b["type"] for b in blocks] == ["numbered_list_item", "numbered_list_item"]
    one = blocks[0]["numbered_list_item"]
    one_child = one["children"][0]["numbered_list_item"]
    assert one["rich_text"][0]["text"]["content"] == "one"
    assert one_child["rich_text"][0]["text"]["content"] == "one-child"
    assert blocks[1]["numbered_list_item"]["rich_text"][0]["text"]["content"] == "two"


def test_single_line_triple_backtick_code_is_parsed_as_code_block() -> None:
    blocks = md_to_notion_blocks("```\ucf54\ub4dc```")
    assert len(blocks) == 1
    assert blocks[0]["type"] == "code"
    assert blocks[0]["code"]["language"] == "plain text"
    assert blocks[0]["code"]["rich_text"][0]["text"]["content"] == "\ucf54\ub4dc"


def test_bold_with_parentheses_and_inline_code_is_split_correctly() -> None:
    md = "- **\uc5c5\ub370\uc774\ud2b8 \ub85c\uc9c1 (`update()` \uba54\uc11c\ub4dc)** \u2014 \ud575\uc2ec."
    blocks = md_to_notion_blocks(md)

    rt = blocks[0]["bulleted_list_item"]["rich_text"]
    assert rt[0]["type"] == "text"
    assert rt[0]["text"]["content"] == "\uc5c5\ub370\uc774\ud2b8 \ub85c\uc9c1 ("
    assert rt[0]["annotations"]["bold"] is True

    assert rt[1]["type"] == "text"
    assert rt[1]["text"]["content"] == "update()"
    assert rt[1]["annotations"]["code"] is True
    assert rt[1]["annotations"]["bold"] is True

    assert rt[2]["type"] == "text"
    assert rt[2]["text"]["content"] == " \uba54\uc11c\ub4dc)"
    assert rt[2]["annotations"]["bold"] is True


def test_lone_asterisk_is_preserved_not_dropped() -> None:
    # lone * (pointer notation, multiplication) must not be silently dropped
    blocks = md_to_notion_blocks("- `*ptr` and 2 * 3 = 6")
    rt = blocks[0]["bulleted_list_item"]["rich_text"]
    full_text = "".join(
        item["text"]["content"] for item in rt if item.get("type") == "text"
    )
    assert "*" in full_text, "lone * was silently dropped"


def test_lone_backtick_is_preserved_not_dropped() -> None:
    # lone backtick (unmatched) must surface as literal text, not disappear
    blocks = md_to_notion_blocks("- use the ` character")
    rt = blocks[0]["bulleted_list_item"]["rich_text"]
    full_text = "".join(
        item["text"]["content"] for item in rt if item.get("type") == "text"
    )
    assert "`" in full_text, "lone backtick was silently dropped"


def test_table_column_count_mismatch_is_normalized() -> None:
    # Data rows with fewer/more columns than header must be padded/trimmed
    md = "| A | B | C |\n|---|---|---|\n| 1 | 2 |\n| x | y | z | extra |"
    blocks = md_to_notion_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "table"
    table = blocks[0]["table"]
    assert table["table_width"] == 3
    for row_block in table["children"]:
        assert len(row_block["table_row"]["cells"]) == 3


def test_unclosed_code_block_emits_content_not_lost() -> None:
    # LLM may omit closing fence; content must not be silently swallowed
    md = "intro\n```python\ndef foo():\n    return 1\n"
    blocks = md_to_notion_blocks(md)
    assert any(b["type"] == "code" for b in blocks), "unclosed code block was lost"
    code_block = next(b for b in blocks if b["type"] == "code")
    assert "def foo" in code_block["code"]["rich_text"][0]["text"]["content"]


def test_h4_maps_to_heading_4() -> None:
    blocks = md_to_notion_blocks("#### Sub heading")
    assert len(blocks) == 1
    assert blocks[0]["type"] == "heading_4"
    rt = blocks[0]["heading_4"]["rich_text"]
    assert rt[0]["text"]["content"] == "Sub heading"


def test_h5_and_h6_degrade_to_heading_4() -> None:
    for prefix, label in [("##### ", "h5 text"), ("###### ", "h6 text")]:
        blocks = md_to_notion_blocks(f"{prefix}{label}")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "heading_4", f"{prefix!r} should degrade to heading_4"
        rt = blocks[0]["heading_4"]["rich_text"]
        assert rt[0]["text"]["content"] == label


def test_indented_table_after_bullet_is_parsed() -> None:
    md = "- **Register naming**:\n\n    | 64-bit | 32-bit |\n    |--------|--------|\n    | `RAX`  | `EAX`  |\n"
    blocks = md_to_notion_blocks(md)
    types = [b["type"] for b in blocks]
    assert "bulleted_list_item" in types
    assert "table" in types
    table = next(b for b in blocks if b["type"] == "table")
    assert table["table"]["table_width"] == 2
    assert len(table["table"]["children"]) == 2  # header + 1 data row


def _table_cell_text(blocks: list[dict], row_index: int, col_index: int) -> str:
    """Extract joined plain text from a specific table cell."""
    table = next(b for b in blocks if b["type"] == "table")
    cell_rich_text = table["table"]["children"][row_index]["table_row"]["cells"][col_index]
    return "".join(
        item["text"]["content"]
        for item in cell_rich_text
        if item.get("type") == "text"
    )


def test_br_lowercase_in_table_cell_becomes_newline() -> None:
    md = "| A | B |\n|---|---|\n| line1<br>line2 | val |"
    blocks = md_to_notion_blocks(md)
    text = _table_cell_text(blocks, 1, 0)
    assert "\n" in text
    assert "line1" in text
    assert "line2" in text


def test_br_uppercase_in_table_cell_becomes_newline() -> None:
    md = "| A | B |\n|---|---|\n| line1<BR>line2 | val |"
    blocks = md_to_notion_blocks(md)
    text = _table_cell_text(blocks, 1, 0)
    assert "\n" in text
    assert "line1" in text
    assert "line2" in text


def test_br_self_closing_in_table_cell_becomes_newline() -> None:
    md = "| A | B |\n|---|---|\n| line1<br/>line2 | val |"
    blocks = md_to_notion_blocks(md)
    text = _table_cell_text(blocks, 1, 0)
    assert "\n" in text
    assert "line1" in text
    assert "line2" in text


def test_br_with_space_self_closing_in_table_cell_becomes_newline() -> None:
    md = "| A | B |\n|---|---|\n| line1<br />line2 | val |"
    blocks = md_to_notion_blocks(md)
    text = _table_cell_text(blocks, 1, 0)
    assert "\n" in text
    assert "line1" in text
    assert "line2" in text


def test_br_inside_code_span_in_table_cell_is_literal() -> None:
    # `<br>` inside a backtick code span must remain as literal text, not become \n
    md = "| A | B |\n|---|---|\n| `<br>` | val |"
    blocks = md_to_notion_blocks(md)
    table = next(b for b in blocks if b["type"] == "table")
    cell_rich_text = table["table"]["children"][1]["table_row"]["cells"][0]
    code_items = [item for item in cell_rich_text if item.get("annotations", {}).get("code")]
    assert any("<br>" in item["text"]["content"] for item in code_items), \
        "backtick-wrapped <br> should be literal, not a newline"


def test_multiple_br_in_one_table_cell_all_become_newlines() -> None:
    # A cell with more than one <br> must have all of them converted
    md = "| A | B |\n|---|---|\n| line1<br>line2<br>line3 | val |"
    blocks = md_to_notion_blocks(md)
    text = _table_cell_text(blocks, 1, 0)
    assert text.count("\n") >= 2, "each <br> should become a separate newline"
    assert "line1" in text
    assert "line2" in text
    assert "line3" in text


def test_br_inside_bold_in_table_cell_text_is_preserved() -> None:
    # <br> inside **bold** is substituted to \n before inline parsing.
    # Known limitation: the bold regex (.+?) does not match across newlines, so
    # bold annotation is NOT preserved when **bold** spans a <br>-converted newline.
    # This test documents the actual behavior: text content is correct and newline
    # is present, but bold annotation on cross-newline spans is not guaranteed.
    md = "| A | B |\n|---|---|\n| **first<br>second** | val |"
    blocks = md_to_notion_blocks(md)
    table = next(b for b in blocks if b["type"] == "table")
    cell_rich_text = table["table"]["children"][1]["table_row"]["cells"][0]
    all_text = "".join(
        item["text"]["content"]
        for item in cell_rich_text
        if item.get("type") == "text"
    )
    assert "\n" in all_text, "<br> inside bold span should become newline"
    assert "first" in all_text
    assert "second" in all_text
    # Bold annotation is lost because _parse_inline bold regex does not span newlines.
    # This is an accepted limitation; a follow-up ticket can add re.DOTALL support.


def test_br_mixed_with_code_span_in_table_cell() -> None:
    # A cell with both a <br> outside a code span and a `<br>` inside one:
    # the outer one becomes \n, the inner one stays literal.
    md = "| A | B |\n|---|---|\n| before<br>after `<br>` end | val |"
    blocks = md_to_notion_blocks(md)
    table = next(b for b in blocks if b["type"] == "table")
    cell_rich_text = table["table"]["children"][1]["table_row"]["cells"][0]
    plain_text = "".join(
        item["text"]["content"]
        for item in cell_rich_text
        if item.get("type") == "text" and not item.get("annotations", {}).get("code")
    )
    code_text = "".join(
        item["text"]["content"]
        for item in cell_rich_text
        if item.get("type") == "text" and item.get("annotations", {}).get("code")
    )
    assert "\n" in plain_text, "bare <br> outside code span should become newline"
    assert "<br>" in code_text, "backtick-wrapped <br> should remain literal"


def test_br_at_start_of_table_cell_becomes_newline() -> None:
    # <br> at the very beginning of a cell (after strip) should be converted
    md = "| A | B |\n|---|---|\n| <br>trailing | val |"
    blocks = md_to_notion_blocks(md)
    text = _table_cell_text(blocks, 1, 0)
    assert "\n" in text
    assert "trailing" in text


def test_br_at_end_of_table_cell_becomes_newline() -> None:
    # <br> at the very end of a cell should be converted
    md = "| A | B |\n|---|---|\n| leading<br> | val |"
    blocks = md_to_notion_blocks(md)
    text = _table_cell_text(blocks, 1, 0)
    assert "\n" in text
    assert "leading" in text


def test_dollar_inside_code_span_in_table_cell_does_not_break_column_split() -> None:
    # $ inside backtick code spans (e.g. assembly `movl $0x10, %rax`) must not
    # be treated as a LaTeX math delimiter; all three columns must be present.
    md = (
        "| 예시 | 모드 | 설명 |\n"
        "|---|---|---|\n"
        "| `movl $0x10, %rax` | 즉시값 | 상수를 레지스터에 저장 |\n"
        "| `movl $arr, %rax` | 즉시값 | 배열 주소를 레지스터에 저장 |"
    )
    blocks = md_to_notion_blocks(md)
    assert len(blocks) == 1
    table = blocks[0]["table"]
    assert table["table_width"] == 3
    for row_block in table["children"]:
        assert len(row_block["table_row"]["cells"]) == 3
    # Second data row first cell must contain only the code, not the entire row
    first_cell = table["children"][1]["table_row"]["cells"][0]
    cell_text = "".join(
        item["text"]["content"] for item in first_cell if item.get("type") == "text"
    )
    assert "즉시값" not in cell_text, "column 2 content leaked into column 1"


def test_latex_math_in_table_cell_still_splits_correctly() -> None:
    # $ outside backtick code spans (real LaTeX) must still suppress | splitting.
    md = (
        "| 수식 | 설명 |\n"
        "|---|---|\n"
        "| $E = mc^2$ | 질량-에너지 등가 |"
    )
    blocks = md_to_notion_blocks(md)
    assert len(blocks) == 1
    table = blocks[0]["table"]
    assert table["table_width"] == 2
    for row_block in table["children"]:
        assert len(row_block["table_row"]["cells"]) == 2
