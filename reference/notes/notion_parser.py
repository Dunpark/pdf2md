"""
notes/notion_parser.py — Markdown to Notion blocks converter.
"""

import re

from notes.constants import _NOTION_EQ_MAX, _NOTION_RT_MAX


def _rt(content: str, *, bold: bool = False, italic: bool = False, code: bool = False) -> dict:
    item: dict = {"type": "text", "text": {"content": content[:_NOTION_RT_MAX]}}
    annotations: dict = {}
    if bold:
        annotations["bold"] = True
    if italic:
        annotations["italic"] = True
    if code:
        annotations["code"] = True
    if annotations:
        item["annotations"] = annotations
    return item


def _eq(expression: str) -> dict:
    return {"type": "equation", "equation": {"expression": expression[:_NOTION_EQ_MAX]}}


def _apply_text_annotations(items: list[dict], *, bold: bool = False, italic: bool = False) -> list[dict]:
    out: list[dict] = []
    for item in items:
        if item.get("type") != "text":
            out.append(item)
            continue

        styled = dict(item)
        annotations = dict(styled.get("annotations", {}))
        if bold:
            annotations["bold"] = True
        if italic:
            annotations["italic"] = True
        if annotations:
            styled["annotations"] = annotations
        out.append(styled)
    return out


def _extract_math_expression(text: str) -> str | None:
    s = text.strip()
    if len(s) >= 2 and s.startswith("$") and s.endswith("$") and not s.startswith("$$"):
        return s[1:-1].strip()
    if len(s) >= 4 and s.startswith("$$") and s.endswith("$$"):
        return s[2:-2].strip()
    if len(s) >= 4 and s.startswith(r"\(") and s.endswith(r"\)"):
        return s[2:-2].strip()
    if len(s) >= 4 and s.startswith(r"\[") and s.endswith(r"\]"):
        return s[2:-2].strip()
    return None


def _parse_inline(text: str) -> list[dict]:
    """Convert inline markdown + LaTeX markers to Notion rich_text array."""
    parts: list[dict] = []
    pattern = (
        r'\*\*`(?P<bold_code>[^`]+)`\*\*'     # **`bold code`** (before **bold**)
        r'|(?<!\\)\$\$(?P<math_double_dollar>.+?)(?<!\\)\$\$'  # $$...$$ inline math
        r'|(?<![\\$])\$(?!\$)(?P<math_dollar>.+?)(?<![\\$])\$(?!\$)'  # $...$ inline math
        r'|\\\((?P<math_paren>.+?)\\\)'       # \(...\) inline math
        r'|\*\*(?P<bold>.+?)\*\*'             # **bold**
        r'|\*(?P<italic>[^*]+)\*'             # *italic*
        r'|`(?P<code>[^`]+)`'                 # `code`
        r'|(?P<lone_dollar>\$)'               # lone $
        r'|(?P<lone_star>\*)'                  # lone * (e.g. pointer notation, multiplication)
        r'|(?P<lone_backtick>`)'               # lone ` (unmatched backtick)
        r'|(?P<plain>[^*`$]+)'                # plain text
    )
    for m in re.finditer(pattern, text):
        if m.group("bold_code") is not None:
            math_expr = _extract_math_expression(m.group("bold_code"))
            if math_expr:
                parts.append(_eq(math_expr))
            else:
                parts.append(_rt(m.group("bold_code"), bold=True, code=True))
        elif m.group("math_double_dollar") is not None:
            parts.append(_eq(m.group("math_double_dollar")))
        elif m.group("math_dollar") is not None:
            parts.append(_eq(m.group("math_dollar")))
        elif m.group("math_paren") is not None:
            parts.append(_eq(m.group("math_paren")))
        elif m.group("bold") is not None:
            nested = _parse_inline(m.group("bold"))
            parts.extend(_apply_text_annotations(nested, bold=True))
        elif m.group("italic") is not None:
            nested = _parse_inline(m.group("italic"))
            parts.extend(_apply_text_annotations(nested, italic=True))
        elif m.group("code") is not None:
            math_expr = _extract_math_expression(m.group("code"))
            if math_expr:
                parts.append(_eq(math_expr))
            else:
                parts.append(_rt(m.group("code"), code=True))
        elif m.group("lone_dollar") is not None:
            parts.append(_rt(m.group("lone_dollar")))
        elif m.group("lone_star") is not None:
            parts.append(_rt(m.group("lone_star")))
        elif m.group("lone_backtick") is not None:
            parts.append(_rt(m.group("lone_backtick")))
        elif m.group("plain") is not None:
            parts.append(_rt(m.group("plain")))
    return parts or [_rt(text)]


