"""Load curated examples.csv for few-shot LLM context and name-alias hints."""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from typing import Any

from backend.config import config

# Column indices (header row in examples.csv; stable if header text changes)
COL_SUBCATEGORY = 0
COL_STANCE = 2
COL_TOOL_NAME = 3
COL_DESCRIPTIVE = 4
COL_URL = 5
COL_DEVELOPER = 6
COL_TAGLINE = 7
COL_USE_CASE = 8
COL_TARGET = 9
COL_PRIMARY_OUT = 10
COL_HARM = 11
COL_G1 = 12
COL_G2 = 13
COL_G3 = 14
COL_EX1 = 15
COL_EX2 = 16
COL_EX3 = 17
COL_INCLUDE = 18
COL_EVIDENCE = 19


_SUBCAT_RE = re.compile(r"^[1-5][A-C]$")


def _row_subcategory(row: list[str]) -> str:
    if not row:
        return ""
    return (row[COL_SUBCATEGORY] or "").strip()


def _tool_name_key(name: str) -> str | None:
    """Single substring key for name_match_filter (alnum, first segment before /)."""
    first = (name or "").split("/")[0].strip()
    if not first:
        return None
    alnum = re.sub(r"[^a-z0-9]+", "", first.lower())
    if len(alnum) < 4 or len(alnum) > 48:
        return None
    return alnum


@lru_cache(maxsize=1)
def load_example_rows() -> tuple[dict[str, Any], ...]:
    """Parse examples.csv into immutable tuples for caching."""
    csv_path = config.EXAMPLES_CSV_PATH
    if not csv_path.is_file():
        return ()

    rows_out: list[dict[str, Any]] = []
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            for row in reader:
                if len(row) < 20:
                    continue
                sub = _row_subcategory(row)
                if not _SUBCAT_RE.match(sub):
                    continue
                tool = (row[COL_TOOL_NAME] or "").strip()
                if not tool:
                    continue
                stance_raw = (row[COL_STANCE] or "").strip()
                if stance_raw.lower().startswith("criminal"):
                    stance = "Criminal AI"
                elif stance_raw.lower().startswith("controversial"):
                    stance = "Controversial institutional AI"
                else:
                    stance = stance_raw[:40] + ("…" if len(stance_raw) > 40 else "")
                rows_out.append(
                    {
                        "subcategory": sub,
                        "stance": stance,
                        "tool_name": tool,
                        "descriptive_category": (row[COL_DESCRIPTIVE] or "").strip(),
                        "url": (row[COL_URL] or "").strip(),
                        "developer": (row[COL_DEVELOPER] or "").strip(),
                        "public_tagline": (row[COL_TAGLINE] or "").strip(),
                        "stated_use_case": (row[COL_USE_CASE] or "").strip(),
                        "target_victim": (row[COL_TARGET] or "").strip(),
                        "primary_output": (row[COL_PRIMARY_OUT] or "").strip(),
                        "harm_category": (row[COL_HARM] or "").strip(),
                        "gate_1": (row[COL_G1] or "").strip(),
                        "gate_2": (row[COL_G2] or "").strip(),
                        "gate_3": (row[COL_G3] or "").strip(),
                        "exclusion_1": (row[COL_EX1] or "").strip(),
                        "exclusion_2": (row[COL_EX2] or "").strip(),
                        "exclusion_3": (row[COL_EX3] or "").strip(),
                        "include_in_repo": (row[COL_INCLUDE] or "").strip(),
                        "evidence_summary": (row[COL_EVIDENCE] or "").strip()[:500],
                    }
                )
    except OSError as e:
        print(f"[examples_csv] Could not read {csv_path}: {e}")
        return ()

    return tuple(rows_out)


def load_example_name_aliases() -> dict[str, str]:
    """
    Map search substring -> subcategory id from curated tool names.
    Keys are alnum-normalized first segment of AI Tool Name; only keys not
    already covered should be merged by the caller.
    """
    aliases: dict[str, str] = {}
    for ex in load_example_rows():
        key = _tool_name_key(ex["tool_name"])
        if key:
            aliases[key] = ex["subcategory"]
    return aliases


def format_examples_for_prompt() -> str:
    """Compact few-shot block for the LLM system prompt."""
    if not config.USE_EXAMPLES_CSV:
        return ""

    examples = load_example_rows()
    if not examples:
        return ""

    header = (
        "CURATED REFERENCE EXAMPLES (from data/rubric/examples.csv — match this style and rubric):\n"
        "Each line: subcategory | stance | tool | descriptive label | harm | evidence\n"
    )
    footer = (
        "\nUse these as calibration for category boundaries, gate patterns, and field completeness."
    )
    max_total = max(500, config.EXAMPLES_PROMPT_MAX_CHARS)
    body_lines: list[str] = []
    used = len(header) + len(footer)

    for ex in examples:
        desc = ex["descriptive_category"] or "—"
        harm = ex["harm_category"] or "—"
        ev = (ex["evidence_summary"] or "").replace("\n", " ")
        if len(ev) > 220:
            ev = ev[:217] + "..."
        line = (
            f"- [{ex['subcategory']}] ({ex['stance']}) {ex['tool_name']}: {desc} | {harm} | {ev}"
        )
        if used + len(line) + 1 > max_total:
            break
        body_lines.append(line)
        used += len(line) + 1

    return header + "\n".join(body_lines) + footer


def merge_known_names(base: dict[str, str]) -> dict[str, str]:
    """Return copy of base with example aliases added (examples do not override base)."""
    merged = dict(base)
    for key, sub in load_example_name_aliases().items():
        if key not in merged:
            merged[key] = sub
    return merged
