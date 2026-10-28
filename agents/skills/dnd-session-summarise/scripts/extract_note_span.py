#!/usr/bin/env python3
"""Extract a span from a text file using 1-based line:column indexes.

By default, columns that exceed line length are clamped to the nearest valid
column because session metadata may contain approximate end columns.
Use --strict to treat out-of-range columns as errors.

Example:
  python3 "<installed-skill>/scripts/extract_note_span.py" \
    --file "Sessions/Notes/2024-10-09 - Session 01.md" \
    --start "42:1" \
    --end "70:40"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple


def parse_index(raw: str, label: str) -> Tuple[int, int]:
    parts = raw.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"{label} must be line:column, got: {raw!r}")

    try:
        line = int(parts[0])
        col = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"{label} must contain integers, got: {raw!r}") from exc

    if line < 1 or col < 1:
        raise ValueError(f"{label} values must be >= 1, got: {raw!r}")

    return line, col


def max_valid_col(line_text: str) -> int:
    # Empty lines still allow column 1 so they can be addressed explicitly.
    return max(1, len(line_text))


def normalize_position(
    lines: list[str], line_no: int, col_no: int, label: str, strict: bool
) -> Tuple[int, int]:
    if line_no < 1 or line_no > len(lines):
        raise ValueError(f"{label} line out of range: {line_no} (file has {len(lines)} lines)")

    max_col = max_valid_col(lines[line_no - 1])
    if col_no <= max_col:
        return line_no, col_no

    if strict:
        raise ValueError(
            f"{label} column out of range: {col_no} (line {line_no} supports 1..{max_col})"
        )

    return line_no, max_col


def extract_span(
    lines: list[str], start: Tuple[int, int], end: Tuple[int, int], strict: bool
) -> str:
    s_line, s_col = normalize_position(lines, start[0], start[1], "start", strict)
    e_line, e_col = normalize_position(lines, end[0], end[1], "end", strict)

    if (e_line, e_col) < (s_line, s_col):
        raise ValueError("end must be at or after start")

    if s_line == e_line:
        line = lines[s_line - 1]
        if not line:
            return ""
        return line[s_col - 1 : e_col]

    out: list[str] = []

    first_line = lines[s_line - 1]
    out.append(first_line[s_col - 1 :] if first_line else "")

    for idx in range(s_line + 1, e_line):
        out.append(lines[idx - 1])

    last_line = lines[e_line - 1]
    out.append(last_line[:e_col] if last_line else "")

    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract note text span from line:column indexes")
    parser.add_argument("--file", required=True, help="Path to note file")
    parser.add_argument("--start", required=True, help="Start index as line:column (1-based)")
    parser.add_argument("--end", required=True, help="End index as line:column (1-based, inclusive)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when a column is outside the addressed line length",
    )
    args = parser.parse_args()

    note_path = Path(args.file)
    if not note_path.exists():
        print(f"ERROR: file not found: {note_path}", file=sys.stderr)
        return 2

    text = note_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        print("ERROR: file is empty", file=sys.stderr)
        return 2

    try:
        start = parse_index(args.start, "start")
        end = parse_index(args.end, "end")
        span = extract_span(lines, start, end, strict=args.strict)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(span)
    if span and not span.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
