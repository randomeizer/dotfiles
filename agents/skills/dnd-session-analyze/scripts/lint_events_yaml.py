#!/usr/bin/env python3
"""Strict linter for session events.yaml artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


QUEST_STATUSES = {"proposed", "active", "deferred", "resolved"}
INDEX_RE = re.compile(r"^([1-9]\d*):([1-9]\d*)$")
PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# Shared scripts belong to the installed suite; campaign data belongs to the vault.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dnd-session-review" / "scripts"))
from dnd_vault import find_vault_root, load_campaign_config

REPO_ROOT = find_vault_root()
CAMPAIGN_CONFIG = load_campaign_config(REPO_ROOT)
NOTES_DIR = REPO_ROOT / "Sessions" / "Notes"
META_SESSIONS_DIR = REPO_ROOT / ".dnd-meta" / "sessions"


def path_label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def ruby_yaml_to_data(text: str) -> Any:
    try:
        proc = subprocess.run(
            [
                "ruby",
                "-ryaml",
                "-rjson",
                "-e",
                "obj = YAML.load(STDIN.read); STDOUT.write(JSON.generate(obj))",
            ],
            input=text,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ValueError(f"Unable to parse YAML via ruby: {stderr}") from exc
    return json.loads(proc.stdout)


def load_yaml(path: Path) -> Any:
    if not path.exists():
        raise ValueError(f"File not found: {path_label(path)}")
    try:
        return ruby_yaml_to_data(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Unable to read file: {path_label(path)} ({exc})") from exc


def discover_sessions() -> List[Dict[str, Any]]:
    pattern = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s*-\s*Session\s*(?P<num>\d{1,3})\.md$")
    sessions: List[Dict[str, Any]] = []
    for note in sorted(NOTES_DIR.glob("*.md")):
        match = pattern.match(note.name)
        if not match:
            continue
        sessions.append(
            {
                "session_number": int(match.group("num")),
                "date": match.group("date"),
                "path": note,
            }
        )
    if not sessions:
        raise ValueError("No session notes found in Sessions/Notes.")
    return sessions


def select_session(selector: Optional[str]) -> Dict[str, Any]:
    sessions = discover_sessions()
    ordered = sorted(sessions, key=lambda item: (item["session_number"], item["date"], item["path"].name))
    if not selector:
        return ordered[-1]

    candidate = selector.strip().lower()
    if candidate == "latest session":
        return ordered[-1]

    match = re.search(r"session\s*(\d{1,3})", candidate)
    if not match:
        raise ValueError(f"Unsupported session selector: {selector}")

    number = int(match.group(1))
    filtered = [s for s in sessions if s["session_number"] == number]
    if not filtered:
        raise ValueError(f"No session note found for Session {number:02d}.")
    return sorted(filtered, key=lambda item: (item["date"], item["path"].name))[-1]


def session_meta_dir(session: Dict[str, Any]) -> Path:
    return META_SESSIONS_DIR / f"{session['date']}-s{session['session_number']:03d}"


def parse_index(value: str) -> Optional[Tuple[int, int]]:
    match = INDEX_RE.match(value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def collect_placeholders(value: Any, pointer: str, errors: List[str]) -> None:
    if isinstance(value, str):
        lowered = value.lower()
        if PLACEHOLDER_RE.search(value) or "replace " in lowered or "yyy-mm-dd" in lowered:
            errors.append(f"{pointer}: placeholder text detected: {value!r}")
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            collect_placeholders(item, f"{pointer}[{idx}]", errors)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            collect_placeholders(item, f"{pointer}.{key}", errors)


def expect_dict(parent: Dict[str, Any], key: str, errors: List[str], pointer: str) -> Optional[Dict[str, Any]]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{pointer}.{key}: expected mapping")
        return None
    return value


def expect_list(parent: Dict[str, Any], key: str, errors: List[str], pointer: str) -> Optional[List[Any]]:
    value = parent.get(key)
    if not isinstance(value, list):
        errors.append(f"{pointer}.{key}: expected list")
        return None
    return value


def expect_non_empty_string(value: Any, pointer: str, errors: List[str]) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{pointer}: expected non-empty string")
        return None
    return value.strip()


def validate_string_list(value: Any, pointer: str, errors: List[str]) -> List[str]:
    if not isinstance(value, list):
        errors.append(f"{pointer}: expected list of strings")
        return []
    out: List[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{pointer}[{idx}]: expected non-empty string")
            continue
        out.append(item.strip())
    return out


def validate_events(data: Dict[str, Any], errors: List[str]) -> List[str]:
    events = expect_list(data, "events", errors, "$")
    if events is None:
        return []
    if not events:
        errors.append("$.events: must include at least one event")
        return []

    seen_ids = set()
    event_ids: List[str] = []
    required_arrays = [
        "participants",
        "locations",
        "factions",
        "items",
        "consequences",
        "quest_hooks",
    ]

    for idx, item in enumerate(events):
        pointer = f"$.events[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{pointer}: expected mapping")
            continue

        event_id = expect_non_empty_string(item.get("id"), f"{pointer}.id", errors)
        if event_id:
            if not re.match(r"^ev-\d{1,3}-\d{3}$", event_id):
                errors.append(f"{pointer}.id: expected pattern ev-<session>-<nnn>")
            if event_id in seen_ids:
                errors.append(f"{pointer}.id: duplicate event id {event_id!r}")
            else:
                seen_ids.add(event_id)
                event_ids.append(event_id)

        expect_non_empty_string(item.get("title"), f"{pointer}.title", errors)
        expect_non_empty_string(item.get("description"), f"{pointer}.description", errors)
        expect_non_empty_string(item.get("source_excerpt"), f"{pointer}.source_excerpt", errors)

        confidence = item.get("confidence")
        if not is_number(confidence):
            errors.append(f"{pointer}.confidence: expected numeric value in [0, 1]")
        elif confidence < 0 or confidence > 1:
            errors.append(f"{pointer}.confidence: out of range [0, 1]")

        start = expect_non_empty_string(item.get("start_index"), f"{pointer}.start_index", errors)
        end = expect_non_empty_string(item.get("end_index"), f"{pointer}.end_index", errors)
        start_parsed = parse_index(start) if start else None
        end_parsed = parse_index(end) if end else None
        if start and not start_parsed:
            errors.append(f"{pointer}.start_index: expected line:column format with positive integers")
        if end and not end_parsed:
            errors.append(f"{pointer}.end_index: expected line:column format with positive integers")
        if start_parsed and end_parsed and start_parsed > end_parsed:
            errors.append(f"{pointer}: start_index must be <= end_index")

        for field in required_arrays:
            validate_string_list(item.get(field), f"{pointer}.{field}", errors)

    return event_ids


def validate_quest_candidates(data: Dict[str, Any], event_ids: Sequence[str], errors: List[str]) -> None:
    candidates = expect_list(data, "quest_candidates", errors, "$")
    if candidates is None:
        return

    seen_keys = set()
    event_id_set = set(event_ids)
    for idx, item in enumerate(candidates):
        pointer = f"$.quest_candidates[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{pointer}: expected mapping")
            continue

        key = expect_non_empty_string(item.get("key"), f"{pointer}.key", errors)
        if key:
            if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", key):
                errors.append(f"{pointer}.key: expected slug format (lowercase words joined by '-')")
            if key in seen_keys:
                errors.append(f"{pointer}.key: duplicate key {key!r}")
            seen_keys.add(key)

        expect_non_empty_string(item.get("title"), f"{pointer}.title", errors)
        expect_non_empty_string(item.get("description"), f"{pointer}.description", errors)

        confidence = item.get("confidence")
        if not is_number(confidence):
            errors.append(f"{pointer}.confidence: expected numeric value in [0, 1]")
        elif confidence < 0 or confidence > 1:
            errors.append(f"{pointer}.confidence: out of range [0, 1]")

        status = expect_non_empty_string(item.get("status"), f"{pointer}.status", errors)
        if status and status not in QUEST_STATUSES:
            errors.append(
                f"{pointer}.status: expected one of {', '.join(sorted(QUEST_STATUSES))}"
            )

        source_ids = validate_string_list(item.get("source_event_ids"), f"{pointer}.source_event_ids", errors)
        if not source_ids:
            errors.append(f"{pointer}.source_event_ids: must include at least one event id")
        for source_id in source_ids:
            if source_id not in event_id_set:
                errors.append(f"{pointer}.source_event_ids: unknown event id {source_id!r}")

        validate_string_list(item.get("keywords"), f"{pointer}.keywords", errors)


def validate_session(data: Dict[str, Any], errors: List[str]) -> None:
    session = expect_dict(data, "session", errors, "$")
    if session is None:
        return

    number = session.get("session_number")
    if not isinstance(number, int) or number <= 0:
        errors.append("$.session.session_number: expected positive integer")

    date = expect_non_empty_string(session.get("date"), "$.session.date", errors)
    if date and not DATE_RE.match(date):
        errors.append("$.session.date: expected YYYY-MM-DD")

    source_note = expect_non_empty_string(session.get("source_note"), "$.session.source_note", errors)
    if source_note:
        note_path = REPO_ROOT / source_note
        if not note_path.exists():
            errors.append(f"$.session.source_note: file does not exist at {source_note}")

    scope = expect_non_empty_string(session.get("scope_used"), "$.session.scope_used", errors)
    if scope and scope not in {"now", "full_note"}:
        errors.append("$.session.scope_used: expected 'now' or 'full_note'")


def validate_context(data: Dict[str, Any], errors: List[str]) -> None:
    context = expect_dict(data, "context", errors, "$")
    if context is None:
        return
    if not isinstance(context.get("previous_summaries"), list):
        errors.append("$.context.previous_summaries: expected list of summary paths")
        return
    validate_string_list(context.get("previous_summaries"), "$.context.previous_summaries", errors)


def validate_root(data: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["$: expected YAML mapping at document root"]

    schema_version = data.get("schema_version")
    if schema_version != 2:
        errors.append("$.schema_version: expected integer 2")

    collect_placeholders(data, "$", errors)
    validate_session(data, errors)
    validate_context(data, errors)
    event_ids = validate_events(data, errors)
    validate_quest_candidates(data, event_ids, errors)
    return errors


def write_report(report_path: Path, target_path: Path, errors: Sequence[str]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Events Lint Report",
        "",
        f"- Timestamp: {dt.datetime.utcnow().isoformat(timespec='seconds')}Z",
        f"- Target: `{path_label(target_path)}`",
        f"- Errors: {len(errors)}",
        "",
        "## Errors",
    ]
    if errors:
        lines.extend(f"- {err}" for err in errors)
    else:
        lines.append("- None")
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def resolve_paths(args: argparse.Namespace) -> Tuple[Path, Path]:
    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = (REPO_ROOT / target).resolve()
        if args.report:
            report = Path(args.report)
            if not report.is_absolute():
                report = (REPO_ROOT / report).resolve()
        else:
            report = target.with_name("events-lint-report.md")
        return target, report

    session = select_session(args.session)
    meta_dir = session_meta_dir(session)
    return meta_dir / "events.yaml", meta_dir / "events-lint-report.md"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Strictly lint events.yaml artifacts")
    p.add_argument("--session", default="latest session", help='Session selector like "Session 12"')
    p.add_argument("--file", default="", help="Explicit events.yaml path")
    p.add_argument("--report", default="", help="Optional report output path")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        target_path, report_path = resolve_paths(args)
        data = load_yaml(target_path)
        errors = validate_root(data)
    except ValueError as exc:
        target_for_report = Path(args.file) if args.file else Path("events.yaml")
        report_path = Path(args.report) if args.report else (REPO_ROOT / ".dnd-meta" / "events-lint-report.md")
        if not report_path.is_absolute():
            report_path = (REPO_ROOT / report_path).resolve()
        write_report(report_path, target_for_report, [str(exc)])
        print(f"events lint failed: {exc}")
        print(f"report: {path_label(report_path)}")
        return 1

    write_report(report_path, target_path, errors)
    if errors:
        print(f"events lint failed: {len(errors)} errors")
        print(f"report: {path_label(report_path)}")
        return 1

    print(f"events lint passed: {path_label(target_path)}")
    print(f"report: {path_label(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
