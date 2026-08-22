"""
notes/constants.py — module-level constants for the notes package.
"""

from pathlib import Path

DEFAULT_MODEL = "xiaomi/mimo-v2.5-pro"
OUTPUT_DIR = Path("notes_output")
SYSTEM_PROMPT_FILE = OUTPUT_DIR / "system_prompt.txt"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 1  # retry once on timeout/network error

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
NOTION_MAX_RETRIES = 1  # retry once on transient Notion API failure
_NOTION_RT_MAX = 2000   # Notion rich_text content character limit
_NOTION_EQ_MAX = 1000   # Notion equation.expression character limit
_NOTION_BATCH = 100     # max blocks per API request
