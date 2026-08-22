# HANDOFF — what came from the `notetaker` repo and why

Read this before touching `reference/`. It contains the things the code does
**not** tell you.

## Goal

```
PDF  →  Markdown  →  md_to_notion_blocks()  →  Notion page
        ^^^^^^^^      ---------- already done ----------
        this is the only part you have to build
```

Markdown is the intermediate representation on purpose: it makes every stage
inspectable (dump the `.md`, look at it) and it lets the existing, tested
Notion writer be reused untouched.

## CLI shape (target)

```
pdf2notion <pdf-path> <notion-page-url>
```

Both are required inputs. The page URL's trailing 32-hex is the `page_id`
Notion's API wants.

## What is in `reference/`

Copied from `TarroLab/notetaker` (commit `dbe80dc`, 2026-08-22). Treat it as
read-only source material — copy pieces out, don't develop inside it.

| Path | What it is | How much to trust it |
|---|---|---|
| `notes/notion_parser.py` (595L) | Markdown → Notion block JSON. Tables, equations, code fences, callouts, toggles, `<details>`, nested lists, h1–h4, quotes, dividers. | **High.** Battle-tested, 36 passing tests. Reuse nearly as-is. One deliberate change needed — see "The one thing to invert". |
| `notes/notion_uploader.py` (106L) | Creates the page, appends blocks in batches of 100, retries on 429 with `Retry-After`. | **High**, but it reads the parent page from `NOTION_PARENT_PAGE_ID` env. You want it from a CLI URL argument instead. |
| `notes/constants.py` (18L) | Notion's hard limits + API version. | **High.** These numbers were learned by getting HTTP 400s, not by reading docs. |
| `notion_client.py` (319L) | Async `httpx` version of the same thing, from the production backend. | **Reference only.** Steal `_validate_payload` (500 KB request cap) and the error-category logic. **Delete the OAuth half** — a personal integration token is one header. |
| `tests/` (3 files, 36 tests) | Golden markdown-in → blocks-out corpus. | **High.** This is your starting test harness. |

Verify the copy still works:

```bash
cd reference && python -m pytest tests/ -q     # expect: 36 passed
```

External dependency of `reference/`: `httpx` only.

## The one thing to invert

You asked for "stop and notify me on an unrecognised format". The parser
currently does the **opposite** — `notes/notion_parser.py:577`:

```python
elif line.strip():
    _reset_list_stack()
    blocks.append(_block_with_color("paragraph", rt(line)))   # catch-all
```

Anything it failed to recognise becomes a plain paragraph. That is exactly the
failure mode you disliked in Notion's own PDF importer: output looks fine,
content is quietly mangled.

Change it to raise instead:

```python
elif line.strip():
    raise UnknownFormatError(line_no=i + 1, line=line)
```

So the "halt on unknown format" feature is **not new code** — it is flipping
one existing fallback.

**Two more silent-loss sites in the same file**, same treatment:

- `notion_parser.py:11` — `content[:_NOTION_RT_MAX]` silently truncates text at 2000 chars
- `notion_parser.py:25` — `expression[:_NOTION_EQ_MAX]` silently truncates equations at 1000 chars

Under strict mode these should raise too. Truncating a formula at 1000
characters produces a wrong formula that still renders.

## Known traps

1. **LaTeX PDFs do not contain equations as text.** "Attention Is All You Need"
   is LaTeX-typeset: `∑` is not a character, it is a glyph from a math font
   placed at coordinates. Same for tables — you get ruling lines and text
   positions, no "table" object. PDF → LaTeX is inference, not extraction.
   This is the hard part of the project and the reason the halt-and-notify
   design is the right call.

2. **The limits in `constants.py` are real.** 2000 chars per rich_text, 1000
   per equation expression, 100 blocks per API request, 500 KB per request
   body. Exceed any of them and Notion returns 400.

3. **`notion_client.py` carries OAuth machinery you don't need.** It exists
   because the source product authenticated many users. You have one user.

4. **The source repo has `pdf_exports.py` files — they are the wrong
   direction** (Markdown → PDF export). They were deliberately not copied.

## What does not exist yet

PDF → Markdown. That's it. Everything downstream is done.

Starting points worth evaluating: `pymupdf` (text spans with coordinates and
font names — font name is a usable signal for "this region is math"),
`pdfplumber` (ruling-line based table extraction).

## Ground rules carried over

- Edit-level changes, never whole-file rewrites.
- Non-trivial logic leaves one runnable check behind (`assert`-based
  `__main__` self-check or one small `test_*.py`). No frameworks.
- Mark deliberate shortcuts with a `# ponytail:` comment naming the ceiling
  and the upgrade path.
