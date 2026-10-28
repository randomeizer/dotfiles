#!/usr/bin/env python3
"""Strict linter for session world.yaml artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


ENTITY_TYPES = {"character", "location", "faction", "item", "creature", "unknown"}
RESOLUTION_STATUSES = {"resolved", "triage_required", "unresolved", "ignored"}
OPEN_STATUSES = {"triage_required", "unresolved"}
RESOLVED_STATUSES = {"resolved", "ignored"}
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
    validate_string_list(context.get("previous_summaries"), "$.context.previous_summaries", errors)
    expect_non_empty_string(context.get("based_on_events_file"), "$.context.based_on_events_file", errors)


def event_ids_from_events_yaml(path: Path, errors: List[str]) -> Set[str]:
    if not path.exists():
        errors.append(f"events file not found for cross-reference validation: {path_label(path)}")
        return set()
    loaded = load_yaml(path)
    if not isinstance(loaded, dict):
        errors.append("events file root must be a mapping")
        return set()
    events = loaded.get("events")
    if not isinstance(events, list):
        errors.append("events file must include an events list")
        return set()
    ids = set()
    for idx, item in enumerate(events):
        if not isinstance(item, dict):
            errors.append(f"events file events[{idx}] is not a mapping")
            continue
        event_id = item.get("id")
        if isinstance(event_id, str) and event_id.strip():
            ids.add(event_id.strip())
    if not ids:
        errors.append("events file contains no usable event IDs")
    return ids


def validate_entities(
    data: Dict[str, Any], valid_event_ids: Set[str], errors: List[str]
) -> Tuple[int, int, int]:
    entities = expect_list(data, "entities", errors, "$")
    if entities is None:
        return 0, 0, 0
    if not entities:
        errors.append("$.entities: must include at least one entity")
        return 0, 0, 0

    open_count = 0
    blocking_count = 0
    resolved_count = 0

    for idx, item in enumerate(entities):
        pointer = f"$.entities[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{pointer}: expected mapping")
            continue

        expect_non_empty_string(item.get("mention"), f"{pointer}.mention", errors)
        expect_non_empty_string(item.get("canonical_title"), f"{pointer}.canonical_title", errors)

        entity_type = expect_non_empty_string(item.get("entity_type"), f"{pointer}.entity_type", errors)
        if entity_type and entity_type not in ENTITY_TYPES:
            errors.append(f"{pointer}.entity_type: expected one of {', '.join(sorted(ENTITY_TYPES))}")

        status = expect_non_empty_string(item.get("resolution_status"), f"{pointer}.resolution_status", errors)
        if status and status not in RESOLUTION_STATUSES:
            errors.append(
                f"{pointer}.resolution_status: expected one of {', '.join(sorted(RESOLUTION_STATUSES))}"
            )

        blocking = item.get("blocking")
        if not isinstance(blocking, bool):
            errors.append(f"{pointer}.blocking: expected boolean")
            blocking = False

        confidence = item.get("confidence")
        if not is_number(confidence):
            errors.append(f"{pointer}.confidence: expected numeric value in [0, 1]")
        elif confidence < 0 or confidence > 1:
            errors.append(f"{pointer}.confidence: out of range [0, 1]")

        validate_string_list(item.get("aliases"), f"{pointer}.aliases", errors)

        event_ids = validate_string_list(item.get("event_ids"), f"{pointer}.event_ids", errors)
        if not event_ids:
            errors.append(f"{pointer}.event_ids: must include at least one event id")
        for event_id in event_ids:
            if event_id not in valid_event_ids:
                errors.append(f"{pointer}.event_ids: unknown event id {event_id!r}")

        spans = item.get("evidence_spans")
        if not isinstance(spans, list) or not spans:
            errors.append(f"{pointer}.evidence_spans: expected non-empty list")
        else:
            for span_idx, span in enumerate(spans):
                span_pointer = f"{pointer}.evidence_spans[{span_idx}]"
                if not isinstance(span, dict):
                    errors.append(f"{span_pointer}: expected mapping")
                    continue
                start = expect_non_empty_string(span.get("start_index"), f"{span_pointer}.start_index", errors)
                end = expect_non_empty_string(span.get("end_index"), f"{span_pointer}.end_index", errors)
                expect_non_empty_string(span.get("excerpt"), f"{span_pointer}.excerpt", errors)

                start_parsed = parse_index(start) if start else None
                end_parsed = parse_index(end) if end else None
                if start and not start_parsed:
                    errors.append(f"{span_pointer}.start_index: expected line:column format with positive integers")
                if end and not end_parsed:
                    errors.append(f"{span_pointer}.end_index: expected line:column format with positive integers")
                if start_parsed and end_parsed and start_parsed > end_parsed:
                    errors.append(f"{span_pointer}: start_index must be <= end_index")

        triage_reason = item.get("triage_reason")
        triage_text = triage_reason.strip() if isinstance(triage_reason, str) else ""
        if status in OPEN_STATUSES and not triage_text:
            errors.append(f"{pointer}.triage_reason: required for {status}")

        if status in RESOLVED_STATUSES and triage_text:
            errors.append(f"{pointer}.triage_reason: must be empty when resolution_status={status}")

        if status in OPEN_STATUSES:
            open_count += 1
            if blocking:
                blocking_count += 1
        elif status in RESOLVED_STATUSES:
            resolved_count += 1

        if blocking and status in RESOLVED_STATUSES:
            errors.append(f"{pointer}: blocking=true is incompatible with resolution_status={status}")

    return open_count, blocking_count, resolved_count


def validate_triage_summary(
    data: Dict[str, Any], expected_open: int, expected_blocking: int, expected_resolved: int, errors: List[str]
) -> None:
    summary = expect_dict(data, "triage_summary", errors, "$")
    if summary is None:
        return

    open_count = summary.get("open_count")
    blocking_count = summary.get("blocking_count")
    resolved_count = summary.get("resolved_count")

    if not isinstance(open_count, int) or open_count < 0:
        errors.append("$.triage_summary.open_count: expected non-negative integer")
    if not isinstance(blocking_count, int) or blocking_count < 0:
        errors.append("$.triage_summary.blocking_count: expected non-negative integer")
    if not isinstance(resolved_count, int) or resolved_count < 0:
        errors.append("$.triage_summary.resolved_count: expected non-negative integer")

    if isinstance(open_count, int) and open_count != expected_open:
        errors.append(
            f"$.triage_summary.open_count: expected {expected_open} based on entities, found {open_count}"
        )
    if isinstance(blocking_count, int) and blocking_count != expected_blocking:
        errors.append(
            f"$.triage_summary.blocking_count: expected {expected_blocking} based on entities, found {blocking_count}"
        )
    if isinstance(resolved_count, int) and resolved_count != expected_resolved:
        errors.append(
            f"$.triage_summary.resolved_count: expected {expected_resolved} based on entities, found {resolved_count}"
        )


def validate_root(data: Any, events_path: Path) -> List[str]:
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["$: expected YAML mapping at document root"]

    schema_version = data.get("schema_version")
    if schema_version != 2:
        errors.append("$.schema_version: expected integer 2")

    collect_placeholders(data, "$", errors)
    validate_session(data, errors)
    validate_context(data, errors)

    event_ids = event_ids_from_events_yaml(events_path, errors)
    open_count, blocking_count, resolved_count = validate_entities(data, event_ids, errors)
    validate_triage_summary(data, open_count, blocking_count, resolved_count, errors)
    return errors


def write_report(report_path: Path, world_path: Path, events_path: Path, errors: Sequence[str]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# World Lint Report",
        "",
        f"- Timestamp: {dt.datetime.utcnow().isoformat(timespec='seconds')}Z",
        f"- Target: `{path_label(world_path)}`",
        f"- Events Source: `{path_label(events_path)}`",
        f"- Errors: {len(errors)}",
        "",
        "## Errors",
    ]
    if errors:
        lines.extend(f"- {err}" for err in errors)
    else:
        lines.append("- None")
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def resolve_world_and_report_paths(args: argparse.Namespace) -> Tuple[Path, Path, Optional[Dict[str, Any]]]:
    if args.file:
        world_path = Path(args.file)
        if not world_path.is_absolute():
            world_path = (REPO_ROOT / world_path).resolve()
        if args.report:
            report = Path(args.report)
            if not report.is_absolute():
                report = (REPO_ROOT / report).resolve()
        else:
            report = world_path.with_name("world-lint-report.md")
        return world_path, report, None

    session = select_session(args.session)
    meta_dir = session_meta_dir(session)
    return meta_dir / "world.yaml", meta_dir / "world-lint-report.md", session


def resolve_events_path(args: argparse.Namespace, world_path: Path, session: Optional[Dict[str, Any]]) -> Path:
    if args.events_file:
        events_path = Path(args.events_file)
        if not events_path.is_absolute():
            events_path = (REPO_ROOT / events_path).resolve()
        return events_path

    if session is not None:
        return session_meta_dir(session) / "events.yaml"

    return world_path.with_name("events.yaml")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Strictly lint world.yaml artifacts")
    p.add_argument("--session", default="latest session", help='Session selector like "Session 12"')
    p.add_argument("--file", default="", help="Explicit world.yaml path")
    p.add_argument("--events-file", default="", help="Optional events.yaml path override")
    p.add_argument("--report", default="", help="Optional report output path")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        world_path, report_path, session = resolve_world_and_report_paths(args)
        events_path = resolve_events_path(args, world_path, session)
        data = load_yaml(world_path)
        errors = validate_root(data, events_path)
    except ValueError as exc:
        world_for_report = Path(args.file) if args.file else Path("world.yaml")
        events_for_report = Path(args.events_file) if args.events_file else Path("events.yaml")
        report_path = Path(args.report) if args.report else (REPO_ROOT / ".dnd-meta" / "world-lint-report.md")
        if not report_path.is_absolute():
            report_path = (REPO_ROOT / report_path).resolve()
        write_report(report_path, world_for_report, events_for_report, [str(exc)])
        print(f"world lint failed: {exc}")
        print(f"report: {path_label(report_path)}")
        return 1

    write_report(report_path, world_path, events_path, errors)
    if errors:
        print(f"world lint failed: {len(errors)} errors")
        print(f"report: {path_label(report_path)}")
        return 1

    print(f"world lint passed: {path_label(world_path)}")
    print(f"report: {path_label(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