def _block_with_color(type_: str, rich_text: list[dict], color: str = "default") -> dict:
    """Build a Notion block that requires a color field (headings, paragraph, list items, quote)."""
    return {"type": type_, type_: {"rich_text": rich_text, "color": color}}


def _parse_table_row(line: str) -> list[list[dict]]:
    """Parse a markdown table row into a list of Notion table_row cells.
    Each cell is a rich_text array (not a dict).
    """
    def _replace_br(cell: str) -> str:
        # Replace <br> variants with \n, but leave content inside backtick code spans untouched.
        result = []
        for part in re.split(r'(`[^`]*`)', cell):
            if part.startswith('`') and part.endswith('`') and len(part) >= 2:
                result.append(part)
            else:
                result.append(re.sub(r'<br\s*/?>', '\n', part, flags=re.IGNORECASE))
        return ''.join(result)

    def _split_cells(row: str) -> list[str]:
        # Split on | while ignoring | inside $...$ math spans or `...` code spans.
        row = row.strip().strip("|")
        cells: list[str] = []
        current: list[str] = []
        in_math = False
        in_code = False
        i = 0
        while i < len(row):
            ch = row[i]
            if ch == "\\" and i + 1 < len(row):
                # Escaped character — consume both chars verbatim.
                current.append(ch)
                current.append(row[i + 1])
                i += 2
                continue
            if ch == "`":
                in_code = not in_code
            if ch == "$" and not in_code:
                in_math = not in_math
            if ch == "|" and not in_math and not in_code:
                cells.append("".join(current))
                current = []
            else:
                current.append(ch)
            i += 1
        cells.append("".join(current))
        return cells

    cells = [_replace_br(cell.strip()) for cell in _split_cells(line)]
    return [_parse_inline(cell) for cell in cells]


