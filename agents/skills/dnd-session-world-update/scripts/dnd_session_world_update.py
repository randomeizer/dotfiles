#!/usr/bin/env python3
"""Standalone world-update runner for Stage 1 session artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Shared scripts belong to the installed suite; campaign data belongs to the vault.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dnd-session-review" / "scripts"))
from dnd_vault import find_vault_root, load_campaign_config

REPO_ROOT = find_vault_root()
CAMPAIGN_CONFIG = load_campaign_config(REPO_ROOT)

SESSIONS_DIR = REPO_ROOT / "Sessions"
NOTES_DIR = SESSIONS_DIR / "Notes"
SUMMARIES_DIR = SESSIONS_DIR / "Summaries"

WORLD_DIR = REPO_ROOT / "World"
TEMPLATES_DIR = REPO_ROOT / "Templates"

META_DIR = REPO_ROOT / ".dnd-meta"
META_SESSIONS_DIR = META_DIR / "sessions"
RESOLVER_PATH = META_DIR / "entity-resolver.yaml"
TRIAGE_DECISIONS_PATH = META_DIR / "triage-decisions.yaml"
LINT_REPORT_PATH = META_DIR / "markdown-lint-report.md"

WORLD_TYPE_DIR = {
    "character": WORLD_DIR / "Characters",
    "location": WORLD_DIR / "Locations",
    "faction": WORLD_DIR / "Factions",
    "item": WORLD_DIR / "Items",
    "creature": WORLD_DIR / "Creatures",
}
WORLD_DIR_TO_TYPE = {str(path.resolve()): key for key, path in WORLD_TYPE_DIR.items()}

WORLD_TEMPLATE = {
    "character": TEMPLATES_DIR / "character-template.md",
    "location": TEMPLATES_DIR / "location-template.md",
    "faction": TEMPLATES_DIR / "faction-template.md",
    "item": TEMPLATES_DIR / "item-template.md",
    "creature": TEMPLATES_DIR / "creature-template.md",
}

MANAGED_START = "<!-- dnd-managed:start -->"
MANAGED_END = "<!-- dnd-managed:end -->"

WORLD_OPEN_STATUSES = {"triage_required", "unresolved"}
FORCED_ENTITY_TYPES = CAMPAIGN_CONFIG.get("forced_entity_types", {})
TRANSFER_VERB_RE = re.compile(
    r"\b(give|gives|gave|gift|gifts|gifted|loan|loans|loaned|lend|lends|lent|buy|buys|bought|purchase|purchases|purchased|sell|sells|sold|hand|hands|handed|pass|passes|passed|stole|stolen|retrieve|retrieved|acquire|acquired)\b",
    re.IGNORECASE,
)
ORIGIN_HINT_RE = re.compile(
    r"\b(from|origin|source|obtained|found|recovered|purchased)\b",
    re.IGNORECASE,
)

DEFAULT_RESOLVER_ENTITIES = CAMPAIGN_CONFIG.get("resolver_seeds", [])

DRY_RUN = False
SUMMARY_HIT_CACHE: Dict[str, int] = {}


class WorldUpdateError(Exception):
    pass


@dataclass
class SessionRef:
    session_number: int
    date: str
    filename: str
    path: Path

    @property
    def session_label(self) -> str:
        return f"Session {self.session_number:02d}"


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return normalize_space(lowered)


def dedupe_preserve(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def forced_entity_type(canonical: str, entity_type: str) -> str:
    forced = FORCED_ENTITY_TYPES.get(normalize_name(canonical))
    if forced in WORLD_TYPE_DIR:
        return forced
    return entity_type


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if DRY_RUN:
        print(f"[dry-run] skip write: {path.relative_to(REPO_ROOT)}")
        return
    path.write_text(content, encoding="utf-8")


def summary_session_hits(canonical: str) -> int:
    key = normalize_name(canonical)
    if key in SUMMARY_HIT_CACHE:
        return SUMMARY_HIT_CACHE[key]

    link_pattern = re.compile(rf"\[\[{re.escape(canonical)}(?:\\?\|[^\]]+)?\]\]")
    plain_pattern = re.compile(rf"\b{re.escape(canonical)}\b", flags=re.IGNORECASE)
    hits = 0
    for path in sorted(SUMMARIES_DIR.glob("*.md")):
        text = read_text(path)
        if link_pattern.search(text) or plain_pattern.search(text):
            hits += 1

    SUMMARY_HIT_CACHE[key] = hits
    return hits


def migrate_forced_entity_path(canonical: str, entity_type: str) -> None:
    forced_type = FORCED_ENTITY_TYPES.get(normalize_name(canonical))
    if forced_type != entity_type:
        return

    target = WORLD_TYPE_DIR[entity_type] / f"{canonical}.md"
    if target.exists():
        return

    for source_type, folder in WORLD_TYPE_DIR.items():
        if source_type == entity_type:
            continue
        source = folder / f"{canonical}.md"
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if DRY_RUN:
            print(f"[dry-run] migrate {source.relative_to(REPO_ROOT)} -> {target.relative_to(REPO_ROOT)}")
            return
        source.replace(target)
        print(f"Migrated {source.relative_to(REPO_ROOT)} -> {target.relative_to(REPO_ROOT)}")
        return


def split_frontmatter(text: str) -> Tuple[str, str]:
    match = re.match(r"\A---\n.*?\n---\n?", text, re.DOTALL)
    if not match:
        return "", text
    return match.group(0), text[match.end() :]


def ruby_yaml_to_json(text: str) -> Any:
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
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise WorldUpdateError(f"Unable to parse YAML via ruby: {exc.stderr.strip()}") from exc
    return json.loads(proc.stdout)


def json_to_ruby_yaml(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    try:
        proc = subprocess.run(
            [
                "ruby",
                "-ryaml",
                "-rjson",
                "-e",
                "obj = JSON.parse(STDIN.read); puts YAML.dump(obj)",
            ],
            input=payload,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise WorldUpdateError(f"Unable to serialize YAML via ruby: {exc.stderr.strip()}") from exc
    return proc.stdout


def ensure_meta_dir() -> None:
    META_DIR.mkdir(parents=True, exist_ok=True)
    META_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def load_data(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    raw = read_text(path).strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return ruby_yaml_to_json(raw)


def dump_data(path: Path, data: Any) -> None:
    ensure_meta_dir()
    yaml_text = json_to_ruby_yaml(data)
    write_text(path, yaml_text if yaml_text.endswith("\n") else yaml_text + "\n")


def migrate_metadata_layout() -> None:
    ensure_meta_dir()
    legacy_map = {
        WORLD_DIR / ".entity-resolver.yaml": RESOLVER_PATH,
        WORLD_DIR / ".triage-decisions.yaml": TRIAGE_DECISIONS_PATH,
    }
    for legacy, target in legacy_map.items():
        if not legacy.exists():
            continue
        data = load_data(legacy, {})
        dump_data(target, data)
        if not DRY_RUN:
            legacy.unlink()


def discover_sessions() -> List[SessionRef]:
    pattern = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s*-\s*Session\s*(?P<num>\d{1,3})\.md$")
    sessions: List[SessionRef] = []
    for path in sorted(NOTES_DIR.glob("*.md")):
        match = pattern.match(path.name)
        if not match:
            continue
        sessions.append(
            SessionRef(
                session_number=int(match.group("num")),
                date=match.group("date"),
                filename=path.name,
                path=path,
            )
        )
    if not sessions:
        raise WorldUpdateError("No session notes found in Sessions/Notes.")
    return sessions


def select_session(selector: Optional[str]) -> SessionRef:
    sessions = discover_sessions()
    by_number = sorted(sessions, key=lambda s: (s.session_number, s.date, s.filename))

    if selector is None:
        return by_number[-1]

    candidate = selector.strip().lower()
    if candidate == "latest session":
        return by_number[-1]

    match = re.search(r"session\s*(\d{1,3})", candidate)
    if not match:
        raise WorldUpdateError(f"Unsupported session selector: {selector}")

    requested = int(match.group(1))
    filtered = [s for s in sessions if s.session_number == requested]
    if not filtered:
        raise WorldUpdateError(f"No session note found for Session {requested:02d}.")
    return sorted(filtered, key=lambda s: (s.date, s.filename))[-1]


def summary_filename(session: SessionRef) -> str:
    return f"{session.date} - Session {session.session_number:03d} - Summary.md"


def summary_stem(session: SessionRef) -> str:
    return Path(summary_filename(session)).stem


def summary_link(session: SessionRef) -> str:
    return f"[[{summary_stem(session)}|Session {session.session_number:03d}]]"


def session_meta_key(session: SessionRef) -> str:
    return f"{session.date}-s{session.session_number:03d}"


def session_meta_dir(session: SessionRef) -> Path:
    return META_SESSIONS_DIR / session_meta_key(session)


def world_brief_path_for(session: SessionRef) -> Path:
    return session_meta_dir(session) / "world-narrative-brief.yaml"


def events_path_for(session: SessionRef) -> Path:
    return session_meta_dir(session) / "events.yaml"


def world_path_for(session: SessionRef) -> Path:
    return session_meta_dir(session) / "world.yaml"


def load_stage1_artifacts(session: SessionRef) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    events_path = events_path_for(session)
    world_path = world_path_for(session)

    missing = []
    if not events_path.exists():
        missing.append(str(events_path.relative_to(REPO_ROOT)))
    if not world_path.exists():
        missing.append(str(world_path.relative_to(REPO_ROOT)))
    if missing:
        listed = ", ".join(f"`{item}`" for item in missing)
        raise WorldUpdateError(f"Missing Stage 1 artifacts: {listed}")

    events_data = load_data(events_path, None)
    world_data = load_data(world_path, None)

    if not isinstance(events_data, dict):
        raise WorldUpdateError(f"Invalid events artifact: `{events_path.relative_to(REPO_ROOT)}`")
    if not isinstance(world_data, dict):
        raise WorldUpdateError(f"Invalid world artifact: `{world_path.relative_to(REPO_ROOT)}`")

    return events_data, world_data


def world_triage_state(world_data: Dict[str, Any]) -> Dict[str, int]:
    entries = world_data.get("entities", []) if isinstance(world_data, dict) else []
    if not isinstance(entries, list):
        entries = []

    open_items = [
        item
        for item in entries
        if isinstance(item, dict)
        and normalize_space(str(item.get("resolution_status", ""))).lower() in WORLD_OPEN_STATUSES
    ]
    blocking = [item for item in open_items if bool(item.get("blocking"))]
    return {
        "open_count": len(open_items),
        "blocking_count": len(blocking),
    }


def to_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def build_world_analysis(events_data: Dict[str, Any], world_data: Dict[str, Any]) -> Dict[str, Any]:
    raw_events = events_data.get("events", [])
    if not isinstance(raw_events, list):
        raw_events = []

    events: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_events, start=1):
        if not isinstance(item, dict):
            continue
        title = normalize_space(str(item.get("title", "")))
        description = normalize_space(str(item.get("description", "")))
        excerpt = normalize_space(str(item.get("source_excerpt", "")))
        text = f"{title}: {description}" if title and description else (title or description or excerpt)
        if not text:
            continue
        participants = [
            normalize_space(str(value))
            for value in item.get("participants", [])
            if normalize_space(str(value))
        ] if isinstance(item.get("participants"), list) else []
        locations = [
            normalize_space(str(value))
            for value in item.get("locations", [])
            if normalize_space(str(value))
        ] if isinstance(item.get("locations"), list) else []
        factions = [
            normalize_space(str(value))
            for value in item.get("factions", [])
            if normalize_space(str(value))
        ] if isinstance(item.get("factions"), list) else []
        items = [
            normalize_space(str(value))
            for value in item.get("items", [])
            if normalize_space(str(value))
        ] if isinstance(item.get("items"), list) else []
        events.append(
            {
                "id": normalize_space(str(item.get("id", ""))) or f"ev-{idx:03d}",
                "text": text,
                "confidence": to_float(item.get("confidence"), 0.7),
                "title": title,
                "description": description,
                "source_excerpt": excerpt,
                "participants": participants,
                "locations": locations,
                "factions": factions,
                "items": items,
            }
        )

    raw_entities = world_data.get("entities", [])
    if not isinstance(raw_entities, list):
        raw_entities = []

    entities: List[Dict[str, Any]] = []
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        canonical = normalize_space(str(item.get("canonical_title", "")))
        if not canonical:
            continue
        entity_type = normalize_space(str(item.get("entity_type", ""))).lower()
        entity_type = forced_entity_type(canonical, entity_type)
        if entity_type not in WORLD_TYPE_DIR:
            continue
        aliases = [
            normalize_space(str(value))
            for value in item.get("aliases", [])
            if normalize_space(str(value))
        ] if isinstance(item.get("aliases"), list) else []
        event_ids = [
            normalize_space(str(value))
            for value in item.get("event_ids", [])
            if normalize_space(str(value))
        ] if isinstance(item.get("event_ids"), list) else []
        evidence_excerpts: List[str] = []
        spans = item.get("evidence_spans", [])
        if isinstance(spans, list):
            for span in spans:
                if not isinstance(span, dict):
                    continue
                excerpt = normalize_space(str(span.get("excerpt", "")))
                if excerpt:
                    evidence_excerpts.append(excerpt)
        entities.append(
            {
                "mention": normalize_space(str(item.get("mention", ""))) or canonical,
                "canonical_title": canonical,
                "entity_type": entity_type,
                "resolution_status": normalize_space(str(item.get("resolution_status", ""))).lower(),
                "confidence": to_float(item.get("confidence"), 0.7),
                "aliases": aliases,
                "event_ids": event_ids,
                "evidence_excerpts": dedupe_preserve(evidence_excerpts),
            }
        )

    return {"events": events, "entities": entities}


def link_entity(surface: str, canonical: str) -> str:
    if normalize_name(surface) == normalize_name(canonical):
        return f"[[{canonical}]]"
    return f"[[{canonical}|{surface}]]"


def escape_wikilink_pipes_in_tables(text: str) -> str:
    link_pattern = re.compile(r"\[\[([^\]]*?)(?<!\\)\|([^\]]+)\]\]")
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        if line.lstrip().startswith("|"):
            line = link_pattern.sub(r"[[\1\\|\2]]", line)
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def protect_existing_links(text: str) -> Tuple[str, Dict[str, str]]:
    mapping: Dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        token = f"__LINK_{len(mapping)}__"
        mapping[token] = match.group(0)
        return token

    safe = re.sub(r"\[\[[^\]]+\]\]", repl, text)
    return safe, mapping


def restore_existing_links(text: str, mapping: Dict[str, str]) -> str:
    for token, original in mapping.items():
        text = text.replace(token, original)
    return text


def resolver_aliases(resolver: Dict[str, Any]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for entry in resolver.get("entities", []):
        canonical = normalize_space(str(entry.get("canonical_title", "")))
        if not canonical:
            continue
        names = [canonical]
        aliases = entry.get("true_aliases", [])
        if isinstance(aliases, list):
            names.extend(normalize_space(str(alias)) for alias in aliases if normalize_space(str(alias)))
        for name in dedupe_preserve(names):
            pairs.append((name, canonical))
    pairs.sort(key=lambda value: len(value[0]), reverse=True)
    return pairs


def linkify_text(text: str, resolver: Dict[str, Any]) -> str:
    frontmatter = ""
    body = text
    frontmatter_match = re.match(r"\A---\n.*?\n---\n?", text, re.DOTALL)
    if frontmatter_match:
        frontmatter = frontmatter_match.group(0)
        body = text[frontmatter_match.end() :]

    safe = body
    for surface, canonical in resolver_aliases(resolver):
        safe, mapping = protect_existing_links(safe)
        pattern = re.compile(rf"(?<![\w\]])({re.escape(surface)})(?![\w\[])")

        def repl(match: re.Match[str]) -> str:
            return link_entity(match.group(1), canonical)

        safe = pattern.sub(repl, safe)
        safe = restore_existing_links(safe, mapping)

    return frontmatter + safe


def ensure_resolver_defaults() -> Dict[str, Any]:
    resolver = load_data(RESOLVER_PATH, {"schema_version": 1, "entities": []})
    if not isinstance(resolver, dict):
        resolver = {"schema_version": 1, "entities": []}
    resolver.setdefault("schema_version", 1)
    resolver.setdefault("entities", [])
    if not isinstance(resolver["entities"], list):
        resolver["entities"] = []

    existing = {
        normalize_space(str(item.get("canonical_title", "")))
        for item in resolver["entities"]
        if isinstance(item, dict)
    }
    for seed in DEFAULT_RESOLVER_ENTITIES:
        if seed["canonical_title"] in existing:
            continue
        resolver["entities"].append(seed)
    dump_data(RESOLVER_PATH, resolver)
    return resolver


def augment_resolver_from_analysis(
    resolver: Dict[str, Any], analysis: Dict[str, Any], session: SessionRef
) -> Dict[str, Any]:
    resolver.setdefault("entities", [])
    if not isinstance(resolver["entities"], list):
        resolver["entities"] = []

    by_canonical: Dict[str, Dict[str, Any]] = {}
    for entry in resolver["entities"]:
        if not isinstance(entry, dict):
            continue
        canonical = normalize_space(str(entry.get("canonical_title", "")))
        if canonical:
            by_canonical[canonical] = entry

    changed = False
    for item in analysis.get("entities", []):
        canonical = normalize_space(str(item.get("canonical_title", "")))
        if not canonical:
            continue
        aliases = [
            normalize_space(str(alias))
            for alias in item.get("aliases", [])
            if normalize_space(str(alias))
        ]
        aliases = dedupe_preserve(aliases)

        existing = by_canonical.get(canonical)
        analysis_entity_type = forced_entity_type(
            canonical, normalize_space(str(item.get("entity_type", "unknown"))) or "unknown"
        )
        if existing is None:
            resolver["entities"].append(
                {
                    "canonical_title": canonical,
                    "entity_type": analysis_entity_type,
                    "true_aliases": aliases,
                    "observed_variants": [],
                    "last_seen_session": session.session_number,
                    "confidence_notes": "Synced from Stage 1 world entity metadata.",
                }
            )
            changed = True
            continue

        old_aliases = existing.get("true_aliases", [])
        if not isinstance(old_aliases, list):
            old_aliases = []
        merged_aliases = dedupe_preserve(
            [normalize_space(str(alias)) for alias in old_aliases if normalize_space(str(alias))] + aliases
        )
        if merged_aliases != old_aliases:
            existing["true_aliases"] = merged_aliases
            changed = True

        if existing.get("entity_type") in {None, "", "unknown"} and analysis_entity_type:
            existing["entity_type"] = analysis_entity_type
            changed = True
        if existing.get("last_seen_session") != session.session_number:
            existing["last_seen_session"] = session.session_number
            changed = True

    if changed:
        dump_data(RESOLVER_PATH, resolver)
    return resolver


def normalize_existing_wikilinks(text: str, analysis: Dict[str, Any]) -> str:
    alias_lookup = build_alias_lookup(analysis)
    known_titles = {
        normalize_space(str(item.get("canonical_title", "")))
        for item in analysis.get("entities", [])
        if normalize_space(str(item.get("canonical_title", "")))
    }
    known_stems = {path.stem for path in REPO_ROOT.rglob("*.md")}

    pattern = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")

    def repl(match: re.Match[str]) -> str:
        target = normalize_space(match.group(1))
        display = normalize_space(match.group(2) or "")
        if not target:
            return match.group(0)

        if "/" in target:
            candidate = REPO_ROOT / target
            if candidate.suffix != ".md":
                candidate = candidate.with_suffix(".md")
            if candidate.exists():
                return match.group(0)
        elif target in known_stems:
            return match.group(0)

        canonical = alias_lookup.get(normalize_name(target))
        if canonical:
            visible = display or target
            return link_entity(visible, canonical)

        # For unresolved placeholders/unknowns, keep readable plain text.
        return display or target

    return pattern.sub(repl, text)


def strip_managed_blocks(body: str) -> str:
    stripped = re.sub(
        re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END),
        "",
        body,
        flags=re.DOTALL,
    )
    return stripped.strip("\n")


def extract_managed_core(body: str) -> str:
    managed_match = re.search(
        re.escape(MANAGED_START) + r"\s*(.*?)\s*" + re.escape(MANAGED_END),
        body,
        flags=re.DOTALL,
    )
    if managed_match:
        return managed_match.group(1).strip()
    return remove_notes_section(strip_managed_blocks(body))


def count_timeline_sessions(text: str) -> int:
    return len(
        re.findall(
            r"^### \[\[\d{4}-\d{2}-\d{2} - Session \d{3} - Summary\|Session \d{3}\]\]\s*$",
            text,
            flags=re.MULTILINE,
        )
    )


def count_prior_timeline_sessions(text: str, session: SessionRef) -> int:
    pattern = re.compile(
        r"^### \[\[(\d{4}-\d{2}-\d{2}) - Session (\d{3}) - Summary\|Session \d{3}\]\]\s*$",
        flags=re.MULTILINE,
    )
    seen = set()
    for match in pattern.finditer(text):
        session_id = f"{match.group(1)}-s{match.group(2)}"
        if session_id == f"{session.date}-s{session.session_number:03d}":
            continue
        seen.add(session_id)
    return len(seen)


def extract_h2_section(core: str, heading: str) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)")
    match = pattern.search(core)
    if not match:
        return ""
    return match.group(1).strip()


def replace_h2_section(core: str, heading: str, content: str) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)")
    replacement = f"{heading}\n\n{content.strip()}\n\n"
    if pattern.search(core):
        return pattern.sub(replacement, core, count=1).strip() + "\n"
    core_clean = core.strip()
    if not core_clean:
        return f"{replacement.strip()}\n"
    return f"{core_clean}\n\n{replacement.strip()}\n"


def remove_h2_section(core: str, heading: str) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)")
    cleaned = pattern.sub("", core).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def strip_recent_development_lines(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    kept: List[str] = []
    for line in lines:
        if re.match(r"^\s*-?\s*Recent development \(Session \d{3}\):", line, flags=re.IGNORECASE):
            continue
        kept.append(line)
    merged = "\n".join(kept).strip()
    return re.sub(r"\n{3,}", "\n\n", merged).strip()


def parse_h2_sections(core: str) -> Tuple[List[str], Dict[str, str]]:
    matches = list(re.finditer(r"(?m)^##\s+.+$", core))
    if not matches:
        return [], {}
    order: List[str] = []
    sections: Dict[str, str] = {}
    for idx, match in enumerate(matches):
        heading = match.group(0).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(core)
        content = core[start:end].strip()
        order.append(heading)
        sections[heading] = content
    return order, sections


def render_h2_sections(order: List[str], sections: Dict[str, str]) -> str:
    blocks: List[str] = []
    for heading in order:
        content = normalize_space(sections.get(heading, ""))
        raw = sections.get(heading, "").strip()
        if raw:
            blocks.append(f"{heading}\n\n{raw}")
        elif content:
            blocks.append(f"{heading}\n\n{content}")
        else:
            blocks.append(heading)
    return "\n\n".join(blocks).strip()


def is_low_signal_section(content: str) -> bool:
    plain = normalize_space(strip_wikilinks(content))
    if not plain:
        return True
    lowered = plain.lower()
    if "{{" in content or "}}" in content:
        return True
    if lowered in {"unknown", "unspecified", "none recorded"}:
        return True
    generic_markers = [
        "is a specific place referenced in active scene flow",
        "provides immediate geographic context for party actions",
        "is a recurring regional anchor that concentrates people, authority, and logistical options",
        "is a recurring location with narrative weight beyond a single encounter",
        "no additional state changes were clearly documented in this session",
        "add manual notes here. keep this section outside the managed block",
    ]
    return any(marker in lowered for marker in generic_markers)


def merge_existing_authored_sections(
    existing_body: str,
    generated_core: str,
    entity_type: str,
) -> str:
    existing_core = extract_managed_core(existing_body)
    existing_order, existing_sections = parse_h2_sections(existing_core)
    if not existing_order:
        return generated_core

    gen_order, gen_sections = parse_h2_sections(generated_core)
    if not gen_order:
        return generated_core

    structural = {"## 🕰️ Session Timeline", "## 🛠️ Managed Updates", "## 🔗 Related Entities"}
    merged = dict(gen_sections)
    for heading in gen_order:
        if heading in structural:
            continue
        if heading == "## 🌐 Overview":
            continue
        existing_content = existing_sections.get(heading, "").strip()
        if not existing_content:
            continue
        if is_low_signal_section(existing_content):
            continue
        merged[heading] = existing_content

    return render_h2_sections(gen_order, merged)


def merge_existing_overview(
    existing_body: str,
    generated_core: str,
    entity_type: str,
    session: SessionRef,
    context: Dict[str, Any],
) -> str:
    existing_core = extract_managed_core(existing_body)
    existing_overview = extract_h2_section(existing_core, "## 🌐 Overview")
    if not existing_overview or is_placeholder_text(existing_overview):
        new_overview = extract_h2_section(generated_core, "## 🌐 Overview")
        if new_overview:
            cleaned = strip_recent_development_lines(new_overview)
            return replace_h2_section(generated_core, "## 🌐 Overview", cleaned).strip()
        return generated_core

    new_overview = extract_h2_section(generated_core, "## 🌐 Overview")
    if not new_overview:
        return generated_core

    existing_overview = strip_recent_development_lines(existing_overview)
    new_overview = strip_recent_development_lines(new_overview)

    if entity_type == "location" and not bool(context.get("is_recurring_location")):
        return replace_h2_section(generated_core, "## 🌐 Overview", new_overview).strip()
    if entity_type == "location" and bool(context.get("is_recurring_location")):
        existing_lower = existing_overview.lower()
        new_lower = new_overview.lower()
        if "in this session" in existing_lower and "broader story" in new_lower:
            return replace_h2_section(generated_core, "## 🌐 Overview", new_overview).strip()

    if is_low_signal_section(new_overview) and not is_low_signal_section(existing_overview):
        chosen = existing_overview
    else:
        chosen = new_overview
    return replace_h2_section(generated_core, "## 🌐 Overview", chosen).strip()


def remove_notes_section(body: str) -> str:
    match = re.search(r"^##\s+📝\s+Notes\s*$", body, re.MULTILINE)
    if not match:
        return body.strip("\n")
    start = match.start()
    after = match.end()
    next_heading = re.search(r"^##\s+", body[after:], re.MULTILINE)
    end = after + next_heading.start() if next_heading else len(body)
    prefix = body[:start].rstrip("\n")
    suffix = body[end:].lstrip("\n")
    if prefix and suffix:
        return f"{prefix}\n\n{suffix}".strip("\n")
    return (prefix or suffix).strip("\n")


def extract_notes_content(body: str) -> str:
    match = re.search(r"^##\s+📝\s+Notes\s*$", body, re.MULTILINE)
    if not match:
        return "- Add manual notes here. Keep this section outside the managed block."
    start = match.end()
    next_heading = re.search(r"^##\s+", body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(body)
    content = body[start:end].strip("\n")
    if not content.strip():
        return "- Add manual notes here. Keep this section outside the managed block."
    return content


def build_notes_section(content: str) -> str:
    cleaned = content.strip("\n")
    if not cleaned:
        cleaned = "- Add manual notes here. Keep this section outside the managed block."
    return f"## 📝 Notes\n\n{cleaned}\n"


def item_in_text(name: str, text: str) -> bool:
    return normalize_name(name) in normalize_name(text)


def seed_template(path: Path, replacements: Dict[str, str]) -> str:
    template = read_text(path)
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def base_world_replacements(entity_type: str, canonical: str, session: SessionRef) -> Dict[str, str]:
    common = {
        "{{Alias 1}}": canonical,
        "{{Alias 2}}": canonical,
        "{{YYYY-MM-DD}}": session.date,
        "{{XX}}": f"{session.session_number:03d}",
        "{{active|missing|deceased|unknown}}": "unknown",
    }
    if entity_type == "character":
        common.update(
            {
                "{{Character Name}}": canonical,
                "{{ally|enemy|neutral|unknown}}": "unknown",
            }
        )
    elif entity_type == "location":
        common.update(
            {
                "{{Location Name}}": canonical,
                "{{accessible|contested|destroyed|unknown}}": "unknown",
                "{{Region Name}}": "Unknown Region",
            }
        )
    elif entity_type == "faction":
        common.update(
            {
                "{{Faction Name}}": canonical,
                "{{active|fractured|defunct|unknown}}": "active",
            }
        )
    elif entity_type == "item":
        common.update(
            {
                "{{Item Name}}": canonical,
                "{{in_party_possession|lost|stored|destroyed|unknown}}": "unknown",
            }
        )
    elif entity_type == "creature":
        common.update(
            {
                "{{Creature Name}}": canonical,
                "{{active|neutralized|deceased|unknown}}": "unknown",
                "{{beast|aberration|fiend|deity_avatar|other}}": "other",
            }
        )
    return common


def confidence_label(value: float) -> str:
    if value >= 0.9:
        return "confirmed"
    if value >= 0.75:
        return "partially confirmed"
    return "unconfirmed"


def to_wikilinks(values: List[str], known_titles: Optional[set] = None, limit: int = 4) -> List[str]:
    out: List[str] = []
    for value in dedupe_preserve(values):
        if not value:
            continue
        if known_titles is not None and value not in known_titles:
            out.append(value)
            continue
        out.append(f"[[{value}]]")
        if len(out) >= limit:
            break
    return out


def first_or(values: List[str], fallback: str) -> str:
    for value in values:
        clean = normalize_space(str(value))
        if clean:
            return clean
    return fallback


def first_linked_or(values: List[str], fallback: str) -> str:
    for value in values:
        clean = normalize_space(str(value))
        if clean.startswith("[[") and clean.endswith("]]"):
            return clean
    return first_or(values, fallback)


def strip_leading_article(value: str) -> str:
    return re.sub(r"^(the|a|an)\s+", "", value.strip(), flags=re.IGNORECASE)


def strip_wikilinks(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        target = normalize_space(match.group(1))
        display = normalize_space(match.group(2) or "")
        return display or target

    return re.sub(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]", repl, text)


def looks_like_roster_line(value: str) -> bool:
    plain = normalize_space(strip_wikilinks(value))
    if not plain:
        return False

    parts = [normalize_space(part) for part in plain.split(",") if normalize_space(part)]
    if len(parts) < 3:
        return False

    name_like = 0
    for part in parts:
        scrubbed = re.sub(r"\([^)]*\)", "", part).strip()
        words = [w for w in re.split(r"\s+", scrubbed) if w]
        if not words:
            continue
        if len(words) <= 2 and all(re.match(r"^[A-Za-z'\\-]+$", w) for w in words):
            name_like += 1

    player_hits = sum(1 for token in re.findall(r"[A-Za-z]+", plain) if looks_like_player_name(token))
    return (name_like / len(parts)) >= 0.8 or player_hits >= 2


def looks_like_player_name(value: str) -> bool:
    clean = normalize_space(value)
    if not clean or " " in clean:
        return False
    low = clean.lower()
    return low in {"david", "ciara", "pony", "tony"}


def alias_candidates_for_frontmatter(context: Dict[str, Any], canonical: str) -> List[str]:
    aliases = [
        normalize_space(str(alias))
        for alias in context.get("aliases", [])
        if normalize_space(str(alias))
    ]
    out: List[str] = []
    for alias in aliases:
        if normalize_name(alias) == normalize_name(canonical):
            continue
        if looks_like_player_name(alias):
            continue
        out.append(alias)
    return dedupe_preserve(out)


def parse_frontmatter_fields(frontmatter: str) -> Tuple[List[str], Dict[str, Any]]:
    if not frontmatter.startswith("---\n"):
        return [], {}
    body = frontmatter.strip()
    if body.startswith("---"):
        body = body[3:]
    if body.endswith("---"):
        body = body[:-3]
    lines = [line.rstrip("\n") for line in body.strip("\n").splitlines()]

    order: List[str] = []
    fields: Dict[str, Any] = {}
    current_list_key: Optional[str] = None
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list_key:
            fields.setdefault(current_list_key, []).append(normalize_space(line[4:]))
            continue
        if ":" not in line:
            current_list_key = None
            continue
        key, raw_value = line.split(":", 1)
        key = normalize_space(key)
        value = raw_value.strip()
        current_list_key = None
        if key not in order:
            order.append(key)
        if value == "":
            fields[key] = []
            current_list_key = key
        else:
            fields[key] = value
    return order, fields


def is_placeholder_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = normalize_space(value)
    return text.startswith("{{") and text.endswith("}}")


def normalize_world_frontmatter(
    frontmatter: str,
    canonical: str,
    entity_type: str,
    context: Dict[str, Any],
) -> str:
    order, fields = parse_frontmatter_fields(frontmatter)
    cleaned: Dict[str, Any] = {}
    for key in order:
        if key in {"title", "aliases"}:
            continue
        cleaned[key] = fields.get(key)

    cleaned["type"] = entity_type
    if "status" not in cleaned or not normalize_space(str(cleaned.get("status", ""))):
        cleaned["status"] = "unknown"
    if is_placeholder_text(cleaned.get("status")):
        cleaned["status"] = "unknown"

    if entity_type == "location" and "region" not in cleaned:
        cleaned["region"] = "Unknown Region"
    if entity_type == "creature" and "classification" not in cleaned:
        cleaned["classification"] = "other"
    if entity_type == "creature" and is_placeholder_text(cleaned.get("classification")):
        cleaned["classification"] = "other"

    if entity_type == "character":
        cleaned["role"] = infer_character_role(canonical, context)
        cleaned["reliability"] = confidence_label(to_float(context.get("confidence"), 0.7))

    aliases = alias_candidates_for_frontmatter(context, canonical)
    if aliases:
        cleaned["aliases"] = aliases

    preferred_order = [
        "aliases",
        "type",
        "status",
        "role",
        "reliability",
        "region",
        "classification",
    ]
    remaining = [key for key in cleaned.keys() if key not in preferred_order]
    ordered_keys = [key for key in preferred_order if key in cleaned] + remaining

    lines = ["---"]
    for key in ordered_keys:
        value = cleaned[key]
        if isinstance(value, list):
            if not value:
                continue
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def character_description(canonical: str, context: Dict[str, Any]) -> str:
    marker_keys = {
        normalize_name(canonical),
        *[normalize_name(value) for value in context.get("mentions", [])],
        *[normalize_name(value) for value in context.get("aliases", [])],
    }

    candidates = dedupe_preserve(
        [normalize_space(str(v)) for v in context.get("entity_excerpts", []) if normalize_space(str(v))]
        + [normalize_space(str(v)) for v in context.get("excerpts", []) if normalize_space(str(v))]
    )
    for excerpt in candidates:
        plain_excerpt = strip_wikilinks(excerpt)
        excerpt_key = normalize_name(plain_excerpt)
        if marker_keys and not any(key and key in excerpt_key for key in marker_keys):
            continue

        # Pattern: "Name: description text"
        if ":" in plain_excerpt:
            left, right = plain_excerpt.split(":", 1)
            left_key = normalize_name(left)
            right_text = normalize_space(right)
            if (
                right_text
                and any(key and key in left_key for key in marker_keys)
                and len(right_text.split()) >= 3
            ):
                return right_text

        match = re.search(r"\(([^)]+)\)", plain_excerpt)
        if match:
            detail = normalize_space(match.group(1))
            detail_words = [w for w in re.split(r"\s+", detail) if w]
            if detail and not looks_like_player_name(detail):
                # Keep descriptive parentheticals, but ignore one-word nickname markers.
                if "," in detail or len(detail_words) >= 2:
                    return f"{canonical} is identified as {detail}."

    return "No reliable physical details were documented this session."


def build_alias_lookup(analysis: Dict[str, Any]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for item in analysis.get("entities", []):
        canonical = normalize_space(str(item.get("canonical_title", "")))
        if not canonical:
            continue
        names = [canonical, normalize_space(str(item.get("mention", "")))]
        names.extend(
            normalize_space(str(alias))
            for alias in item.get("aliases", [])
            if normalize_space(str(alias))
        )
        for name in names:
            if not name:
                continue
            lookup[normalize_name(name)] = canonical
    return lookup


def canonicalize_name(value: str, alias_lookup: Dict[str, str]) -> str:
    clean = normalize_space(value)
    if not clean:
        return clean
    key = normalize_name(clean)
    if key in alias_lookup:
        return alias_lookup[key]

    no_article_key = normalize_name(strip_leading_article(clean))
    if no_article_key in alias_lookup:
        return alias_lookup[no_article_key]

    return clean


def build_entity_context(canonical: str, entity_type: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    alias_lookup = build_alias_lookup(analysis)
    known_titles = {
        normalize_space(str(item.get("canonical_title", "")))
        for item in analysis.get("entities", [])
        if normalize_space(str(item.get("canonical_title", "")))
    }
    entity_entries = [
        item
        for item in analysis.get("entities", [])
        if item.get("canonical_title") == canonical and item.get("entity_type") == entity_type
    ]

    mentions = dedupe_preserve(
        [normalize_space(str(item.get("mention", ""))) for item in entity_entries if normalize_space(str(item.get("mention", "")))]
    )
    aliases: List[str] = []
    for item in entity_entries:
        for alias in item.get("aliases", []):
            clean = normalize_space(str(alias))
            if clean:
                aliases.append(clean)
    aliases = dedupe_preserve(aliases)

    event_ids = set()
    for item in entity_entries:
        for event_id in item.get("event_ids", []):
            clean = normalize_space(str(event_id))
            if clean:
                event_ids.add(clean)

    marker_keys = {
        normalize_name(canonical),
        *[normalize_name(value) for value in mentions],
        *[normalize_name(value) for value in aliases],
    }

    relevant_events: List[Dict[str, Any]] = []
    for event in analysis.get("events", []):
        event_id = normalize_space(str(event.get("id", "")))
        searchable = " ".join(
            [
                normalize_space(str(event.get("text", ""))),
                " ".join(event.get("participants", [])),
                " ".join(event.get("locations", [])),
                " ".join(event.get("factions", [])),
                " ".join(event.get("items", [])),
            ]
        )
        searchable_key = normalize_name(searchable)
        has_marker = any(key and key in searchable_key for key in marker_keys)
        if event_id in event_ids or has_marker:
            relevant_events.append(event)

    if not relevant_events and analysis.get("events"):
        relevant_events = analysis["events"][:1]

    participants: List[str] = []
    locations: List[str] = []
    factions: List[str] = []
    items: List[str] = []
    event_texts: List[str] = []
    event_excerpts: List[str] = []
    entity_excerpts: List[str] = []

    for event in relevant_events:
        event_text = normalize_space(str(event.get("text", "")))
        if event_text:
            event_texts.append(event_text)
        excerpt = normalize_space(str(event.get("source_excerpt", "")))
        if excerpt:
            event_excerpts.append(excerpt)
        participants.extend(
            canonicalize_name(str(value), alias_lookup)
            for value in event.get("participants", [])
            if normalize_space(str(value))
        )
        locations.extend(
            canonicalize_name(str(value), alias_lookup)
            for value in event.get("locations", [])
            if normalize_space(str(value))
        )
        factions.extend(
            canonicalize_name(str(value), alias_lookup)
            for value in event.get("factions", [])
            if normalize_space(str(value))
        )
        items.extend(
            canonicalize_name(str(value), alias_lookup)
            for value in event.get("items", [])
            if normalize_space(str(value))
        )

    for item in entity_entries:
        for excerpt in item.get("evidence_excerpts", []):
            clean = normalize_space(str(excerpt))
            if clean:
                entity_excerpts.append(clean)

    excerpts = dedupe_preserve(entity_excerpts + event_excerpts)

    self_markers = {
        normalize_name(canonical),
        *[normalize_name(value) for value in mentions],
        *[normalize_name(value) for value in aliases],
    }
    related_characters = [
        value
        for value in dedupe_preserve(participants)
        if normalize_name(value) not in self_markers
    ]

    confidences = [to_float(item.get("confidence"), 0.7) for item in entity_entries]
    confidence = max(confidences) if confidences else 0.7

    return {
        "mentions": dedupe_preserve(mentions + aliases)[:8],
        "aliases": aliases,
        "event_texts": dedupe_preserve(event_texts)[:6],
        "excerpts": excerpts[:6],
        "entity_excerpts": dedupe_preserve(entity_excerpts)[:6],
        "event_excerpts": dedupe_preserve(event_excerpts)[:6],
        "primary_excerpt": first_or(dedupe_preserve(entity_excerpts), first_or(dedupe_preserve(event_excerpts), "")),
        "related_characters": dedupe_preserve(related_characters)[:6],
        "locations": dedupe_preserve(locations)[:6],
        "factions": dedupe_preserve(factions)[:6],
        "items": dedupe_preserve(items)[:6],
        "confidence": confidence,
        "known_titles": known_titles,
    }


def infer_character_role(canonical: str, context: Dict[str, Any]) -> str:
    lowered = canonical.lower()
    if canonical in CAMPAIGN_CONFIG.get("party_members", []):
        return "party member"
    if "mayor" in lowered:
        return "mayor"
    if "king" in lowered:
        return "monarch"
    if "lord" in lowered:
        return "noble"
    if "captain" in lowered:
        return "captain"
    alias_blob = " ".join(
        normalize_space(str(v)).lower() for v in context.get("aliases", []) if normalize_space(str(v))
    )
    excerpt = normalize_space(context.get("primary_excerpt", "")).lower()
    combined = " ".join(
        [normalize_space(str(v)).lower() for v in context.get("entity_excerpts", []) if normalize_space(str(v))]
        + [normalize_space(str(v)).lower() for v in context.get("event_texts", []) if normalize_space(str(v))]
    )
    if "captain" in excerpt or "captain" in combined or "captain" in alias_blob:
        return "captain"
    if "store owner" in excerpt:
        return "merchant"
    return "contact"


def faction_overview(canonical: str, summary: str, context: Dict[str, Any]) -> str:
    lowered = canonical.lower()
    if "lords alliance" in lowered:
        vibe = (
            f"[[{canonical}]] reads as an organized political-military bloc using formal authority, "
            "obligation, and institutional pressure."
        )
    elif "zhentarim" in lowered:
        vibe = (
            f"[[{canonical}]] presents as a covert coercive network whose presence is often inferred "
            "through symbols, intermediaries, and deniable violence."
        )
    elif "pirate" in lowered:
        vibe = (
            f"[[{canonical}]] projects a predatory maritime threat profile, favoring intimidation, "
            "interception, and rapid escalation."
        )
    else:
        reliability = confidence_label(to_float(context.get("confidence"), 0.7))
        vibe = f"[[{canonical}]] appears as an active power bloc in the current arc ({reliability})."

    summary_clean = normalize_space(summary).rstrip(".!?")
    if ": " in summary_clean:
        summary_clean = summary_clean.split(": ", 1)[1].strip()
    influence = f"In this session, it shapes events around this thread: {summary_clean}."
    return f"{vibe} {influence}"


def character_overview(canonical: str, role: str, context: Dict[str, Any]) -> str:
    role_key = normalize_space(role).lower()
    if role_key == "captain":
        return (
            f"[[{canonical}]] is a career mariner whose leadership style is measured, "
            "procedural, and quietly protective of crew and vessel. In the broader story, "
            "this character frames maritime risk, enforces operational reality, and keeps "
            "expeditions moving toward mission outcomes."
        )
    if role_key == "party member":
        return (
            f"[[{canonical}]] is a core member of the adventuring party whose choices "
            "shape both tactical outcomes and group dynamics. In the broader story, this "
            "character drives momentum through decisions made under pressure and at key "
            "moral or strategic forks."
        )
    if role_key == "merchant":
        return (
            f"[[{canonical}]] is a civilian commerce contact whose value comes from access, "
            "information, and practical resupply. In the broader story, this character "
            "supports the party's readiness and local anchoring between larger mission beats."
        )
    if role_key in {"mayor", "monarch", "noble"}:
        return (
            f"[[{canonical}]] is a civic authority figure whose position carries political "
            "weight beyond any single encounter. In the broader story, this character "
            "influences how institutional power, obligations, and consequences reach the party."
        )

    domains: List[str] = []
    for loc in context.get("locations", []):
        clean = normalize_space(str(loc))
        if clean:
            domains.append(clean)
    for fac in context.get("factions", []):
        clean = normalize_space(str(fac))
        if clean:
            domains.append(clean)
    domains = dedupe_preserve(domains)

    if domains:
        if len(domains) == 1:
            scope = domains[0]
        else:
            scope = ", ".join(domains[:2])
        return (
            f"[[{canonical}]] is a recurring figure whose presence helps define the tone and "
            f"stakes around {scope}. In the broader story, this character influences how the "
            "party navigates relationships, risk, and mission continuity."
        )

    return (
        f"[[{canonical}]] is a recurring character in the campaign with growing relevance to "
        "the party's direction. In the broader story, this character helps connect immediate "
        "scene-level events to longer-term narrative consequences."
    )


def classify_location_kind(canonical: str, context: Dict[str, Any]) -> str:
    key = normalize_name(canonical)
    lowered = canonical.lower()
    blob = " ".join(
        [canonical]
        + [normalize_space(str(v)) for v in context.get("aliases", [])]
        + [normalize_space(str(v)) for v in context.get("event_texts", [])]
        + [normalize_space(str(v)) for v in context.get("excerpts", [])]
    ).lower()
    if key == "the voyage":
        return "ship"
    if any(token in lowered for token in ["galley", "ready room", "captain", "cabin", "hold", "deck"]):
        return "ship_space"
    if any(token in lowered for token in ["dock", "harbor", "port"]):
        return "dock"
    if "river" in lowered:
        return "river"
    if any(token in lowered for token in ["store", "shop", "market", "enclave"]):
        return "commercial"
    if any(
        token in key
        for token in ["neverwinter", "luskan", "gundarlun", "gundbarg", "fisktbark"]
    ):
        return "settlement"
    return "site"


def link_if_known(name: str, context: Dict[str, Any]) -> str:
    clean = normalize_space(name)
    if not clean:
        return clean
    known_titles = context.get("known_titles", set())
    if isinstance(known_titles, set) and clean in known_titles:
        return f"[[{clean}]]"
    return clean


def infer_location_descriptor(canonical: str, context: Dict[str, Any]) -> str:
    can_low = canonical.lower()
    texts = [
        normalize_space(strip_wikilinks(str(v))).lower()
        for v in (
            context.get("entity_excerpts", [])
            + context.get("event_excerpts", [])
            + context.get("event_texts", [])
            + context.get("excerpts", [])
        )
        if normalize_space(str(v))
    ]

    for text in texts:
        if f"city of {can_low}" in text:
            return "city"
        if f"town of {can_low}" in text or f"town name {can_low}" in text:
            return "town"
        if f"island of {can_low}" in text:
            return "island"
        if f"capital in {can_low}" in text:
            return "capital city"
        if f"docks of {can_low}" in text and ("dock" in can_low or "harbor" in can_low):
            return "dock district"
        if f"river {can_low}" in text or f"{can_low} river" in text:
            return "river"
        if "store" in text and can_low in text:
            return "store"
        if "enclave" in text and can_low in text:
            return "enclave"

    kind = classify_location_kind(canonical, context)
    if kind == "ship":
        return "ship"
    if kind == "ship_space":
        return "shipboard location"
    if kind == "dock":
        return "dock district"
    if kind == "river":
        return "river"
    if kind == "commercial":
        return "trade location"
    if kind == "settlement":
        return "settlement"
    return "location"


def infer_location_relation(canonical: str, context: Dict[str, Any]) -> Tuple[str, str]:
    canonical_key = normalize_name(canonical)
    others = [
        normalize_space(str(loc))
        for loc in context.get("locations", [])
        if normalize_space(str(loc)) and normalize_name(str(loc)) != canonical_key
    ]
    if not others:
        return "", ""

    texts = [
        normalize_space(strip_wikilinks(str(v)))
        for v in (
            context.get("event_texts", [])
            + context.get("entity_excerpts", [])
            + context.get("event_excerpts", [])
            + context.get("excerpts", [])
        )
        if normalize_space(str(v))
    ]

    for text in texts:
        if canonical_key not in normalize_name(text):
            continue
        for loc in others:
            if re.search(rf"\bon\s+{re.escape(loc)}\b", text, flags=re.IGNORECASE):
                return "on", loc
        for loc in others:
            if re.search(rf"\bin\s+{re.escape(loc)}\b", text, flags=re.IGNORECASE):
                return "in", loc
        for loc in others:
            if re.search(rf"\bnear\s+{re.escape(loc)}\b", text, flags=re.IGNORECASE):
                return "near", loc
    return "", ""


def location_fact_sentence(canonical: str, context: Dict[str, Any]) -> str:
    descriptor = infer_location_descriptor(canonical, context)
    relation_prep, relation_loc = infer_location_relation(canonical, context)
    if descriptor == "island" and relation_prep == "near":
        relation_prep, relation_loc = "", ""
    relation = ""
    if relation_prep and relation_loc:
        relation = f" {relation_prep} {link_if_known(relation_loc, context)}"

    excerpt = normalize_space(
        first_or(context.get("entity_excerpts", []), first_or(context.get("event_excerpts", []), ""))
    )
    excerpt_low = strip_wikilinks(excerpt).lower()
    can_low = canonical.lower()

    if "pirate capital" in excerpt_low and normalize_name(canonical) in normalize_name(excerpt):
        return f"[[{canonical}]] is noted as a pirate capital."
    if re.search(rf"^on the docks of {re.escape(can_low)}\\b", excerpt_low):
        return f"[[{canonical}]] is a city with active harbor docks."

    if descriptor == "city":
        return f"[[{canonical}]] is a city{relation}."
    if descriptor == "town":
        if "no deep water port" in excerpt_low:
            return f"[[{canonical}]] is a town{relation} with no deep-water port."
        return f"[[{canonical}]] is a town{relation}."
    if descriptor == "island":
        return f"[[{canonical}]] is an island{relation}."
    if descriptor == "dock district":
        return f"[[{canonical}]] is a dock district{relation}."
    if descriptor == "river":
        return f"[[{canonical}]] is a river{relation}."
    if descriptor == "store":
        return f"[[{canonical}]] is a store{relation}."
    if descriptor == "enclave":
        return f"[[{canonical}]] is an enclave{relation}."
    if descriptor == "ship":
        return f"[[{canonical}]] is the vessel currently carrying the party and crew."

    if relation:
        return f"[[{canonical}]] is a location{relation}."

    if excerpt:
        clean = normalize_space(excerpt).rstrip(".!?")
        if len(clean.split()) >= 4:
            if clean[0].islower():
                clean = clean[0].upper() + clean[1:]
            return clean + "."

    return f"[[{canonical}]] is a known location in the current arc, with limited confirmed detail so far."


def location_access_context(canonical: str, context: Dict[str, Any]) -> str:
    kind = classify_location_kind(canonical, context)
    if kind == "ship":
        return "Reached by boarding from harbor infrastructure under crew-controlled access."
    if kind == "ship_space":
        return "Reached only after boarding the vessel and moving through crew-controlled interior routes."
    if kind == "dock":
        return "Reached via city-side approaches, gangways, and active maritime traffic lanes."
    if kind == "river":
        return "Reached from nearby banks, bridges, and adjacent waterfront approaches."
    if kind == "commercial":
        return "Reached through local district foot traffic and standard market access points."
    return f"Reached through nearby routes tied to [[{canonical}]] and surrounding terrain."


def location_feature_line(canonical: str, context: Dict[str, Any]) -> str:
    excerpt = normalize_space(first_or(context.get("entity_excerpts", []), first_or(context.get("event_excerpts", []), "")))
    if excerpt:
        trimmed = excerpt.rstrip(".!?")
        if len(trimmed.split()) >= 6 and not trimmed.endswith((" the", " a", " an", " and", " or", " of", " to", " in")):
            return trimmed[0].upper() + trimmed[1:] + "."

    kind = classify_location_kind(canonical, context)
    if kind == "ship":
        return "A seaworthy deck plan with command, crew, and support spaces designed for sustained coastal and open-water travel."
    if kind == "ship_space":
        return "Constrained interior space where close-quarters interactions expose tension, trust, and command style."
    if kind == "dock":
        return "Busy waterfront infrastructure with cargo flow, boarding points, and constant vessel turnover."
    if kind == "river":
        return "A moving waterway shaping travel, visibility, and tactical movement."
    if kind == "commercial":
        return "Trade-facing interiors and storefront access optimized for supplies, negotiation, and information exchange."
    if kind == "settlement":
        return "Layered civic terrain mixing public movement, local authority, and logistical staging."
    return "Persistent environmental details remain partially documented and should be expanded as new evidence appears."


def location_strategic_relevance(canonical: str, context: Dict[str, Any], summary: str) -> str:
    kind = classify_location_kind(canonical, context)
    if kind in {"ship", "ship_space"}:
        return (
            f"In the broader campaign, [[{canonical}]] influences readiness, group cohesion, and mission execution during maritime transit."
        )
    if kind == "dock":
        return (
            f"In the broader campaign, [[{canonical}]] acts as a transfer and leverage point between urban politics and seaborne operations."
        )
    if kind == "river":
        return (
            f"In the broader campaign, [[{canonical}]] shapes pursuit routes, surveillance lines, and movement constraints."
        )
    if kind == "commercial":
        return (
            f"In the broader campaign, [[{canonical}]] supports equipment flow, rumor-gathering, and practical preparation between major beats."
        )
    if kind == "settlement":
        return (
            f"In the broader campaign, [[{canonical}]] anchors alliances, obligations, and route planning across connected story arcs."
        )
    summary_clean = normalize_space(summary).rstrip(".!?")
    return f"In the broader campaign, [[{canonical}]] remains relevant as recurring story ground connected to {summary_clean}."


def location_overview(canonical: str, summary: str, context: Dict[str, Any]) -> str:
    kind = classify_location_kind(canonical, context)
    recurring = bool(context.get("is_recurring_location"))
    fact = location_fact_sentence(canonical, context)
    if not recurring:
        if fact:
            return fact
        if kind == "ship":
            return (
                f"[[{canonical}]] is the vessel currently carrying the party, crew, and mission cargo through active maritime operations. "
                "It functions as the immediate setting for travel readiness, onboard routines, and command handoffs in this session."
            )
        if kind == "ship_space":
            return (
                f"[[{canonical}]] is a functional interior aboard the vessel used for shipboard routines and close-quarters interaction. "
                "In this session, it primarily serves as a scene location where practical tasks and social pressure overlap."
            )
        if kind == "dock":
            return (
                f"[[{canonical}]] is the active harbor edge where embarkation, logistics, and public movement intersect. "
                "In this session, it serves as a concrete transition point between city activity and seaborne action."
            )
        if kind == "river":
            return (
                f"[[{canonical}]] is a local waterway shaping nearby movement and access routes. "
                "In this session, it functions as environmental context for travel and positioning."
            )
        if kind == "commercial":
            return (
                f"[[{canonical}]] is a practical trade-facing site used for supplies, equipment, and local contact points. "
                "In this session, it supports preparation and operational readiness."
            )
        return (
            f"[[{canonical}]] is a specific place referenced in active scene flow. "
            "In this session, it provides immediate geographic context for party actions."
        )

    if kind == "ship":
        return (
            f"[[{canonical}]] is the party's maritime base of operations, carrying crew, command structure, and mission logistics. "
            "In the broader story, it functions as both transport and social pressure-cooker where trust and authority are tested."
        )
    if kind == "ship_space":
        return (
            f"[[{canonical}]] is an operational interior aboard the vessel where routine duties and close-quarters conversations shape group dynamics. "
            "In the broader story, scenes here surface interpersonal pressure points that affect decision quality at sea."
        )
    if kind == "dock":
        return (
            f"[[{canonical}]] is a maritime threshold where land-based plans convert into shipboard action. "
            "In the broader story, it marks transitions between civic intrigue, provisioning, departures, and returns."
        )
    if kind == "river":
        return (
            f"[[{canonical}]] is a persistent natural transit artery with practical and tactical influence over movement. "
            "In the broader story, it shapes route security, approach timing, and visibility during operations."
        )
    if kind == "commercial":
        return (
            f"[[{canonical}]] is a civilian trade-facing site where the party can secure supplies, contacts, and local context. "
            "In the broader story, it supports preparation and connective tissue between higher-risk expedition beats."
        )
    if kind == "settlement":
        if fact:
            return f"{fact} {location_strategic_relevance(canonical, context, summary)}"
        return (
            f"[[{canonical}]] is a recurring settlement with ongoing relevance to regional politics, movement, and mission planning. "
            "In the broader story, choices tied to this place can ripple into later arcs."
        )
    broad = (
        f"[[{canonical}]] is a recurring location with narrative weight beyond a single encounter. "
        "In the broader story, it helps connect immediate scene outcomes to longer-term campaign stakes."
    )
    if fact and normalize_name(strip_wikilinks(fact)) not in normalize_name(strip_wikilinks(broad)):
        return f"{broad} {fact}"
    return broad


def item_overview(canonical: str, summary: str, context: Dict[str, Any]) -> str:
    summary_clean = normalize_space(summary).rstrip(".!?")
    if ": " in summary_clean:
        summary_clean = summary_clean.split(": ", 1)[1].strip()
    return (
        f"[[{canonical}]] is a notable story asset in this arc. "
        f"In this session, it matters through {summary_clean}."
    )


def creature_overview(canonical: str, summary: str, context: Dict[str, Any]) -> str:
    summary_clean = normalize_space(summary).rstrip(".!?")
    if ": " in summary_clean:
        summary_clean = summary_clean.split(": ", 1)[1].strip()
    return (
        f"[[{canonical}]] appears as an active threat or wild force in the current story. "
        f"Its immediate impact this session is captured by {summary_clean}."
    )


def populate_template_placeholders(
    text: str,
    session: SessionRef,
    entity_type: str,
    canonical: str,
    context: Dict[str, Any],
) -> str:
    summary = first_or(context.get("event_texts", []), f"{canonical} is referenced in this session.")
    secondary = first_or(
        context.get("event_texts", [])[1:],
        "No additional state changes were clearly documented in this session.",
    )
    excerpt = first_or(context.get("entity_excerpts", []), first_or(context.get("excerpts", []), summary))

    known_titles = context.get("known_titles", set())
    character_links = to_wikilinks(context.get("related_characters", []), known_titles=known_titles, limit=4)
    location_links = to_wikilinks(context.get("locations", []), known_titles=known_titles, limit=4)
    faction_links = to_wikilinks(context.get("factions", []), known_titles=known_titles, limit=4)
    item_links = to_wikilinks(context.get("items", []), known_titles=known_titles, limit=4)

    first_character = first_or(character_links, "none recorded")
    second_character = first_or(character_links[1:], "none recorded")
    first_location = first_linked_or(location_links, first_or(location_links, "[[Unknown Location]]"))
    first_faction = first_or(faction_links, "none recorded")
    first_item = first_or(item_links, "none recorded")

    role = infer_character_role(canonical, context)
    reliability = confidence_label(to_float(context.get("confidence"), 0.7))
    open_unknown = "How this thread will evolve across future sessions remains unclear."

    generic_map = {
        "{{YYYY-MM-DD}}": session.date,
        "{{XX}}": f"{session.session_number:03d}",
        "{{What changed}}": summary,
        "{{Actions/revelations/consequences}}": secondary,
        "{{Unknowns}}": open_unknown,
        "{{Additional details}}": excerpt,
        "{{Faction activity and impact}}": summary,
        "{{What happened here}}": summary,
        "{{State changes}}": secondary,
        "{{Acquired/used/lost details}}": summary,
        "[[Name]]": first_character,
        "[[Location]]": first_location,
        "[[Faction Name]]": first_faction,
        "[[Item Name]]": first_item,
        "[[Faction/Character]]": first_or([first_faction, first_character], "none recorded"),
        "[[Character/Faction]]": first_or([first_character, first_faction], "none recorded"),
        "[[Faction]]": first_faction,
        "[[Item]]": first_item,
        "[[Quest]]": summary_link(session),
        "[[A]]": first_character,
        "[[B]]": second_character,
        "[[C]]": first_or([f"[[{canonical}]]"], "none recorded"),
    }

    character_map = {
        "{{Two-sentence campaign-level introduction covering the character's enduring role in the story and signature traits/themes; avoid session-specific recap language.}}": character_overview(
            canonical, role, context
        ),
        "{{Brief introduction of the character, their role in the overall story, and any key traits or themes associated with them.}}": character_overview(
            canonical, role, context
        ),
        "{{Brief summary of the character, their role in the story, and any key traits or themes associated with them.}}": character_overview(
            canonical, role, context
        ),
        "{{Brief summary of the character, its role in the story, and any key traits or themes associated with it.}}": character_overview(
            canonical, role, context
        ),
        "{{confirmed|partially confirmed|unconfirmed}}": reliability,
        "{{Appearance, voice, notable traits}}": character_description(canonical, context),
        "{{ally/enemy/family/contact}}": "contact",
        "{{context}}": summary,
        "{{role/status}}": "status unclear",
        "{{...}}": "No distinct mechanical details were confirmed this session.",
        "{{Known goals}}": f"Acts within the thread where {summary}",
        "{{Suspected goals (mark as uncertain)}}": "Possible hidden motives; unconfirmed.",
        "{{Why this character matters now}}": summary,
        "{{Unresolved facts}}": open_unknown,
        "{{ally|enemy|neutral|unknown}}": "neutral",
    }

    location_map = {
        "{{If recurring across sessions, give a two-sentence campaign-level description of enduring role/themes; otherwise write single-sentence description of what is actually known (type/region/relationship), not generic filler.}}": location_overview(
            canonical, summary, context
        ),
        "{{If recurring across sessions, give a two-sentence campaign-level description of enduring role/themes; otherwise write a concrete fact-first description of what is actually known (type/region/relationship), not generic filler.}}": location_overview(
            canonical, summary, context
        ),
        "{{If recurring across sessions, give a two-sentence campaign-level description of enduring role/themes; otherwise give a concise session-grounded description.}}": location_overview(
            canonical, summary, context
        ),
        "{{Two-sentence campaign-level introduction of the location's enduring role in the story and key traits/themes; avoid session recap wording.}}": location_overview(
            canonical, summary, context
        ),
        "{{Brief introduction of the location, its role in the overall story, and any key traits or themes associated with it.}}": location_overview(
            canonical, summary, context
        ),
        "{{Brief summary of the location, its role in the story, and any key traits or themes associated with it.}}": location_overview(
            canonical, summary, context
        ),
        "{{What and where}}": summary,
        "{{Travel/access context}}": location_access_context(canonical, context),
        "{{Physical/magical features}}": location_feature_line(canonical, context),
        "{{role}}": "active in current events",
        "{{Threats}}": secondary,
        "{{Why this location matters}}": location_strategic_relevance(canonical, context, summary),
        "{{Region Name}}": first_or(context.get("locations", []), "Unknown Region"),
        "{{accessible|contested|destroyed|unknown}}": "accessible",
    }

    faction_map = {
        "{{Brief summary of the faction, its role in the story, and any key traits or themes associated with it.}}": faction_overview(
            canonical, summary, context
        ),
        "{{What this faction is}}": faction_overview(canonical, summary, context),
        "{{Beliefs and objectives}}": "Operational goals are inferred from session actions and remain partially confirmed.",
        "{{leader/envoy/operative}}": "operative",
        "{{active/missing/deceased}}": "active",
        "{{How they operate}}": secondary,
        "{{significance}}": "Referenced in active session threads.",
        "{{local|regional|coastal|global}}": "regional",
        "{{low|medium|high}}": "medium",
        "{{active|fractured|defunct|unknown}}": "active",
    }

    item_map = {
        "{{Brief summary of the item, its role in the story, and any key traits or themes associated with it.}}": item_overview(
            canonical, summary, context
        ),
        "{{Appearance, size, weight, notable features}}": excerpt,
        "{{Physical description and significance}}": excerpt,
        "{{effects, limits}}": "Precise mechanics were not fully detailed in this session.",
        "{{story utility}}": summary,
        "{{source}}": first_location,
        "{{confirmed|unconfirmed}}": reliability,
        "{{Who wants it / what can go wrong}}": secondary,
        "{{Unknown powers/origin}}": open_unknown,
        "{{in_party_possession|lost|stored|destroyed|unknown}}": "unknown",
    }

    creature_map = {
        "{{Brief summary of the creature, its role in the story, and any key traits or themes associated with it.}}": creature_overview(
            canonical, summary, context
        ),
        "{{Appearance and nature}}": excerpt,
        "{{Observed abilities}}": summary,
        "{{Observed resistances and immunities}}": "No reliable resistances or immunities were documented this session.",
        "{{Observed vulnerabilities}}": "No reliable vulnerabilities were documented this session.",
        "{{Weaknesses/resistances if known}}": "No reliable weakness data recorded yet.",
        "{{Patterns and triggers}}": secondary,
        "{{low|medium|high|extreme}}": "medium",
        "{{avoid|negotiate|contain|eliminate}}": "contain",
        "{{beast|aberration|fiend|deity_avatar|other}}": "other",
        "{{active|neutralized|deceased|unknown}}": "unknown",
    }

    replacements = dict(generic_map)
    if entity_type == "character":
        replacements.update(character_map)
    elif entity_type == "location":
        replacements.update(location_map)
    elif entity_type == "faction":
        replacements.update(faction_map)
    elif entity_type == "item":
        replacements.update(item_map)
    elif entity_type == "creature":
        replacements.update(creature_map)

    for key in sorted(replacements.keys(), key=len, reverse=True):
        text = text.replace(key, replacements[key])

    if entity_type == "character":
        text = re.sub(r"(?m)^- \*\*Role:\*\* .*$", f"- **Role:** {role}", text)
        text = re.sub(r"(?m)^- \*\*Current Location:\*\* .*$", f"- **Current Location:** {first_location}", text)
        text = re.sub(r"(?m)^- \*\*Reliability:\*\* .*$", f"- **Reliability:** {reliability}", text)
        text = re.sub(
            r"(?m)^- \*\*Items & Assets:\*\* .*$",
            "- **Items & Assets:** No personal assets were directly attributed this session.",
            text,
        )
    elif entity_type == "item":
        text = re.sub(r"(?m)^- \*\*Holder:\*\* .*$", f"- **Holder:** {first_or(character_links, 'none recorded')}", text)
        text = re.sub(r"(?m)^- \*\*Location:\*\* .*$", f"- **Location:** {first_location}", text)
        text = re.sub(r"(?m)^- \*\*Confidence:\*\* .*$", f"- **Confidence:** {reliability}", text)
    elif entity_type == "faction":
        text = re.sub(r"(?m)^- \*\*Scope:\*\* .*$", "- **Scope:** regional", text)
        text = re.sub(r"(?m)^- \*\*Risk to party:\*\* .*$", "- **Risk to party:** medium", text)

    if entity_type == "location":
        location_list = first_or(location_links, "none recorded")
        character_list = first_or(character_links, "none recorded")
        faction_list = first_or(faction_links, "none recorded")
        item_list = first_or(item_links, "none recorded")
        quest_list = summary_link(session)
        related_entities_section = (
            "### 📍Locations\n\n"
            f"- {location_list}\n\n"
            "### 👤 Characters\n\n"
            f"- {character_list}\n\n"
            "### 🏰 Factions\n\n"
            f"- {faction_list}\n\n"
            "### 📦 Items\n\n"
            f"- {item_list}\n\n"
            "### ⚔️ Quests\n\n"
            f"- {quest_list}"
        )
        text = replace_h2_section(text, "## 🔗 Related Entities", related_entities_section)

    text = re.sub(r"\{\{[^{}]+\}\}", "unspecified", text)
    return text


def managed_world_block(
    session: SessionRef,
    canonical: str,
    context: Dict[str, Any],
    include_timeline: bool = True,
    include_updates: bool = True,
) -> str:
    mentions = [m for m in context.get("mentions", []) if not looks_like_player_name(m)][:6]

    lines: List[str] = []
    if include_updates:
        lines.extend(["## 🛠️ Managed Updates", ""])
        lines.append(f"- Last Updated Session: {summary_link(session)}")
        lines.append(f"- Canonical Entity: [[{canonical}]]")
        lines.append("- Observed Mentions:")
        if mentions:
            for mention in mentions:
                lines.append(f"  - {mention}")
        else:
            lines.append(f"  - {canonical}")

    if include_timeline:
        if lines:
            lines.append("")
        lines.append("## 🕰️ Session Timeline")
        lines.append("")
        lines.append(f"### {summary_link(session)}")
        lines.append("")

        event_texts = context.get("event_texts", [])
        if event_texts:
            for event_text in event_texts[:4]:
                lines.append(f"- {event_text}")
        else:
            lines.append("- Mentioned in this session.")

    return "\n".join(lines).strip()


def normalize_notes_content(notes_content: str, canonical: str, context: Dict[str, Any]) -> str:
    cleaned = notes_content.strip()
    if not cleaned or cleaned == "- Add manual notes here. Keep this section outside the managed block.":
        excerpt = first_or(context.get("entity_excerpts", []), first_or(context.get("excerpts", []), ""))
        if excerpt:
            return f"- {excerpt}"
        return "- Add manual notes here. Keep this section outside the managed block."

    canonical_markers = {
        normalize_name(canonical),
        *[normalize_name(value) for value in context.get("mentions", [])],
        *[normalize_name(value) for value in context.get("aliases", [])],
    }

    def best_entity_note() -> str:
        for value in context.get("entity_excerpts", []):
            candidate = normalize_space(str(value))
            if not candidate:
                continue
            if looks_like_roster_line(candidate):
                continue
            key = normalize_name(strip_wikilinks(candidate))
            if any(marker and marker in key for marker in canonical_markers):
                return candidate
        for value in context.get("excerpts", []):
            candidate = normalize_space(str(value))
            if not candidate:
                continue
            if looks_like_roster_line(candidate):
                continue
            key = normalize_name(strip_wikilinks(candidate))
            if any(marker and marker in key for marker in canonical_markers):
                return candidate
        return ""

    plain_cleaned = strip_wikilinks(cleaned)
    plain_key = normalize_name(plain_cleaned)
    has_entity_marker = any(marker and marker in plain_key for marker in canonical_markers)

    lines = [line for line in cleaned.splitlines() if line.strip()]
    if len(lines) == 1 and lines[0].startswith("- "):
        bullet = normalize_space(lines[0][2:])
        plain_bullet = strip_wikilinks(bullet)
        bullet_key = normalize_name(plain_bullet)
        event_excerpt = first_or(context.get("event_excerpts", []), "")
        entity_excerpt = first_or(context.get("entity_excerpts", []), "")
        if event_excerpt and bullet_key == normalize_name(event_excerpt) and entity_excerpt and not has_entity_marker:
            return f"- {entity_excerpt}"

        # Replace clearly auto-generated, entity-mismatched single-line notes.
        if not has_entity_marker:
            replacement = best_entity_note()
            if replacement:
                return f"- {replacement}"

        # Replace player-roster spillover bullets with entity evidence.
        if looks_like_roster_line(plain_bullet):
            replacement = best_entity_note()
            if replacement:
                return f"- {replacement}"

    return cleaned


def render_managed_sections(
    session: SessionRef,
    entity_type: str,
    canonical: str,
    context: Dict[str, Any],
) -> str:
    template_path = WORLD_TEMPLATE[entity_type]
    base = seed_template(template_path, base_world_replacements(entity_type, canonical, session))
    populated = populate_template_placeholders(base, session, entity_type, canonical, context)
    _, body = split_frontmatter(populated)
    core = extract_managed_core(body)
    if entity_type == "item":
        core = remove_h2_section(core, "## 🛠️ Managed Updates")

    core_has_timeline = "## 🕰️ Session Timeline" in core
    include_updates = entity_type != "item"
    managed_meta = managed_world_block(
        session,
        canonical,
        context,
        include_timeline=not core_has_timeline,
        include_updates=include_updates,
    )
    if core and managed_meta:
        return f"{core.rstrip()}\n\n{managed_meta.rstrip()}".strip()
    if core:
        return core.strip()
    return managed_meta.strip()


def compose_world_document(frontmatter: str, managed_sections: str, notes_content: str) -> str:
    notes = build_notes_section(notes_content).rstrip()
    body = (
        f"{MANAGED_START}\n\n{managed_sections.rstrip()}\n\n{MANAGED_END}\n\n{notes}\n"
    )
    if frontmatter:
        return frontmatter + body
    return body


def update_world(
    session: SessionRef,
    analysis: Dict[str, Any],
    resolver: Dict[str, Any],
    category: str,
    structure_only: bool = False,
    prepare_only: bool = False,
) -> List[str]:
    touched: List[str] = []
    by_canonical: Dict[str, Dict[str, str]] = {}

    for entity in analysis.get("entities", []):
        canonical = entity.get("canonical_title")
        entity_type = entity.get("entity_type")
        if not canonical or entity_type not in WORLD_TYPE_DIR:
            continue
        if category != "all" and entity_type != category:
            continue
        by_canonical[canonical] = entity

    for canonical, entity in sorted(by_canonical.items(), key=lambda value: value[0]):
        entity_type = entity["entity_type"]
        migrate_forced_entity_path(canonical, entity_type)
        folder = WORLD_TYPE_DIR[entity_type]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{canonical}.md"
        context = build_entity_context(canonical, entity_type, analysis)

        if prepare_only:
            if path.exists():
                continue
            base = seed_template(WORLD_TEMPLATE[entity_type], base_world_replacements(entity_type, canonical, session))
            write_text(path, base if base.endswith("\n") else base + "\n")
            touched.append(str(path.relative_to(REPO_ROOT)))
            continue

        if path.exists():
            existing = read_text(path)
            frontmatter, body = split_frontmatter(existing)
            prior_sessions = count_prior_timeline_sessions(existing, session)
            summary_hits = summary_session_hits(canonical)
            context["prior_timeline_sessions"] = prior_sessions
            context["summary_session_hits"] = summary_hits
            context["is_recurring_location"] = entity_type == "location" and (
                prior_sessions >= 1 or summary_hits >= 2
            )
            if structure_only:
                core = extract_managed_core(body)
                if entity_type == "item":
                    core = remove_h2_section(core, "## 🛠️ Managed Updates")
                core_has_timeline = "## 🕰️ Session Timeline" in core
                include_updates = entity_type != "item"
                managed_meta = managed_world_block(
                    session,
                    canonical,
                    context,
                    include_timeline=not core_has_timeline,
                    include_updates=include_updates,
                )
                if core and managed_meta:
                    managed_sections = f"{core.rstrip()}\n\n{managed_meta.rstrip()}".strip()
                elif core:
                    managed_sections = core.strip()
                else:
                    managed_sections = managed_meta.strip()
            else:
                managed_sections = render_managed_sections(session, entity_type, canonical, context)
                managed_sections = merge_existing_authored_sections(
                    body,
                    managed_sections,
                    entity_type,
                )
                managed_sections = merge_existing_overview(
                    body,
                    managed_sections,
                    entity_type,
                    session,
                    context,
                )
            notes_content = extract_notes_content(strip_managed_blocks(body))
            if not structure_only:
                notes_content = normalize_notes_content(notes_content, canonical, context)
            normalized_frontmatter = normalize_world_frontmatter(
                frontmatter, canonical, entity_type, context
            )
            rebuilt = compose_world_document(
                normalized_frontmatter, managed_sections, notes_content
            )
            linked = linkify_text(rebuilt, resolver)
            final = normalize_existing_wikilinks(linked, analysis)
            final = escape_wikilink_pipes_in_tables(final)
        else:
            template_path = WORLD_TEMPLATE[entity_type]
            base = seed_template(template_path, base_world_replacements(entity_type, canonical, session))
            frontmatter, body = split_frontmatter(base)
            context["prior_timeline_sessions"] = 0
            summary_hits = summary_session_hits(canonical)
            context["summary_session_hits"] = summary_hits
            context["is_recurring_location"] = entity_type == "location" and summary_hits >= 2
            if structure_only:
                core = extract_managed_core(body)
                if entity_type == "item":
                    core = remove_h2_section(core, "## 🛠️ Managed Updates")
                core_has_timeline = "## 🕰️ Session Timeline" in core
                include_updates = entity_type != "item"
                managed_meta = managed_world_block(
                    session,
                    canonical,
                    context,
                    include_timeline=not core_has_timeline,
                    include_updates=include_updates,
                )
                if core and managed_meta:
                    managed_sections = f"{core.rstrip()}\n\n{managed_meta.rstrip()}".strip()
                elif core:
                    managed_sections = core.strip()
                else:
                    managed_sections = managed_meta.strip()
            else:
                managed_sections = render_managed_sections(session, entity_type, canonical, context)
            notes_content = extract_notes_content(strip_managed_blocks(body))
            if not structure_only:
                notes_content = normalize_notes_content(notes_content, canonical, context)
            normalized_frontmatter = normalize_world_frontmatter(
                frontmatter, canonical, entity_type, context
            )
            rebuilt = compose_world_document(
                normalized_frontmatter, managed_sections, notes_content
            )
            linked = linkify_text(rebuilt, resolver)
            final = normalize_existing_wikilinks(linked, analysis)
            final = escape_wikilink_pipes_in_tables(final)

        write_text(path, final)
        touched.append(str(path.relative_to(REPO_ROOT)))

    return touched


def in_scope_entities(
    analysis: Dict[str, Any], category: str, resolved_only: bool = False
) -> Dict[str, Dict[str, Any]]:
    selected: Dict[str, Dict[str, Any]] = {}
    for entity in analysis.get("entities", []):
        canonical = entity.get("canonical_title")
        entity_type = entity.get("entity_type")
        if not canonical or entity_type not in WORLD_TYPE_DIR:
            continue
        if category != "all" and entity_type != category:
            continue
        if resolved_only and entity.get("resolution_status") != "resolved":
            continue
        selected[canonical] = entity
    return selected


def extract_item_claims(canonical: str, context: Dict[str, Any]) -> Dict[str, Any]:
    sources = dedupe_preserve(
        [
            normalize_space(str(line))
            for line in (
                context.get("entity_excerpts", [])
                + context.get("event_excerpts", [])
                + context.get("event_texts", [])
            )
            if normalize_space(str(line))
        ]
    )
    names = dedupe_preserve(
        [
            normalize_space(str(name))
            for name in context.get("related_characters", [])
            if normalize_space(str(name))
        ]
    )
    locations = dedupe_preserve(
        [
            normalize_space(str(loc))
            for loc in context.get("locations", [])
            if normalize_space(str(loc))
        ]
    )

    holder_claims: List[Dict[str, str]] = []
    origin_claims: List[Dict[str, str]] = []
    transfer_claims: List[Dict[str, str]] = []

    def has_name(text: str, candidates: List[str]) -> bool:
        clean = normalize_name(text)
        for candidate in candidates:
            if normalize_name(candidate) and normalize_name(candidate) in clean:
                return True
        return False

    canonical_marker = normalize_name(canonical)
    canonical_tail = normalize_name(canonical.split()[-1]) if canonical.split() else ""

    def has_item_marker(text: str) -> bool:
        clean = normalize_name(text)
        if canonical_marker and canonical_marker in clean:
            return True
        # Allow explicit shortened references like "the grimoire" for Arcane Grimoire.
        if canonical_tail and canonical_tail in clean:
            return True
        return False

    for source in sources:
        lower = source.lower()
        has_canonical = has_item_marker(source)
        has_character = has_name(source, names)
        has_location = has_name(source, locations)

        if TRANSFER_VERB_RE.search(source) and has_canonical and has_character:
            transfer_claims.append(
                {
                    "claim": source,
                    "evidence": source,
                    "confidence": "confirmed",
                }
            )

        explicit_holder = (
            "held by" in lower
            or "owned by" in lower
            or "carried by" in lower
            or "wielded by" in lower
            or "in possession of" in lower
            or ("artifact" in lower and "hip" in lower and " at " in lower)
        )
        if explicit_holder and has_canonical and has_character:
            holder_claims.append(
                {
                    "claim": source,
                    "evidence": source,
                    "confidence": "confirmed",
                }
            )

        if ORIGIN_HINT_RE.search(source) and has_canonical and (has_location or has_character):
            origin_claims.append(
                {
                    "claim": source,
                    "evidence": source,
                    "confidence": "confirmed",
                }
            )

    def dedupe_claims(claims: List[Dict[str, str]]) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        seen = set()
        for claim in claims:
            key = normalize_space(claim.get("claim", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(claim)
        return out

    holder_claims = dedupe_claims(holder_claims)
    origin_claims = dedupe_claims(origin_claims)
    transfer_claims = dedupe_claims(transfer_claims)

    holder_value = "unknown"
    holder_confidence = "unconfirmed"
    if holder_claims:
        holder_value = "explicit evidence present"
        holder_confidence = "confirmed"

    origin_value = "unknown"
    origin_confidence = "unconfirmed"
    if origin_claims:
        origin_value = "explicit evidence present"
        origin_confidence = "confirmed"

    return {
        "explicit_holder_claims": holder_claims,
        "explicit_origin_claims": origin_claims,
        "explicit_transfer_claims": transfer_claims,
        "holder": {"value": holder_value, "confidence": holder_confidence},
        "origin": {"value": origin_value, "confidence": origin_confidence},
    }


def command_build_brief(args: argparse.Namespace) -> int:
    session = select_session(args.session)
    events_data, world_data = load_stage1_artifacts(session)

    triage = world_triage_state(world_data)
    if triage["open_count"] > 0:
        raise WorldUpdateError(
            "Risk gate: open triage items remain in world.yaml. "
            "Resolve triage in `$dnd-session-analyze` before building narrative brief."
        )

    analysis = build_world_analysis(events_data, world_data)
    scoped = in_scope_entities(analysis, args.category, resolved_only=True)

    entities_out: List[Dict[str, Any]] = []
    for canonical, entity in sorted(scoped.items(), key=lambda value: value[0]):
        entity_type = entity["entity_type"]
        context = build_entity_context(canonical, entity_type, analysis)
        target_file = str((WORLD_TYPE_DIR[entity_type] / f"{canonical}.md").relative_to(REPO_ROOT))
        brief_item: Dict[str, Any] = {
            "canonical_title": canonical,
            "entity_type": entity_type,
            "target_file": target_file,
            "event_ids": entity.get("event_ids", []),
            "event_texts": context.get("event_texts", []),
            "entity_excerpts": context.get("entity_excerpts", []),
            "event_excerpts": context.get("event_excerpts", []),
            "related_entities": {
                "characters": context.get("related_characters", []),
                "locations": context.get("locations", []),
                "factions": context.get("factions", []),
                "items": context.get("items", []),
            },
            "requires_manual_narrative": True,
        }
        if entity_type == "item":
            brief_item["item_claims"] = extract_item_claims(canonical, context)
        entities_out.append(brief_item)

    brief = {
        "schema_version": 1,
        "session": {
            "session_number": session.session_number,
            "date": session.date,
            "selector": session.session_label,
            "source_note": str(session.path.relative_to(REPO_ROOT)),
        },
        "category": args.category,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "entities": entities_out,
    }

    out_path = world_brief_path_for(session)
    dump_data(out_path, brief)

    print(f"Session: {session.date} Session {session.session_number:03d}")
    print(f"Category: {args.category}")
    print(f"Brief entities: {len(entities_out)}")
    print(f"Brief: {out_path.relative_to(REPO_ROOT)}")
    return 0


def markdown_targets() -> Dict[str, List[Path]]:
    by_stem: Dict[str, List[Path]] = {}
    for path in REPO_ROOT.rglob("*.md"):
        by_stem.setdefault(path.stem, []).append(path)
    return by_stem


def lint_files(paths: List[Path]) -> Dict[str, Any]:
    targets = markdown_targets()
    errors: List[str] = []
    warnings: List[str] = []
    checked = 0

    link_pattern = re.compile(r"!?\[\[([^\]]+)\]\]")
    unescaped_piped_wikilink_pattern = re.compile(r"\[\[[^\]]*(?<!\\)\|[^\]]+\]\]")
    heading_pattern = re.compile(r"^(#{1,6})\s+")

    def wikilink_target(raw: str) -> str:
        core = raw.replace("\\|", "|").replace("\\#", "#")
        core = core.split("|", 1)[0]
        core = core.split("#", 1)[0]
        return core.strip()

    for path in paths:
        if not path.exists() or path.suffix.lower() != ".md":
            continue
        checked += 1
        text = read_text(path)
        lines = text.splitlines()

        blank_run = 0
        prev_heading_level = 0
        for idx, line in enumerate(lines, start=1):
            if line.rstrip() != line:
                errors.append(f"{path.relative_to(REPO_ROOT)}:{idx} trailing whitespace")

            if line.strip() == "":
                blank_run += 1
                if blank_run > 2:
                    warnings.append(
                        f"{path.relative_to(REPO_ROOT)}:{idx} more than two consecutive blank lines"
                    )
            else:
                blank_run = 0

            heading_match = heading_pattern.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                if prev_heading_level and level - prev_heading_level > 1:
                    warnings.append(
                        f"{path.relative_to(REPO_ROOT)}:{idx} heading jump h{prev_heading_level}->h{level}"
                    )
                prev_heading_level = level

                if idx > 1 and lines[idx - 2].strip() and not lines[idx - 2].startswith("---"):
                    warnings.append(
                        f"{path.relative_to(REPO_ROOT)}:{idx} missing blank line before heading"
                    )
                if idx < len(lines) and lines[idx].strip() and not lines[idx].startswith("|"):
                    warnings.append(
                        f"{path.relative_to(REPO_ROOT)}:{idx} missing blank line after heading"
                    )

            for match in link_pattern.finditer(line):
                raw = match.group(1)
                target = wikilink_target(raw)
                if not target or "{{" in target:
                    continue

                found = False
                if "/" in target:
                    candidate = REPO_ROOT / target
                    if candidate.suffix != ".md":
                        candidate = candidate.with_suffix(".md")
                    if candidate.exists():
                        found = True
                else:
                    found = target in targets
                if not found:
                    warnings.append(
                        f"{path.relative_to(REPO_ROOT)}:{idx} unresolved wikilink target '{target}'"
                    )

            if line.lstrip().startswith("|") and unescaped_piped_wikilink_pattern.search(line):
                errors.append(
                    f"{path.relative_to(REPO_ROOT)}:{idx} unescaped wikilink pipe in table cell"
                )

    return {"checked_files": checked, "errors": errors, "warnings": warnings}


def headings_in_text(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if re.match(r"^##\s+|^###\s+", line)]


def entity_type_for_path(path: Path) -> Optional[str]:
    parent = str(path.parent.resolve())
    return WORLD_DIR_TO_TYPE.get(parent)


def required_template_headings(entity_type: str) -> List[str]:
    template = read_text(WORLD_TEMPLATE[entity_type])
    _, body = split_frontmatter(template)
    core = extract_managed_core(body)
    headings = headings_in_text(core)
    return [h for h in headings if "{{" not in h and "}}" not in h]


def lint_structure(paths: List[Path]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    checked = 0

    for path in paths:
        if not path.exists() or path.suffix.lower() != ".md":
            continue
        entity_type = entity_type_for_path(path)
        if not entity_type:
            continue
        checked += 1
        text = read_text(path)
        _, body = split_frontmatter(text)
        core = extract_managed_core(body)
        actual = headings_in_text(core)
        required = required_template_headings(entity_type)

        for heading in required:
            if heading not in actual:
                errors.append(f"{path.relative_to(REPO_ROOT)} missing heading `{heading}`")

        last_idx = -1
        for heading in required:
            if heading not in actual:
                continue
            idx = actual.index(heading)
            if idx < last_idx:
                errors.append(
                    f"{path.relative_to(REPO_ROOT)} heading order mismatch near `{heading}`"
                )
                break
            last_idx = idx

        if MANAGED_START not in text or MANAGED_END not in text:
            errors.append(f"{path.relative_to(REPO_ROOT)} missing managed markers")
        if "## 📝 Notes" not in text:
            warnings.append(f"{path.relative_to(REPO_ROOT)} missing `## 📝 Notes` section")

    return {"checked_files": checked, "errors": errors, "warnings": warnings}


def write_lint_report(result: Dict[str, Any], report_path: Path) -> Path:
    lines = [
        "# Markdown Lint Report",
        "",
        f"- Checked Files: {result['checked_files']}",
        f"- Errors: {len(result['errors'])}",
        f"- Warnings: {len(result['warnings'])}",
        "",
        "## Errors",
    ]
    if result["errors"]:
        lines.extend(f"- {item}" for item in result["errors"])
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Warnings")
    if result["warnings"]:
        lines.extend(f"- {item}" for item in result["warnings"])
    else:
        lines.append("- None")

    write_text(report_path, "\n".join(lines).rstrip() + "\n")
    return report_path


def resolve_lint_paths(paths: List[str]) -> List[Path]:
    if not paths:
        files: List[Path] = []
        for root in WORLD_TYPE_DIR.values():
            if root.exists():
                files.extend(sorted(root.rglob("*.md")))
        return files

    files: List[Path] = []
    for raw in paths:
        target = (REPO_ROOT / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        if target.is_dir():
            files.extend(sorted(target.rglob("*.md")))
        elif target.suffix.lower() == ".md":
            files.append(target)
    return files


def command_run(args: argparse.Namespace) -> int:
    if not args.structure_only:
        raise WorldUpdateError(
            "Narrative generation is model-authored in this workflow. "
            "Run model prose updates first, then run this command with `--structure-only`."
        )

    session = select_session(args.session)
    events_data, world_data = load_stage1_artifacts(session)

    triage = world_triage_state(world_data)
    if triage["open_count"] > 0:
        raise WorldUpdateError(
            "Risk gate: open triage items remain in world.yaml. "
            "Resolve triage in `$dnd-session-analyze` before world-update."
        )

    analysis = build_world_analysis(events_data, world_data)
    resolver = ensure_resolver_defaults()
    resolver = augment_resolver_from_analysis(resolver, analysis, session)
    touched = update_world(
        session,
        analysis,
        resolver,
        args.category,
        structure_only=bool(args.structure_only),
        prepare_only=False,
    )

    lint_targets = [REPO_ROOT / item for item in touched]
    lint_result = lint_files(lint_targets)
    structure_result = lint_structure(lint_targets)
    report_path = write_lint_report(
        {
            "checked_files": lint_result["checked_files"],
            "errors": lint_result["errors"] + structure_result["errors"],
            "warnings": lint_result["warnings"] + structure_result["warnings"],
        },
        session_meta_dir(session) / "markdown-lint-report.md",
    )

    print(f"Session: {session.date} Session {session.session_number:03d}")
    print(f"Category: {args.category}")
    print(f"Updated world files: {len(touched)}")
    for item in touched:
        print(f"- {item}")
    print(
        f"Markdown lint checked={lint_result['checked_files']} "
        f"errors={len(lint_result['errors'])} warnings={len(lint_result['warnings'])}"
    )
    print(
        f"Structure lint checked={structure_result['checked_files']} "
        f"errors={len(structure_result['errors'])} warnings={len(structure_result['warnings'])}"
    )
    print(f"Report: {report_path.relative_to(REPO_ROOT)}")
    return 1 if (lint_result["errors"] or structure_result["errors"]) else 0


def command_prepare(args: argparse.Namespace) -> int:
    session = select_session(args.session)
    events_data, world_data = load_stage1_artifacts(session)

    triage = world_triage_state(world_data)
    if triage["open_count"] > 0:
        raise WorldUpdateError(
            "Risk gate: open triage items remain in world.yaml. "
            "Resolve triage in `$dnd-session-analyze` before world-update."
        )

    analysis = build_world_analysis(events_data, world_data)
    resolver = ensure_resolver_defaults()
    resolver = augment_resolver_from_analysis(resolver, analysis, session)
    touched = update_world(
        session,
        analysis,
        resolver,
        args.category,
        structure_only=False,
        prepare_only=True,
    )

    print(f"Session: {session.date} Session {session.session_number:03d}")
    print(f"Category: {args.category}")
    print(f"Prepared world files: {len(touched)}")
    for item in touched:
        print(f"- {item}")
    return 0


def command_lint_markdown(args: argparse.Namespace) -> int:
    targets = resolve_lint_paths(args.paths or [])
    result = lint_files(targets)
    report_path = write_lint_report(result, LINT_REPORT_PATH)
    print(
        f"Markdown lint checked={result['checked_files']} "
        f"errors={len(result['errors'])} warnings={len(result['warnings'])}"
    )
    print(f"Report: {report_path.relative_to(REPO_ROOT)}")
    return 1 if result["errors"] else 0


def command_lint_structure(args: argparse.Namespace) -> int:
    targets = resolve_lint_paths(args.paths or [])
    result = lint_structure(targets)
    print(
        f"Structure lint checked={result['checked_files']} "
        f"errors={len(result['errors'])} warnings={len(result['warnings'])}"
    )
    for item in result["errors"]:
        print(f"ERROR: {item}")
    for item in result["warnings"]:
        print(f"WARN: {item}")
    return 1 if result["errors"] else 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Standalone world update from Stage 1 artifacts")
    sub = p.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Create missing world files from templates only")
    prepare.add_argument("--session", default="latest session")
    prepare.add_argument(
        "--category",
        default="all",
        choices=["all", "character", "location", "faction", "item", "creature"],
        help="Limit scaffolding to one entity category",
    )
    prepare.add_argument("--dry-run", action="store_true")

    build_brief = sub.add_parser(
        "build-brief",
        help="Build per-entity narrative evidence brief for model-authored prose pass",
    )
    build_brief.add_argument("--session", default="latest session")
    build_brief.add_argument(
        "--category",
        default="all",
        choices=["all", "character", "location", "faction", "item", "creature"],
        help="Limit brief output to one entity category",
    )
    build_brief.add_argument("--dry-run", action="store_true")

    run = sub.add_parser("run", help="Update world files for a session")
    run.add_argument("--session", default="latest session")
    run.add_argument(
        "--category",
        default="all",
        choices=["all", "character", "location", "faction", "item", "creature"],
        help="Limit updates to one entity category",
    )
    run.add_argument(
        "--structure-only",
        action="store_true",
        help="Preserve authored prose and update only structural/meta sections",
    )
    run.add_argument("--dry-run", action="store_true")

    lint = sub.add_parser("lint-markdown", help="Lint world markdown files")
    lint.add_argument("paths", nargs="*")
    lint.add_argument("--dry-run", action="store_true")

    lint_structure = sub.add_parser("lint-structure", help="Lint world files against template structure")
    lint_structure.add_argument("paths", nargs="*")
    lint_structure.add_argument("--dry-run", action="store_true")

    return p


def main() -> int:
    global DRY_RUN
    args = parser().parse_args()
    os.chdir(REPO_ROOT)
    DRY_RUN = bool(getattr(args, "dry_run", False))
    migrate_metadata_layout()

    try:
        if args.command == "prepare":
            return command_prepare(args)
        if args.command == "build-brief":
            return command_build_brief(args)
        if args.command == "run":
            return command_run(args)
        if args.command == "lint-markdown":
            return command_lint_markdown(args)
        if args.command == "lint-structure":
            return command_lint_structure(args)
    except WorldUpdateError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