def md_to_notion_blocks(md: str) -> list[dict]:
    """Convert markdown text to a list of Notion block objects."""
    blocks: list[dict] = []
    lines = md.splitlines()
    i = 0
    code_buf: list[str] = []
    code_lang = ""
    in_code = False
    callout_buf: list[str] = []
    callout_icon = ""
    in_callout = False
    details_summary = ""
    details_buf: list[str] = []
    in_details = False
    details_after_summary = False
    in_details_summary = False
    details_summary_buf: list[str] = []
    math_buf: list[str] = []
    in_math = False
    math_closer = ""
    toggle_buf: list[str] = []
    toggle_title = ""
    in_toggle = False
    list_stack: list[tuple[int, str, dict]] = []

    def _reset_list_stack() -> None:
        list_stack.clear()

    def _append_list_item(indent: int, list_type: str, item: dict) -> None:
        while list_stack and indent < list_stack[-1][0]:
            list_stack.pop()

        if not list_stack:
            blocks.append(item)
            list_stack.append((indent, list_type, item))
            return

        top_indent, top_type, top_item = list_stack[-1]
        if indent > top_indent:
            top_item[top_type].setdefault("children", []).append(item)
        else:
            if len(list_stack) >= 2:
                parent_indent, parent_type, parent_item = list_stack[-2]
                if parent_indent < indent:
                    parent_item[parent_type].setdefault("children", []).append(item)
                else:
                    blocks.append(item)
            else:
                blocks.append(item)
            list_stack.pop()

        list_stack.append((indent, list_type, item))

    def _flatten_list_depth(items: list[dict], depth: int = 0) -> list[dict]:
        """Flatten nested list children beyond Notion-safe depth."""
        out: list[dict] = []
        for item in items:
            item_type = item.get("type")
            if item_type not in ("bulleted_list_item", "numbered_list_item"):
                out.append(item)
                continue

            node = item.get(item_type, {})
            children = node.get("children")
            if not isinstance(children, list):
                out.append(item)
                continue

            flat_children = _flatten_list_depth(children, depth + 1)
            new_node = dict(node)
            new_item = dict(item)

            # Keep nesting up to depth 2 (root=0). Deeper children are promoted.
            if depth >= 2:
                new_node.pop("children", None)
                new_item[item_type] = new_node
                out.append(new_item)
                out.extend(flat_children)
            else:
                new_node["children"] = flat_children
                new_item[item_type] = new_node
                out.append(new_item)

        return out

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        stripped_lower = stripped.lower()

        # Math block: $$...$$ or \[...\]
        if not in_code and not in_callout and not in_details and not in_math:
            if stripped.startswith("$$"):
                _reset_list_stack()
                tail = stripped[2:]
                if tail.endswith("$$"):
                    expr = tail[:-2].strip()
                    if expr:
                        blocks.append({"type": "equation", "equation": {"expression": expr}})
                else:
                    in_math = True
                    math_closer = "$$"
                    math_buf = [tail] if tail else []
                i += 1
                continue
            if stripped.startswith(r"\["):
                _reset_list_stack()
                tail = stripped[2:]
                if tail.endswith(r"\]"):
                    expr = tail[:-2].strip()
                    if expr:
                        blocks.append({"type": "equation", "equation": {"expression": expr}})
                else:
                    in_math = True
                    math_closer = r"\]"
                    math_buf = [tail] if tail else []
                i += 1
                continue

        if in_math:
            if stripped.endswith(math_closer):
                end_idx = line.rfind(math_closer)
                math_buf.append(line[:end_idx])
                expr = "\n".join(math_buf).strip()
                if expr:
                    _reset_list_stack()
                    blocks.append({"type": "equation", "equation": {"expression": expr}})
                in_math = False
                math_closer = ""
                math_buf = []
            else:
                math_buf.append(line)
            i += 1
            continue

        # <toggle title="..."> block
        toggle_open_m = re.match(r'^<toggle\s+title="([^"]*)">\s*$', stripped, flags=re.IGNORECASE)
        if toggle_open_m and not in_code:
            in_toggle = True
            toggle_title = toggle_open_m.group(1).strip()
            toggle_buf = []
            i += 1
            continue

        if in_toggle:
            if stripped_lower == "</toggle>":
                in_toggle = False
                _reset_list_stack()
                children = md_to_notion_blocks("\n".join(toggle_buf))
                blocks.append({
                    "type": "toggle",
                    "toggle": {
                        "rich_text": _parse_inline(toggle_title),
                        "color": "default",
                        "children": children,
                    },
                })
                toggle_buf = []
            else:
                toggle_buf.append(line)
            i += 1
            continue

        # <details><summary> toggle block
        details_one_line = re.match(
            r'^<details(?:\s+open)?\s*>\s*<summary>(.*)</summary>\s*(.*?)\s*</details>\s*$',
            stripped,
            flags=re.IGNORECASE,
        )
        if details_one_line and not in_code:
            _reset_list_stack()
            summary = details_one_line.group(1).strip()
            answer = details_one_line.group(2).strip()
            children = [_block_with_color("paragraph", _parse_inline(answer))] if answer else []
            blocks.append({
                "type": "toggle",
                "toggle": {
                    "rich_text": _parse_inline(summary),
                    "color": "default",
                    "children": children,
                },
            })
            i += 1
            continue

        details_open_summary = re.match(
            r'^<details(?:\s+open)?\s*>\s*<summary>(.*)</summary>\s*$',
            stripped,
            flags=re.IGNORECASE,
        )
        if details_open_summary and not in_code:
            in_details = True
            details_summary = details_open_summary.group(1).strip()
            details_buf = []
            details_after_summary = True
            i += 1
            continue

        if re.match(r'^<details(?:\s+open)?\s*>$', stripped, flags=re.IGNORECASE) and not in_code:
            in_details = True
            details_summary = ""
            details_buf = []
            details_after_summary = False
            i += 1
            continue

        if in_details:
            if in_details_summary:
                # Accumulate multi-line summary until </summary> is found.
                close_m = re.match(r'^(.*)</summary>\s*$', stripped, flags=re.IGNORECASE)
                if close_m:
                    details_summary_buf.append(close_m.group(1))
                    details_summary = "\n".join(details_summary_buf).strip()
                    details_summary_buf = []
                    in_details_summary = False
                    details_after_summary = True
                else:
                    details_summary_buf.append(stripped)
                i += 1
                continue
            summary_m = re.match(r'^<summary>(.*)</summary>$', stripped, flags=re.IGNORECASE)
            summary_open_m = re.match(r'^<summary>(.*)', stripped, flags=re.IGNORECASE) if not summary_m else None
            if summary_m:
                details_summary = summary_m.group(1)
                details_after_summary = True
            elif summary_open_m:
                # <summary> opened but not closed on same line — multi-line summary.
                in_details_summary = True
                details_summary_buf = [summary_open_m.group(1)]
            elif stripped_lower == "</details>":
                in_details = False
                _reset_list_stack()
                children = md_to_notion_blocks("\n".join(details_buf)) if details_buf else []
                blocks.append({
                    "type": "toggle",
                    "toggle": {
                        "rich_text": _parse_inline(details_summary),
                        "color": "default",
                        "children": children,
                    },
                })
            elif details_after_summary and stripped:
                details_buf.append(stripped)
            i += 1
            continue

        # Callout open: <callout icon="emoji"> or <callout="emoji">
        callout_open = re.match(
            r'^<callout(?:\s+icon)?\s*=\s*["\']([^"\']*)["\']\s*>$',
            stripped,
            flags=re.IGNORECASE,
        )
        if callout_open and not in_code:
            in_callout = True
            callout_icon = callout_open.group(1)
            callout_buf = []
            i += 1
            continue

        if in_callout:
            if stripped_lower == "</callout>":
                in_callout = False
                _reset_list_stack()
                content = "\n".join(callout_buf).strip()
                blocks.append({
                    "type": "callout",
                    "callout": {
                        "rich_text": _parse_inline(content),
                        "icon": {"type": "emoji", "emoji": callout_icon},
                        "color": "default",
                    },
                })
                callout_buf = []
            else:
                if stripped:
                    callout_buf.append(stripped)
            i += 1
            continue

        # Skip orphaned closing tags so raw markers are not exposed in output.
        if stripped_lower in ("</details>", "</callout>", "</toggle>"):
            i += 1
            continue

        # Code block
        if not in_code and stripped.startswith("```") and stripped.endswith("```") and len(stripped) > 6:
            _reset_list_stack()
            blocks.append({
                "type": "code",
                "code": {
                    "rich_text": [_rt(stripped[3:-3])],
                    "language": "plain text",
                },
            })
            i += 1
            continue

        if stripped.startswith("```"):
            _reset_list_stack()
            if not in_code:
                in_code = True
                code_lang = stripped[3:].strip() or "plain text"
                code_buf = []
            else:
                in_code = False
                blocks.append({
                    "type": "code",
                    "code": {
                        "rich_text": [_rt("\n".join(code_buf))],
                        "language": code_lang,
                    },
                })
                code_buf = []
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # Markdown table: detect header row followed by separator row.
        # Use stripped to handle indented tables (e.g. after a bullet point).
        # Skip blank lines between header and separator to handle LLM-formatted tables.
        if re.match(r'^\|.+\|', stripped):
            sep_idx = i + 1
            while sep_idx < len(lines) and not lines[sep_idx].strip():
                sep_idx += 1
            if sep_idx < len(lines) and re.match(r'^\|[-| :]+\|', lines[sep_idx].strip()):
                _reset_list_stack()
                header_cells = _parse_table_row(stripped)
                col_count = len(header_cells)
                i = sep_idx + 1  # skip header + separator
                rows: list[list[dict]] = [header_cells]
                while i < len(lines):
                    row_stripped = lines[i].strip()
                    if not row_stripped:
                        # Skip blank lines only if the next non-blank line is still a table row
                        j = i + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines) and re.match(r'^\|.+\|', lines[j].strip()):
                            i = j
                            continue
                        break
                    if re.match(r'^\|.+\|', row_stripped):
                        rows.append(_parse_table_row(row_stripped))
                        i += 1
                    else:
                        break
                # Normalize all rows to header column count (pad or trim).
                # Notion API rejects table_row cells that don't match table_width.
                normalized: list[list[list[dict]]] = []
                for row in rows:
                    if len(row) < col_count:
                        row = row + [[] for _ in range(col_count - len(row))]
                    else:
                        row = row[:col_count]
                    normalized.append(row)
                blocks.append({
                    "type": "table",
                    "table": {
                        "table_width": col_count,
                        "has_column_header": True,
                        "has_row_header": False,
                        "children": [
                            {"type": "table_row", "table_row": {"cells": row}} for row in normalized
                        ],
                    },
                })
                continue

        rt = _parse_inline
        expanded = line.expandtabs(4)
        if line.startswith("###### ") or line.startswith("##### "):
            _reset_list_stack()
            # Notion max heading is heading_4; h5/h6 degrade to heading_4
            offset = 7 if line.startswith("###### ") else 6
            blocks.append(_block_with_color("heading_4", rt(line[offset:])))
        elif line.startswith("#### "):
            _reset_list_stack()
            blocks.append(_block_with_color("heading_4", rt(line[5:])))
        elif line.startswith("### "):
            _reset_list_stack()
            blocks.append(_block_with_color("heading_3", rt(line[4:])))
        elif line.startswith("## "):
            # gray_background makes h2 sections visually distinct from h3
            _reset_list_stack()
            blocks.append(_block_with_color("heading_2", rt(line[3:]), "gray_background"))
        elif line.startswith("# "):
            _reset_list_stack()
            blocks.append(_block_with_color("heading_1", rt(line[2:])))
        elif bullet_m := re.match(r'^(\s*)[-*]\s+(.*)$', expanded):
            indent = len(bullet_m.group(1))
            content = bullet_m.group(2)
            item = _block_with_color("bulleted_list_item", rt(content))
            _append_list_item(indent, "bulleted_list_item", item)
        elif num_m := re.match(r'^(\s*)\d+\.\s+(.*)$', expanded):
            indent = len(num_m.group(1))
            content = num_m.group(2)
            item = _block_with_color("numbered_list_item", rt(content))
            _append_list_item(indent, "numbered_list_item", item)
        elif line.startswith("> "):
            _reset_list_stack()
            blocks.append(_block_with_color("quote", rt(line[2:])))
        elif line.strip() in ("---", "***", "___"):
            _reset_list_stack()
            blocks.append({"type": "divider", "divider": {}})
        elif re.match(r'^\*\*TL;DR\*\*:', line):
            # TL;DR summary lines stand out better as quotes in Notion
            _reset_list_stack()
            content = re.sub(r'^\*\*TL;DR\*\*:\s*', '', line)
            blocks.append(_block_with_color("quote", rt(content)))
        elif line.strip():
            _reset_list_stack()
            blocks.append(_block_with_color("paragraph", rt(line)))
        else:
            _reset_list_stack()

        i += 1

    # Emit any unclosed code block so content is not silently lost.
    if in_code and code_buf:
        blocks.append({
            "type": "code",
            "code": {
                "rich_text": [_rt("\n".join(code_buf))],
                "language": code_lang,
            },
        })

    return _flatten_list_depth(blocks)
