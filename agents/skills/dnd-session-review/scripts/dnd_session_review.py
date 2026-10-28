#!/usr/bin/env python3
"""D&D vault skill pipeline.

Implements staged processing:
- analyze
- triage
- summarize-quests
- world-update
- run-all
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Shared scripts belong to the installed suite; campaign data belongs to the vault.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dnd-session-review" / "scripts"))
from dnd_vault import configured_player_character, find_vault_root, load_campaign_config

REPO_ROOT = find_vault_root()
CAMPAIGN_CONFIG = load_campaign_config(REPO_ROOT)
SESSIONS_DIR = REPO_ROOT / "Sessions"
NOTES_DIR = SESSIONS_DIR / "Notes"
SUMMARIES_DIR = SESSIONS_DIR / "Summaries"
QUESTS_ROOT_DIR = REPO_ROOT / "Quests"
QUESTS_ACTIVE_DIR = QUESTS_ROOT_DIR / "Active"
QUESTS_COMPLETED_DIR = QUESTS_ROOT_DIR / "Completed"
QUESTS_DIR = QUESTS_ACTIVE_DIR
LEGACY_QUESTS_DIR = SESSIONS_DIR / "Quests"
WORLD_DIR = REPO_ROOT / "World"
TEMPLATES_DIR = REPO_ROOT / "Templates"
META_DIR = REPO_ROOT / ".dnd-meta"
META_SESSIONS_DIR = META_DIR / "sessions"

RESOLVER_PATH = META_DIR / "entity-resolver.yaml"
TRIAGE_DECISIONS_PATH = META_DIR / "triage-decisions.yaml"
QUEST_MAP_PATH = META_DIR / "quest-map.yaml"
QUEST_SIGNALS_PATH = META_DIR / "quest-signals.yaml"
QUEST_DECISIONS_PATH = META_DIR / "quest-decisions.yaml"
LINT_REPORT_PATH = META_DIR / "markdown-lint-report.md"
ANALYZE_SKILL_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dnd-session-analyze" / "scripts"
EVENTS_LINT_SCRIPT = ANALYZE_SKILL_SCRIPTS_DIR / "lint_events_yaml.py"
WORLD_LINT_SCRIPT = ANALYZE_SKILL_SCRIPTS_DIR / "lint_world_yaml.py"

WORLD_TYPE_DIR = {
    "character": WORLD_DIR / "Characters",
    "location": WORLD_DIR / "Locations",
    "faction": WORLD_DIR / "Factions",
    "item": WORLD_DIR / "Items",
    "creature": WORLD_DIR / "Creatures",
}

WORLD_TEMPLATE = {
    "character": TEMPLATES_DIR / "character-template.md",
    "location": TEMPLATES_DIR / "location-template.md",
    "faction": TEMPLATES_DIR / "faction-template.md",
    "item": TEMPLATES_DIR / "item-template.md",
    "creature": TEMPLATES_DIR / "creature-template.md",
}

MANAGED_START = "<!-- dnd-managed:start -->"
MANAGED_END = "<!-- dnd-managed:end -->"

ENTITY_TYPES = ["character", "location", "faction", "item", "creature", "unknown"]
WORLD_OPEN_STATUSES = {"triage_required", "unresolved"}
DRY_RUN = False

DEFAULT_RESOLVER_ENTITIES = CAMPAIGN_CONFIG.get("resolver_seeds", [])

STOP_WORDS = {
    "The",
    "And",
    "Now",
    "Previously",
    "Day",
    "Session",
    "We",
    "Our",
    "They",
    "He",
    "She",
    "It",
    "As",
    "At",
    "In",
    "On",
    "To",
    "Of",
    "For",
    "From",
    "After",
    "Before",
    "Back",
    "Meanwhile",
    "INITIATIVE",
}

DISALLOWED_SINGLE_WORDS = {
    "Would",
    "Welcome",
    "Other",
    "Intercepted",
    "Bordered",
    "Fought",
    "Feels",
    "First",
    "Outside",
    "Downstairs",
    "Inside",
    "Then",
    "Unable",
    "Seems",
    "Still",
    "Meanwhile",
    "Where",
    "When",
    "What",
    "Which",
    "Who",
    "Why",
    "How",
    "You",
    "Its",
    "It",
    "They",
}

QUEST_ACTION_PHRASES = [
    ("go", "Investigate"),
    ("find out", "Investigate"),
    ("look into", "Investigate"),
    ("follow up", "Follow Up"),
    ("track down", "Track"),
    ("return to", "Return To"),
    ("report to", "Report To"),
    ("speak with", "Meet"),
    ("talk to", "Meet"),
    ("investigate", "Investigate"),
    ("determine", "Determine"),
    ("discover", "Discover"),
    ("uncover", "Uncover"),
    ("recover", "Recover"),
    ("retrieve", "Recover"),
    ("rescue", "Rescue"),
    ("solve", "Solve"),
    ("prevent", "Prevent"),
    ("protect", "Protect"),
    ("explore", "Explore"),
    ("locate", "Locate"),
    ("follow", "Follow"),
    ("report", "Report"),
    ("warn", "Warn"),
    ("meet", "Meet"),
    ("track", "Track"),
    ("find", "Find"),
    ("stop", "Stop"),
]

QUEST_STRONG_ACTIONS = {
    "Investigate",
    "Determine",
    "Discover",
    "Uncover",
    "Find",
    "Track",
    "Rescue",
    "Recover",
    "Stop",
    "Solve",
}

QUEST_MISSION_MARKERS = {
    "job",
    "mission",
    "conscripted",
    "ordered",
    "reward",
    "contract",
    "tasked",
    "insists",
    "leave dawn",
    "deadline",
    "two week",
    "weeks or longer",
}

QUEST_LONG_HORIZON_MARKERS = {
    "next session",
    "later",
    "again",
    "eventually",
    "ongoing",
    "continue",
    "follow-up",
    "follow up",
    "still",
}

OPEN_QUESTION_MARKERS = {
    "not sure",
    "unsure",
    "unknown",
    "unclear",
    "find out",
    "determine",
    "seems",
    "rumor",
    "mystery",
}

QUEST_TRANSIENT_TERMS = {
    "initiative",
    "attack",
    "damage",
    "short rest",
    "long rest",
    "shop",
    "buy",
    "bought",
    "purchase",
    "sold",
    "loot",
    "potion",
    "spell slot",
    "saving throw",
    "skill check",
}

QUEST_GENERIC_TARGET_WORDS = {
    "problem",
    "issue",
    "thing",
    "things",
    "something",
    "someone",
    "somebody",
    "whatever",
    "anything",
    "everything",
    "they",
    "them",
    "their",
    "have",
    "has",
    "with",
    "from",
    "into",
    "that",
    "this",
    "those",
    "these",
    "solve",
    "solving",
    "investigate",
    "investigation",
    "reported",
    "report",
}

QUEST_CONTEXT_STOPWORDS = {
    "the",
    "and",
    "king",
    "lord",
    "captain",
    "mayor",
    "sir",
    "lady",
    "city",
    "all",
    "lords",
    "duty",
    "fleet",
    "insists",
    "will",
    "one",
    "post",
    "gate",
    "burly",
    "captained",
    "crimes",
    "owes",
    "conscripted",
    "may",
}


@dataclass
class SessionRef:
    session_number: int
    date: str
    filename: str
    path: Path

    @property
    def session_label(self) -> str:
        return f"Session {self.session_number:02d}"

    @property
    def note_title(self) -> str:
        return self.path.stem


class PipelineError(Exception):
    pass


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return normalize_space(lowered)


def slugify(value: str) -> str:
    slug = normalize_name(value).replace(" ", "-")
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def title_case_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if DRY_RUN:
        print(f"[dry-run] skip write: {path}")
        return
    path.write_text(content, encoding="utf-8")


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
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise PipelineError(f"Unable to parse YAML data via ruby: {exc.stderr.strip()}") from exc
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
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise PipelineError(f"Unable to serialize YAML data via ruby: {exc.stderr.strip()}") from exc
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
        LEGACY_QUESTS_DIR / ".quest-map.yaml": QUEST_MAP_PATH,
    }

    for legacy, target in legacy_map.items():
        if legacy.exists():
            source = legacy
        elif not target.exists():
            continue
        else:
            continue
        if not source.exists():
            continue
        data = load_data(source, {})
        dump_data(target, data)
        if source != target and legacy.exists() and not DRY_RUN:
            legacy.unlink()

    migrate_session_artifacts()


def default_quest_signal_model() -> Dict[str, Any]:
    action_signals = []
    for phrase, action in QUEST_ACTION_PHRASES:
        action_signals.append(
            {
                "phrase": phrase,
                "action": action,
                "weight": 1.0,
                "accepted": 0,
                "rejected": 0,
            }
        )
    return {
        "schema_version": 1,
        "auto_accept_score": 7,
        "signals": action_signals,
        "strong_actions": sorted(QUEST_STRONG_ACTIONS),
        "mission_markers": sorted(QUEST_MISSION_MARKERS),
        "long_horizon_markers": sorted(QUEST_LONG_HORIZON_MARKERS),
        "open_question_markers": sorted(OPEN_QUESTION_MARKERS),
        "transient_terms": sorted(QUEST_TRANSIENT_TERMS),
        "generic_target_words": sorted(QUEST_GENERIC_TARGET_WORDS),
        "context_stopwords": sorted(QUEST_CONTEXT_STOPWORDS),
    }


def ensure_quest_signal_model() -> Dict[str, Any]:
    model = load_data(QUEST_SIGNALS_PATH, default_quest_signal_model())
    changed = False

    defaults = default_quest_signal_model()
    if "signals" not in model:
        model["signals"] = defaults["signals"]
        changed = True

    # Backfill fields introduced by newer schema versions.
    for key in [
        "schema_version",
        "auto_accept_score",
        "strong_actions",
        "mission_markers",
        "long_horizon_markers",
        "open_question_markers",
        "transient_terms",
        "generic_target_words",
        "context_stopwords",
    ]:
        if key not in model:
            model[key] = defaults[key]
            changed = True

    # Ensure each signal has counters and a weight for online adjustment.
    normalized_signals = []
    seen = set()
    for entry in model.get("signals", []):
        phrase = normalize_space(str(entry.get("phrase", ""))).lower()
        action = normalize_space(str(entry.get("action", ""))) or "Investigate"
        if not phrase:
            continue
        key = f"{phrase}|{action}"
        if key in seen:
            continue
        seen.add(key)
        normalized_signals.append(
            {
                "phrase": phrase,
                "action": action,
                "weight": float(entry.get("weight", 1.0)),
                "accepted": int(entry.get("accepted", 0)),
                "rejected": int(entry.get("rejected", 0)),
            }
        )
    if len(normalized_signals) != len(model.get("signals", [])):
        changed = True
    model["signals"] = normalized_signals

    if changed:
        dump_data(QUEST_SIGNALS_PATH, model)
    return model


def quest_signal_index(model: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for entry in model.get("signals", []):
        phrase = normalize_space(str(entry.get("phrase", ""))).lower()
        action = normalize_space(str(entry.get("action", "")))
        if not phrase or not action:
            continue
        index[phrase] = entry
    return index


def quest_candidate_id(session: SessionRef, candidate: Dict[str, Any]) -> str:
    payload = "|".join(
        [
            str(session.session_number),
            session.date,
            candidate.get("key", ""),
            candidate.get("title", ""),
            candidate.get("description", ""),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def load_quest_decisions() -> Dict[str, Any]:
    return load_data(QUEST_DECISIONS_PATH, {"schema_version": 1, "decisions": []})


def quest_decision_index(session: SessionRef, decisions: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for item in decisions.get("decisions", []):
        if item.get("session_number") != session.session_number:
            continue
        candidate_id = item.get("candidate_id")
        if not candidate_id:
            continue
        by_id[candidate_id] = item
    return by_id


def update_quest_signal_feedback(
    model: Dict[str, Any], matched_signals: List[str], accepted: bool
) -> None:
    if not matched_signals:
        return
    index = quest_signal_index(model)
    for phrase in matched_signals:
        key = normalize_space(phrase).lower()
        entry = index.get(key)
        if not entry:
            continue
        if accepted:
            entry["accepted"] = int(entry.get("accepted", 0)) + 1
            entry["weight"] = min(5.0, float(entry.get("weight", 1.0)) + 0.08)
        else:
            entry["rejected"] = int(entry.get("rejected", 0)) + 1
            entry["weight"] = max(0.2, float(entry.get("weight", 1.0)) - 0.12)

def migrate_session_artifacts() -> None:
    report_re = re.compile(
        r"^\.(\d{4}-\d{2}-\d{2})\s*-\s*Session\s*(\d{1,3})\s*-\s*Run Report\.md$"
    )

    if SUMMARIES_DIR.exists():
        for path in SUMMARIES_DIR.iterdir():
            if not path.is_file():
                continue

            rm = report_re.match(path.name)
            if rm:
                session = SessionRef(
                    session_number=int(rm.group(2)),
                    date=rm.group(1),
                    filename="",
                    path=NOTES_DIR / f"{rm.group(1)} - Session {int(rm.group(2)):02d}.md",
                )
                target = report_path_for(session)
                write_text(target, read_text(path))
                if not DRY_RUN:
                    path.unlink()


def convert_yaml_file(path: Path) -> bool:
    data = load_data(path, None)
    if data is None:
        return False
    dump_data(path, data)
    return True


def discover_sessions() -> List[SessionRef]:
    pattern = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s*-\s*Session\s*(?P<num>\d{1,3})\.md$")
    sessions: List[SessionRef] = []
    for path in sorted(NOTES_DIR.glob("*.md")):
        match = pattern.match(path.name)
        if not match:
            continue
        date = match.group("date")
        num = int(match.group("num"))
        sessions.append(
            SessionRef(session_number=num, date=date, filename=path.name, path=path)
        )
    if not sessions:
        raise PipelineError("No session notes found in Sessions/Notes.")
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
        raise PipelineError(f"Unsupported session selector: {selector}")

    requested = int(match.group(1))
    filtered = [s for s in sessions if s.session_number == requested]
    if not filtered:
        raise PipelineError(f"No session note found for Session {requested:02d}.")

    return sorted(filtered, key=lambda s: (s.date, s.filename))[-1]


def summary_filename(session: SessionRef) -> str:
    return f"{session.date} - Session {session.session_number:03d} - Summary.md"


def summary_stem(session: SessionRef) -> str:
    return Path(summary_filename(session)).stem


def session_meta_key(session: SessionRef) -> str:
    return f"{session.date}-s{session.session_number:03d}"


def session_meta_dir(session: SessionRef) -> Path:
    return META_SESSIONS_DIR / session_meta_key(session)


def parse_sections(text: str) -> Dict[str, str]:
    lines = text.splitlines()
    headings: List[Tuple[int, str, int]] = []
    for idx, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s*(.+?)\s*$", line)
        if not m:
            continue
        level = len(m.group(1))
        heading = m.group(2).strip().lower()
        headings.append((idx, heading, level))

    def section_for(keyword: str) -> str:
        for i, (start_idx, heading, level) in enumerate(headings):
            if heading.startswith(keyword):
                end_idx = len(lines)
                for nxt, _, nxt_level in headings[i + 1 :]:
                    if nxt_level <= level:
                        end_idx = nxt
                        break
                return "\n".join(lines[start_idx + 1 : end_idx]).strip()
        return ""

    previously = section_for("previously")
    now = section_for("now")

    scope = "full_note"
    if now:
        now_heading_match = re.search(r"^(#{1,6})\s*now\b", text, re.IGNORECASE | re.MULTILINE)
        if now_heading_match:
            scope = "after_h1_now" if len(now_heading_match.group(1)) == 1 else "after_h2_now"
        else:
            scope = "after_h2_now"

    return {"previously": previously, "now": now, "scope_used": scope}


def sentence_chunks(text: str) -> List[str]:
    out: List[str] = []
    for line in text.splitlines():
        line = normalize_space(line)
        if not line:
            continue
        if line.startswith(("-", "*", "\u2022")):
            line = normalize_space(line[1:])
            if line:
                out.append(line)
            continue
        if re.match(r"^\d+[\.)]\s+", line):
            out.append(re.sub(r"^\d+[\.)]\s+", "", line))
            continue
        if len(line) > 25:
            out.append(line)
    return out


def extract_events(text: str, limit: int = 24) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(sentence_chunks(text), start=1):
        if len(chunk) < 8:
            continue
        confidence = 0.72
        if chunk.endswith("."):
            confidence += 0.08
        if "?" in chunk:
            confidence -= 0.08
        events.append(
            {
                "id": f"ev-{idx:03d}",
                "text": chunk,
                "confidence": round(max(0.4, min(0.98, confidence)), 2),
            }
        )
        if len(events) >= limit:
            break
    return events


def extract_wikilinks(text: str) -> List[str]:
    out: List[str] = []
    pattern = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")
    for raw, display in pattern.findall(text):
        value = display if display else raw
        value = normalize_space(value)
        if value:
            out.append(value)
    return out


def extract_proper_nouns(text: str) -> List[str]:
    raw: List[str] = []
    pattern = re.compile(r"\b([A-Z][a-zA-Z'’\-]+(?:\s+[A-Z][a-zA-Z'’\-]+){0,3})\b")
    for candidate in pattern.findall(text):
        candidate = normalize_space(candidate)
        if not candidate:
            continue
        first = candidate.split(" ")[0]
        if first in STOP_WORDS:
            continue
        if len(candidate) <= 2 or "'" in candidate or "’" in candidate:
            continue
        raw.append(candidate)

    counts: Dict[str, int] = {}
    for candidate in raw:
        key = normalize_name(candidate)
        counts[key] = counts.get(key, 0) + 1

    candidates: List[str] = []
    for candidate in raw:
        words = candidate.split()
        lowered = candidate.lower()
        key = normalize_name(candidate)
        if len(words) == 1:
            if candidate in DISALLOWED_SINGLE_WORDS or lowered in {w.lower() for w in DISALLOWED_SINGLE_WORDS}:
                continue
            if counts.get(key, 0) < 2 and candidate not in {alias for seed in DEFAULT_RESOLVER_ENTITIES for alias in [seed["canonical_title"], *seed.get("true_aliases", [])]}:
                continue
        candidates.append(candidate)

    return candidates


def dedupe_preserve(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        key = normalize_name(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def is_entity_candidate(value: str) -> bool:
    value = normalize_space(value)
    if not value or len(value) < 3:
        return False
    if "'" in value or "’" in value:
        return False
    lowered = value.lower()
    blocked = {
        "its",
        "it",
        "would",
        "welcome",
        "you",
        "your",
        "they",
        "their",
        "them",
        "other",
        "first",
        "outside",
        "inside",
        "downstairs",
        "high",
        "message",
        "says",
        "intercepted",
        "bordered",
        "fought",
        "feels",
        "still",
        "where",
        "when",
        "what",
        "which",
        "who",
        "why",
        "how",
    }
    if lowered in blocked:
        return False
    return True


def guess_entity_type(name: str) -> str:
    lowered = name.lower()
    if any(t in lowered for t in ["alliance", "brotherhood", "society", "network", "harpers", "enclave"]):
        return "faction"
    if any(t in lowered for t in ["isles", "island", "sea", "harbor", "harbour", "bay", "town", "village", "road", "cave", "grotto"]):
        return "location"
    if any(t in lowered for t in ["cloak", "bag", "scroll", "pendant", "amulet", "rapier", "dagger", "trident", "ring"]):
        return "item"
    if any(t in lowered for t in ["shark", "sahaugin", "spectre", "yeti", "aboleth", "lion", "creature"]):
        return "creature"
    if any(t in lowered for t in ["lord", "king", "captain", "archdruid", "warden", "jarl", "mayor"]):
        return "character"
    if " " in name:
        return "character"
    return "unknown"


def load_resolver() -> Dict[str, Any]:
    default = {"schema_version": 1, "entities": DEFAULT_RESOLVER_ENTITIES}
    resolver = load_data(RESOLVER_PATH, default)
    if "entities" not in resolver:
        resolver = default
    return resolver


def resolver_index(resolver: Dict[str, Any]) -> List[Dict[str, Any]]:
    entities = resolver.get("entities", [])
    prepared = []
    for entry in entities:
        names = [entry.get("canonical_title", "")]
        names.extend(entry.get("true_aliases", []))
        names.extend(entry.get("observed_variants", []))
        names = [n for n in dedupe_preserve([normalize_space(x) for x in names if x])]
        prepared.append({"entry": entry, "names": names})
    return prepared


def score_match(mention: str, candidate_names: List[str]) -> float:
    mnorm = normalize_name(mention)
    if not mnorm:
        return 0.0

    best = 0.0
    for name in candidate_names:
        nnorm = normalize_name(name)
        if not nnorm:
            continue
        if mnorm == nnorm:
            exact = 1.0 if normalize_space(mention) == normalize_space(name) else 0.99
            best = max(best, exact)
            continue
        if mnorm in nnorm or nnorm in mnorm:
            overlap = min(len(mnorm), len(nnorm)) / max(len(mnorm), len(nnorm))
            best = max(best, 0.84 + overlap * 0.12)
            continue
        ratio = SequenceMatcher(None, mnorm, nnorm).ratio()
        best = max(best, ratio)

    return round(best, 4)


def resolve_mentions(
    mentions: List[str],
    resolver: Dict[str, Any],
    session: SessionRef,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    idx = resolver_index(resolver)

    entities: List[Dict[str, Any]] = []
    triage_items: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []

    for mention in mentions:
        guess = guess_entity_type(mention)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for candidate in idx:
            score = score_match(mention, candidate["names"])
            if score > 0:
                scored.append((score, candidate["entry"]))

        scored.sort(key=lambda t: t[0], reverse=True)
        best_score = scored[0][0] if scored else 0.0
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = round(best_score - second_score, 4)

        if scored and best_score >= 0.94 and margin >= 0.05:
            canonical = scored[0][1]["canonical_title"]
            entity_type = scored[0][1].get("entity_type", guess)
            entities.append(
                {
                    "mention": mention,
                    "canonical_title": canonical,
                    "entity_type": entity_type,
                    "resolution": "auto_link",
                    "confidence": best_score,
                    "match_margin": margin,
                }
            )
            continue

        if scored and best_score >= 0.80:
            candidates = []
            for score, entry in scored[:3]:
                candidates.append(
                    {
                        "canonical_title": entry["canonical_title"],
                        "entity_type": entry.get("entity_type", "unknown"),
                        "score": score,
                    }
                )

            item_id = hashlib.sha1(
                f"{session.session_number}|{session.date}|{mention}".encode("utf-8")
            ).hexdigest()[:12]
            blocking = guess in {"character", "unknown"}
            triage_items.append(
                {
                    "id": item_id,
                    "session_number": session.session_number,
                    "session_date": session.date,
                    "mention": mention,
                    "entity_type_guess": guess,
                    "reason": "medium_confidence_match",
                    "blocking": blocking,
                    "candidates": candidates,
                    "status": "open",
                    "created_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
                }
            )
            entities.append(
                {
                    "mention": mention,
                    "canonical_title": None,
                    "entity_type": guess,
                    "resolution": "triage_required",
                    "confidence": best_score,
                    "match_margin": margin,
                }
            )
            continue

        item_id = hashlib.sha1(
            f"new|{session.session_number}|{session.date}|{mention}".encode("utf-8")
        ).hexdigest()[:12]
        blocking = guess == "character"
        triage_items.append(
            {
                "id": item_id,
                "session_number": session.session_number,
                "session_date": session.date,
                "mention": mention,
                "entity_type_guess": guess,
                "reason": "new_or_low_confidence",
                "blocking": blocking,
                "candidates": [],
                "status": "open",
                "created_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
        )
        unresolved.append({"mention": mention, "entity_type_guess": guess, "confidence": best_score})
        entities.append(
            {
                "mention": mention,
                "canonical_title": None,
                "entity_type": guess,
                "resolution": "unresolved",
                "confidence": best_score,
                "match_margin": margin,
            }
        )

    return entities, triage_items, unresolved


def merge_triage_items(
    existing: Dict[str, Any], new_items: List[Dict[str, Any]], session: SessionRef
) -> Dict[str, Any]:
    queue = existing or {"schema_version": 1, "items": []}
    items = queue.get("items", [])
    items = [
        item
        for item in items
        if not (
            item.get("session_number") == session.session_number
            and item.get("status") == "open"
        )
    ]
    by_id = {item["id"]: item for item in items}

    for item in new_items:
        if item["id"] in by_id:
            current = by_id[item["id"]]
            if current.get("status") == "resolved":
                continue
            current.update({k: v for k, v in item.items() if k not in {"created_at"}})
        else:
            items.append(item)
    queue["items"] = items
    return queue


def normalize_keyword(value: str) -> str:
    return slugify(value)[:40]


def context_window_text(chunks: List[str], index: int, window: int = 2) -> str:
    start = max(0, index - window)
    end = min(len(chunks), index + window + 1)
    return " ".join(chunks[start:end])


def first_quest_action(chunk: str, model: Dict[str, Any]) -> Optional[Tuple[str, int, int, str, float]]:
    lowered = chunk.lower()
    matches: List[Tuple[int, int, str, str, int, int]] = []
    signals = sorted(
        model.get("signals", []),
        key=lambda item: len(str(item.get("phrase", ""))),
        reverse=True,
    )
    for signal in signals:
        phrase = normalize_space(str(signal.get("phrase", ""))).lower()
        action = normalize_space(str(signal.get("action", ""))) or "Investigate"
        if not phrase:
            continue
        match = re.search(rf"\b{re.escape(phrase)}\b", lowered)
        if not match:
            continue
        matches.append((match.start(), -len(phrase), phrase, action, match.start(), match.end()))

    if not matches:
        return None
    non_go = [m for m in matches if m[2] != "go"]
    pool = non_go or matches
    best = sorted(pool, key=lambda t: (t[0], t[1]))[0]
    signal_idx = quest_signal_index(model)
    weight = float(signal_idx.get(best[2], {}).get("weight", 1.0))
    return (best[3], best[4], best[5], best[2], weight)


def quest_context_anchors(chunks: List[str], index: int) -> List[str]:
    context = context_window_text(chunks, index, window=4)
    mentions: List[str] = []
    mentions.extend(extract_wikilinks(context))
    mentions.extend(extract_proper_nouns(context))

    for match in re.finditer(
        r"\b(?:from|to|in|at|off|near)\s+([A-Z][a-zA-Z'’\-]+(?:\s+[A-Z][a-zA-Z'’\-]+){0,2})",
        context,
    ):
        mentions.append(normalize_space(match.group(1)))
    for match in re.finditer(
        r"\b([A-Z][a-zA-Z'’\-]+)\s+is\s+(?:west|east|north|south)\s+of\b",
        context,
    ):
        mentions.append(normalize_space(match.group(1)))
    for word in re.findall(r"\b([A-Z][a-zA-Z'’\-]{2,})\b", context):
        mentions.append(normalize_space(word))

    mentions = dedupe_preserve(mentions)
    anchors: List[str] = []
    blocked_names = {normalize_name(x) for x in STOP_WORDS.union(DISALLOWED_SINGLE_WORDS)}
    for mention in mentions:
        if not is_entity_candidate(mention):
            continue
        if normalize_name(mention) in blocked_names:
            continue
        anchors.append(mention)
    return anchors[:6]


def clean_quest_target(raw_target: str) -> str:
    target = normalize_space(raw_target.strip(" .,:;-"))
    if not target:
        return ""
    target = re.split(r"[.;!?]", target, maxsplit=1)[0]
    target = re.sub(
        r"^(to|the|a|an|about|for|if|that|whether|who|what|where|why|how)\s+",
        "",
        target,
        flags=re.IGNORECASE,
    )
    target = re.sub(r"\b(and then|then|after|before|while|when)\b.*$", "", target, flags=re.IGNORECASE)
    return normalize_space(target.strip(" .,:;-"))


def quest_target_tokens(target: str, model: Dict[str, Any]) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", target)
    tokens = []
    generic_words = set(model.get("generic_target_words", []))
    for word in words:
        lowered = word.lower()
        if lowered in generic_words:
            continue
        if len(lowered) < 3 and lowered not in {"npc"}:
            continue
        tokens.append(word)
    return tokens


def quest_tokens_from_anchors(anchors: List[str], context: str, model: Dict[str, Any]) -> List[str]:
    location_tokens: List[str] = []
    other_tokens: List[str] = []
    lowered_context = context.lower()
    context_stopwords = set(model.get("context_stopwords", []))
    generic_words = set(model.get("generic_target_words", []))
    for anchor in anchors:
        starts_with_title = anchor.split(" ", 1)[0].lower() in {"king", "lord", "captain", "mayor"}
        anchor_norm = re.escape(anchor.lower())
        location_hint = (
            guess_entity_type(anchor) == "location"
            or (
                not starts_with_title
                and re.search(rf"\b{anchor_norm}\s+is\s+(?:west|east|north|south)\s+of\b", lowered_context)
            )
            or (
                not starts_with_title
                and re.search(rf"\b(?:from|to|in|at|off|near)\s+{anchor_norm}\b", lowered_context)
            )
        )
        bucket = location_tokens if location_hint else other_tokens
        for word in re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", anchor):
            lowered = word.lower()
            if lowered in generic_words:
                continue
            if lowered in context_stopwords:
                continue
            if len(lowered) < 3:
                continue
            bucket.append(word)
    return dedupe_preserve(location_tokens + other_tokens)


def has_mission_signal(text: str, model: Dict[str, Any]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in model.get("mission_markers", []))


def mission_anchor_tokens(context: str, model: Dict[str, Any]) -> List[str]:
    hints: List[str] = []
    for match in re.finditer(
        r"\b([A-Z][a-zA-Z'’\-]+)\s+is\s+(?:west|east|north|south)\s+of\b",
        context,
    ):
        hints.append(match.group(1))
    for match in re.finditer(
        r"\bfrom\s+(?!King\b|Lord\b|Captain\b|Mayor\b)([A-Z][a-zA-Z'’\-]+)\b",
        context,
    ):
        hints.append(match.group(1))
    tokens = quest_target_tokens(" ".join(hints), model)
    return dedupe_preserve(tokens)


def is_open_question_chunk(chunk: str, model: Dict[str, Any]) -> bool:
    lowered = chunk.lower()
    if not any(marker in lowered for marker in model.get("open_question_markers", [])):
        return False
    if any(term in lowered for term in model.get("transient_terms", [])):
        return False
    return True


def quest_candidate_score(
    chunk: str,
    target_tokens: List[str],
    action: str,
    mission_signal: bool,
    anchor_count: int,
    signal_weight: float,
    model: Dict[str, Any],
) -> int:
    lowered = chunk.lower()
    score = 2 + int(round(max(0.0, signal_weight) * 0.5))
    strong_actions = set(model.get("strong_actions", []))
    if action in strong_actions:
        score += 1
    if mission_signal:
        score += 1
    if anchor_count > 0:
        score += 1
    if any(marker in lowered for marker in model.get("long_horizon_markers", [])):
        score += 1
    if len(target_tokens) >= 2:
        score += 1
    if len(target_tokens) >= 4:
        score += 1
    if any(term in lowered for term in model.get("transient_terms", [])):
        score -= 2
    if re.search(r"\b\d+\s*(cp|sp|gp|pp|copper|silver|gold)\b", lowered):
        score -= 2
    if len(chunk.split()) < 6:
        score -= 1
    if not target_tokens:
        score -= 2
    return score


def quest_title(action: str, target_tokens: List[str]) -> str:
    if not target_tokens:
        return action
    words = [w[0].upper() + w[1:] if w else w for w in target_tokens[:4]]
    return f"{action} {' '.join(words)}"


def quest_keywords(chunk: str, action: str, target_tokens: List[str], model: Dict[str, Any]) -> List[str]:
    extracted = [normalize_keyword(action)]
    extracted.extend(normalize_keyword(token) for token in target_tokens[:6])

    mentions = dedupe_preserve(extract_wikilinks(chunk) + extract_proper_nouns(chunk))
    for mention in mentions[:4]:
        extracted.append(normalize_keyword(mention))

    out = []
    generic_words = set(model.get("generic_target_words", []))
    for keyword in extracted:
        if not keyword:
            continue
        if keyword.replace("-", " ") in generic_words:
            continue
        out.append(keyword)
    return dedupe_preserve(out)[:10]


def extract_quest_candidates(text: str, model: Dict[str, Any]) -> List[Dict[str, Any]]:
    chunks = sentence_chunks(text)
    quests: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        context = context_window_text(chunks, idx)
        anchors = quest_context_anchors(chunks, idx)
        anchor_tokens = quest_tokens_from_anchors(anchors, context, model)
        mission_tokens = mission_anchor_tokens(context, model)
        mission_signal = has_mission_signal(context, model)
        action_match = first_quest_action(chunk, model)
        if action_match:
            action, _, action_end, matched_phrase, signal_weight = action_match
            target = clean_quest_target(chunk[action_end:])
            raw_target_tokens = quest_target_tokens(target, model)
            if re.search(r"\b\d+\s*(cp|sp|gp|pp|copper|silver|gold)\b", chunk.lower()) and not mission_signal:
                continue
            target_tokens = raw_target_tokens
            if len(target_tokens) < 2:
                target_tokens = dedupe_preserve(mission_tokens + target_tokens + anchor_tokens)

            score = quest_candidate_score(
                chunk,
                target_tokens,
                action=action,
                mission_signal=mission_signal,
                anchor_count=len(anchors),
                signal_weight=signal_weight,
                model=model,
            )

            strong_actions = set(model.get("strong_actions", []))
            if action in strong_actions and (mission_signal or anchor_tokens):
                score = max(score, 3)
            if score < 3:
                continue

            title_tokens = dedupe_preserve(mission_tokens + raw_target_tokens) if mission_tokens else raw_target_tokens
            if mission_tokens and not title_tokens:
                title_tokens = mission_tokens
            if not title_tokens:
                title_tokens = target_tokens

            title = quest_title(action, title_tokens)
            key = slugify(title)
            if key in {"investigate", "track", "find", "report", "meet", "uncover"}:
                continue

            quests.append(
                {
                    "key": key,
                    "title": title,
                    "description": chunk.strip(" ."),
                    "keywords": quest_keywords(context, action, dedupe_preserve(target_tokens + mission_tokens), model),
                    "matched_signals": [matched_phrase],
                    "score": score,
                }
            )
            continue

        if not is_open_question_chunk(chunk, model):
            continue
        if not mission_signal and not any(guess_entity_type(a) in {"location", "faction", "item", "creature"} for a in anchors):
            continue
        question_tokens = quest_target_tokens(chunk, model)
        if not anchor_tokens and not mission_tokens and not question_tokens:
            continue
        open_tokens = dedupe_preserve(question_tokens + mission_tokens + anchor_tokens)
        action = "Uncover"
        score = quest_candidate_score(
            chunk,
            open_tokens,
            action=action,
            mission_signal=mission_signal,
            anchor_count=len(anchors),
            signal_weight=1.0,
            model=model,
        )
        if "not sure" in chunk.lower() or "unknown" in chunk.lower():
            score = max(score, 3)
        if score < 3:
            continue

        title = quest_title(action, open_tokens)
        key = slugify(title)
        if key in {"investigate", "track", "find", "report", "meet", "uncover"}:
            continue

        quests.append(
            {
                "key": key,
                "title": title,
                "description": f"Open question: {chunk.strip(' .')}",
                "keywords": quest_keywords(context, action, open_tokens, model),
                "matched_signals": ["open-question"],
                "score": score,
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    for quest in quests:
        idx = seen.get(quest["key"])
        if idx is None:
            seen[quest["key"]] = len(deduped)
            deduped.append(quest)
            continue
        deduped[idx]["keywords"] = dedupe_preserve(deduped[idx].get("keywords", []) + quest.get("keywords", []))
        deduped[idx]["matched_signals"] = dedupe_preserve(
            deduped[idx].get("matched_signals", []) + quest.get("matched_signals", [])
        )
        deduped[idx]["score"] = max(deduped[idx].get("score", 0), quest.get("score", 0))

    deduped.sort(key=lambda q: q.get("score", 0), reverse=True)
    return deduped[:8]


def select_quests_from_candidates(
    session: SessionRef,
    candidates: List[Dict[str, Any]],
    model: Dict[str, Any],
    decisions: Dict[str, Any],
) -> List[Dict[str, Any]]:
    auto_accept = int(model.get("auto_accept_score", 4))
    decision_by_id = quest_decision_index(session, decisions)

    selected: List[Dict[str, Any]] = []
    for candidate in candidates:
        cid = quest_candidate_id(session, candidate)
        decision = decision_by_id.get(cid)
        if decision:
            mode = normalize_space(str(decision.get("decision", ""))).lower()
            if mode in {"reject", "defer"}:
                continue
            if mode == "accept":
                chosen = dict(candidate)
                title_override = normalize_space(str(decision.get("title_override", "")))
                if title_override:
                    chosen["title"] = title_override
                    chosen["key"] = slugify(title_override)
                extra_keywords = [
                    normalize_keyword(k)
                    for k in decision.get("keywords_add", [])
                    if normalize_keyword(k)
                ]
                chosen["keywords"] = dedupe_preserve(chosen.get("keywords", []) + extra_keywords)
                selected.append(chosen)
                continue

        if int(candidate.get("score", 0)) >= auto_accept:
            selected.append(dict(candidate))

    selected.sort(key=lambda q: int(q.get("score", 0)), reverse=True)
    for item in selected:
        item.pop("score", None)
    return selected[:8]


def run_interactive_quest_review(
    session: SessionRef, analysis: Dict[str, Any]
) -> Dict[str, Any]:
    model = ensure_quest_signal_model()
    decisions = load_quest_decisions()
    decision_by_id = quest_decision_index(session, decisions)
    auto_accept = int(model.get("auto_accept_score", 4))

    candidates = analysis.get("quest_candidates", []) or []
    review_queue = []
    for candidate in candidates:
        cid = quest_candidate_id(session, candidate)
        if cid in decision_by_id:
            continue
        if int(candidate.get("score", 0)) >= auto_accept:
            continue
        review_queue.append((cid, candidate))

    if not review_queue:
        return {"accepted": 0, "rejected": 0, "deferred": 0, "pending": 0}

    if DRY_RUN:
        print(f"[dry-run] quest-review preview: pending_candidates={len(review_queue)}")
        return {"accepted": 0, "rejected": 0, "deferred": 0, "pending": len(review_queue)}

    if not sys.stdin.isatty():
        print(f"Quest review pending: {len(review_queue)} candidates (non-interactive mode).")
        return {"accepted": 0, "rejected": 0, "deferred": 0, "pending": len(review_queue)}

    accepted = 0
    rejected = 0
    deferred = 0

    print(f"\nQuest review for Session {session.session_number:02d}: {len(review_queue)} candidates\n")
    for cid, candidate in review_queue:
        print("-" * 72)
        print(f"Title: {candidate.get('title')}")
        print(f"Score: {candidate.get('score')}")
        print(f"Description: {candidate.get('description')}")
        print(f"Keywords: {', '.join(candidate.get('keywords', []))}")
        answer = input("Decision [a=accept, e=accept+edit title, r=reject, d=defer] (default d): ").strip().lower()
        if not answer:
            answer = "d"

        record = {
            "candidate_id": cid,
            "candidate_key": candidate.get("key"),
            "session_number": session.session_number,
            "session_date": session.date,
            "decided_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        if answer == "a":
            record["decision"] = "accept"
            accepted += 1
            update_quest_signal_feedback(model, candidate.get("matched_signals", []), accepted=True)
        elif answer == "e":
            edited = input(f"Title [{candidate.get('title')}]: ").strip()
            record["decision"] = "accept"
            if edited:
                record["title_override"] = edited
            accepted += 1
            update_quest_signal_feedback(model, candidate.get("matched_signals", []), accepted=True)
        elif answer == "r":
            record["decision"] = "reject"
            rejected += 1
            update_quest_signal_feedback(model, candidate.get("matched_signals", []), accepted=False)
        else:
            record["decision"] = "defer"
            deferred += 1

        decisions.setdefault("decisions", []).append(record)

    dump_data(QUEST_DECISIONS_PATH, decisions)
    dump_data(QUEST_SIGNALS_PATH, model)
    return {"accepted": accepted, "rejected": rejected, "deferred": deferred, "pending": 0}


def previous_summaries(session: SessionRef, window: int) -> List[str]:
    files = []
    pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*-\s*Session\s*(\d{1,3})\s*-\s*Summary\.md$")
    for path in SUMMARIES_DIR.glob("*.md"):
        match = pattern.match(path.name)
        if not match:
            continue
        num = int(match.group(2))
        if num >= session.session_number:
            continue
        files.append((num, match.group(1), path))

    files.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [item[2].name for item in files[:window]]


def report_path_for(session: SessionRef) -> Path:
    return session_meta_dir(session) / "run-report.md"


def write_run_report(session: SessionRef, title: str, lines: List[str]) -> None:
    report = [f"# {title}", "", f"- Session: {session.session_label}", f"- Date: {session.date}"]
    report.append(f"- Timestamp: {dt.datetime.utcnow().isoformat(timespec='seconds')}Z")
    report.append("")
    report.extend(lines)
    write_text(report_path_for(session), "\n".join(report).rstrip() + "\n")


def events_path_for(session: SessionRef) -> Path:
    return session_meta_dir(session) / "events.yaml"


def world_path_for(session: SessionRef) -> Path:
    return session_meta_dir(session) / "world.yaml"


def to_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def score_from_confidence(value: Any) -> int:
    score = int(round(to_float(value, 0.7) * 10))
    return max(1, min(10, score))


def lint_stage1_outputs(session: SessionRef) -> None:
    if DRY_RUN:
        print(f"[dry-run] skip Stage 1 lint for Session {session.session_number:02d}")
        return

    if not EVENTS_LINT_SCRIPT.exists() or not WORLD_LINT_SCRIPT.exists():
        raise PipelineError(
            "Missing dnd-session-analyze lint scripts. Expected "
            f"`{EVENTS_LINT_SCRIPT}` and `{WORLD_LINT_SCRIPT}`."
        )

    missing = []
    if not events_path_for(session).exists():
        missing.append(str(events_path_for(session).relative_to(REPO_ROOT)))
    if not world_path_for(session).exists():
        missing.append(str(world_path_for(session).relative_to(REPO_ROOT)))
    if missing:
        listed = ", ".join(f"`{item}`" for item in missing)
        raise PipelineError(
            f"Missing Stage 1 artifacts: {listed}. Run `$dnd-session-analyze` for {session.session_label} first."
        )

    events_cmd = [sys.executable, str(EVENTS_LINT_SCRIPT), "--session", session.session_label]
    world_cmd = [sys.executable, str(WORLD_LINT_SCRIPT), "--session", session.session_label]

    for cmd in [events_cmd, world_cmd]:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)
        if proc.returncode != 0:
            details = "\n".join(x for x in [proc.stdout.strip(), proc.stderr.strip()] if x)
            raise PipelineError(f"Stage 1 lint failed.\n{details}".strip())


def world_triage_state(world_data: Dict[str, Any]) -> Dict[str, Any]:
    entities = world_data.get("entities", []) if isinstance(world_data, dict) else []
    if not isinstance(entities, list):
        entities = []

    open_items = [
        item
        for item in entities
        if isinstance(item, dict)
        and normalize_space(str(item.get("resolution_status", ""))).lower() in WORLD_OPEN_STATUSES
    ]
    blocking = [item for item in open_items if bool(item.get("blocking"))]
    resolved = [
        item
        for item in entities
        if isinstance(item, dict)
        and normalize_space(str(item.get("resolution_status", ""))).lower() in {"resolved", "ignored"}
    ]
    return {
        "open_items": open_items,
        "open_count": len(open_items),
        "blocking_count": len(blocking),
        "resolved_count": len(resolved),
    }


def build_analysis_from_stage1(session: SessionRef, context_window: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    events_path = events_path_for(session)
    world_path = world_path_for(session)

    events_data = load_data(events_path, None)
    world_data = load_data(world_path, None)

    if not isinstance(events_data, dict):
        raise PipelineError(
            f"Missing or invalid Stage 1 events artifact: `{events_path.relative_to(REPO_ROOT)}`"
        )
    if not isinstance(world_data, dict):
        raise PipelineError(
            f"Missing or invalid Stage 1 world artifact: `{world_path.relative_to(REPO_ROOT)}`"
        )

    event_entries = events_data.get("events", [])
    if not isinstance(event_entries, list):
        event_entries = []

    events = []
    event_ids = set()
    for idx, item in enumerate(event_entries, start=1):
        if not isinstance(item, dict):
            continue
        title = normalize_space(str(item.get("title", "")))
        description = normalize_space(str(item.get("description", "")))
        text = f"{title}: {description}" if title and description else (title or description)
        if not text:
            text = f"Event {idx}"
        event_id = normalize_space(str(item.get("id", "")))
        if event_id:
            event_ids.add(event_id)
        events.append(
            {
                "id": event_id or f"ev-{session.session_number}-{idx:03d}",
                "text": text,
                "confidence": to_float(item.get("confidence"), 0.75),
            }
        )

    entity_entries = world_data.get("entities", [])
    if not isinstance(entity_entries, list):
        entity_entries = []

    resolution_map = {
        "resolved": "auto_link",
        "triage_required": "triage_required",
        "unresolved": "unresolved",
        "ignored": "unresolved",
    }

    entities = []
    unresolved_entities = []
    for item in entity_entries:
        if not isinstance(item, dict):
            continue
        mention = normalize_space(str(item.get("mention", "")))
        if not mention:
            continue
        canonical = normalize_space(str(item.get("canonical_title", ""))) or None
        entity_type = normalize_space(str(item.get("entity_type", "unknown"))).lower()
        if entity_type not in ENTITY_TYPES:
            entity_type = "unknown"

        status = normalize_space(str(item.get("resolution_status", ""))).lower()
        resolution = resolution_map.get(status, "unresolved")
        match_margin = None
        spans = item.get("evidence_spans", [])
        if isinstance(spans, list) and spans:
            first = spans[0]
            if isinstance(first, dict):
                start = normalize_space(str(first.get("start_index", "")))
                end = normalize_space(str(first.get("end_index", "")))
                if start and end:
                    match_margin = f"{start}-{end}"

        normalized = {
            "mention": mention,
            "canonical_title": canonical,
            "entity_type": entity_type,
            "resolution": resolution,
            "confidence": to_float(item.get("confidence"), 0.7),
            "match_margin": match_margin,
        }
        entities.append(normalized)
        if resolution in {"triage_required", "unresolved"}:
            unresolved_entities.append(normalized)

    raw_candidates = events_data.get("quest_candidates", [])
    if not isinstance(raw_candidates, list):
        raw_candidates = []

    quest_candidates = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        title = normalize_space(str(item.get("title", "")))
        key = normalize_keyword(str(item.get("key", "")))
        if not key and title:
            key = slugify(title)
        if not key:
            continue
        quest_candidates.append(
            {
                "key": key,
                "title": title or title_case_slug(key),
                "description": normalize_space(str(item.get("description", ""))),
                "keywords": dedupe_preserve(
                    [
                        normalize_keyword(str(kw))
                        for kw in item.get("keywords", [])
                        if normalize_keyword(str(kw))
                    ]
                )
                if isinstance(item.get("keywords"), list)
                else [],
                "matched_signals": [],
                "score": score_from_confidence(item.get("confidence")),
            }
        )

    quest_model = ensure_quest_signal_model()
    quest_decisions = load_quest_decisions()
    quests = select_quests_from_candidates(session, quest_candidates, quest_model, quest_decisions)

    session_block = events_data.get("session", {}) if isinstance(events_data.get("session"), dict) else {}
    context_block = events_data.get("context", {}) if isinstance(events_data.get("context"), dict) else {}

    source_note = normalize_space(str(session_block.get("source_note", ""))) or str(
        session.path.relative_to(REPO_ROOT)
    )
    scope_used = normalize_space(str(session_block.get("scope_used", ""))) or "now"

    previous = context_block.get("previous_summaries", [])
    if not isinstance(previous, list):
        previous = []
    previous = [normalize_space(str(p)) for p in previous if normalize_space(str(p))]

    triage_state = world_triage_state(world_data)
    uncertainties = dedupe_preserve([e.get("mention", "") for e in unresolved_entities if e.get("mention")])

    analysis = {
        "schema_version": 1,
        "session": {
            "session_number": session.session_number,
            "date": session.date,
            "source_note": source_note,
            "scope_used": scope_used,
        },
        "context": {
            "previous_summaries": previous if previous else previous_summaries(session, context_window),
            "context_window": context_window,
        },
        "events": events,
        "entities": entities,
        "quest_candidates": quest_candidates,
        "quests": quests,
        "uncertainties": uncertainties,
        "unresolved_entities": unresolved_entities,
        "proposed_changes": {
            "summary": summary_filename(session),
            "quest_updates": [q["key"] for q in quests],
            "quest_candidates": [q["key"] for q in quest_candidates],
            "world_updates": sorted(
                {
                    e.get("canonical_title")
                    for e in entities
                    if e.get("canonical_title") and e.get("entity_type") in WORLD_TYPE_DIR
                }
            ),
        },
        "note_patch_candidates": {
            "next_session": session.session_number + 1,
            "target_summary": summary_stem(session),
        },
        "quality": {
            "events_count": len(events),
            "mentions_count": len({e.get("mention") for e in entities if e.get("mention")}),
            "triage_candidates": triage_state["open_count"],
            "quest_candidates": len(quest_candidates),
            "quests_selected": len(quests),
            "confidence_summary": {
                "auto_linked": len([e for e in entities if e.get("resolution") == "auto_link"]),
                "triage_required": len([e for e in entities if e.get("resolution") == "triage_required"]),
                "unresolved": len([e for e in entities if e.get("resolution") == "unresolved"]),
            },
        },
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    return analysis, world_data


def load_analysis_or_stage1(
    session: SessionRef, context_window: int, refresh: bool = False
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    lint_stage1_outputs(session)
    analysis, world_data = build_analysis_from_stage1(session, context_window)
    return analysis, world_data


def ensure_resolver_defaults() -> Dict[str, Any]:
    resolver = load_resolver()
    existing = {e.get("canonical_title") for e in resolver.get("entities", [])}
    for seed in DEFAULT_RESOLVER_ENTITIES:
        if seed["canonical_title"] not in existing:
            resolver.setdefault("entities", []).append(seed)
    dump_data(RESOLVER_PATH, resolver)
    return resolver


def link_entity(surface: str, canonical: str) -> str:
    if normalize_name(surface) == normalize_name(canonical):
        return f"[[{canonical}]]"
    return f"[[{canonical}|{surface}]]"


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
    pairs = []
    for entry in resolver.get("entities", []):
        canonical = entry.get("canonical_title")
        if not canonical:
            continue
        names = [canonical]
        names.extend(entry.get("true_aliases", []))
        names = dedupe_preserve([n for n in names if n])
        for name in names:
            pairs.append((name, canonical))
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def linkify_text(text: str, resolver: Dict[str, Any]) -> str:
    frontmatter = ""
    body = text
    fm_match = re.match(r"\A---\n.*?\n---\n?", text, re.DOTALL)
    if fm_match:
        frontmatter = fm_match.group(0)
        body = text[fm_match.end() :]

    safe, mapping = protect_existing_links(body)

    for surface_name, canonical in resolver_aliases(resolver):
        pattern = re.compile(rf"(?<![\w\]])({re.escape(surface_name)})(?![\w\[])")

        def _repl(match: re.Match[str]) -> str:
            return link_entity(match.group(1), canonical)

        safe = pattern.sub(_repl, safe)

    safe = restore_existing_links(safe, mapping)
    return frontmatter + safe


def markdown_targets() -> Dict[str, List[Path]]:
    by_stem: Dict[str, List[Path]] = {}
    for path in REPO_ROOT.rglob("*.md"):
        stem = path.stem
        by_stem.setdefault(stem, []).append(path)
    return by_stem


def lint_files(paths: List[Path]) -> Dict[str, Any]:
    targets = markdown_targets()
    errors: List[str] = []
    warnings: List[str] = []
    checked = 0

    link_pattern = re.compile(r"!?\[\[([^\]]+)\]\]")
    heading_pattern = re.compile(r"^(#{1,6})\s+")

    for path in paths:
        if not path.exists() or path.suffix.lower() != ".md":
            continue
        checked += 1
        text = read_text(path)
        lines = text.splitlines()

        blank_run = 0
        prev_heading_level = 0
        for i, line in enumerate(lines, start=1):
            if line.rstrip() != line:
                errors.append(f"{path.relative_to(REPO_ROOT)}:{i} trailing whitespace")

            if line.strip() == "":
                blank_run += 1
                if blank_run > 2:
                    warnings.append(
                        f"{path.relative_to(REPO_ROOT)}:{i} more than two consecutive blank lines"
                    )
            else:
                blank_run = 0

            hm = heading_pattern.match(line)
            if hm:
                level = len(hm.group(1))
                if prev_heading_level and level - prev_heading_level > 1:
                    warnings.append(
                        f"{path.relative_to(REPO_ROOT)}:{i} heading jump h{prev_heading_level}->h{level}"
                    )
                prev_heading_level = level

                if i > 1 and lines[i - 2].strip() and not lines[i - 2].startswith("---"):
                    warnings.append(
                        f"{path.relative_to(REPO_ROOT)}:{i} missing blank line before heading"
                    )
                if i < len(lines) and lines[i].strip() and not lines[i].startswith("|"):
                    warnings.append(
                        f"{path.relative_to(REPO_ROOT)}:{i} missing blank line after heading"
                    )

            for m in link_pattern.finditer(line):
                raw = m.group(1)
                target = raw.split("|", 1)[0].split("#", 1)[0].strip()
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
                        f"{path.relative_to(REPO_ROOT)}:{i} unresolved wikilink target '{target}'"
                    )

    return {"checked_files": checked, "errors": errors, "warnings": warnings}


def write_lint_report(result: Dict[str, Any], report_path: Optional[Path] = None) -> Path:
    target = report_path or LINT_REPORT_PATH
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
        lines.extend(f"- {msg}" for msg in result["errors"])
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Warnings")
    if result["warnings"]:
        lines.extend(f"- {msg}" for msg in result["warnings"])
    else:
        lines.append("- None")

    write_text(target, "\n".join(lines).rstrip() + "\n")
    return target


def ensure_summary_quality(analysis: Dict[str, Any]) -> None:
    events_count = analysis.get("quality", {}).get("events_count", 0)
    if events_count < 2:
        raise PipelineError("Risk gate: insufficient extracted events for reliable summary generation.")


def choose_locations(analysis: Dict[str, Any]) -> List[str]:
    out = []
    for e in analysis.get("entities", []):
        if e.get("entity_type") == "location" and e.get("canonical_title"):
            out.append(e["canonical_title"])
    out = dedupe_preserve(out)
    return out[:3]


def choose_party_links(resolver: Dict[str, Any]) -> str:
    preferred = CAMPAIGN_CONFIG.get("summary_party", CAMPAIGN_CONFIG.get("party_members", []))
    parts = []
    for name in preferred:
        entry = next(
            (x for x in resolver.get("entities", []) if x.get("canonical_title") == name), None
        )
        if not entry:
            continue
        display = entry.get("true_aliases", [name])[0] if entry.get("true_aliases") else name
        parts.append(link_entity(display, name))
    return ", ".join(parts)


def generate_summary(session: SessionRef, analysis: Dict[str, Any], resolver: Dict[str, Any]) -> str:
    events = analysis.get("events", [])
    if not events:
        events = [{"text": "Session notes require manual review.", "confidence": 0.5}]

    key_events = events[:6]
    focus = configured_player_character(CAMPAIGN_CONFIG)
    if not focus:
        raise PipelineError("Player character is not configured. Run $dnd-session-setup first.")
    focus_entry = next((entry for entry in resolver.get("entities", [])
                        if focus in [entry.get("canonical_title"), *entry.get("true_aliases", [])]), {})
    focus_names = [focus, *focus_entry.get("true_aliases", [])]
    focus_events = [e for e in events if any(name.lower() in e.get("text", "").lower() for name in focus_names)][:3]
    if not focus_events:
        focus_events = key_events[:2]

    locations = choose_locations(analysis)
    location_links = ", ".join(f"[[{loc}]]" for loc in locations) if locations else "[[Unknown Location]]"

    summary = []
    summary.append("---")
    summary.append(f"title: Session {session.session_number:02d} - Session {session.session_number:02d}")
    summary.append(f"session_number: {session.session_number:02d}")
    summary.append(f"date: {session.date}")
    summary.append(f"scope_used: {analysis['session'].get('scope_used', 'full_note')}")
    summary.append("quality_state: draft")
    summary.append("---")
    summary.append(
        f"# Session {session.session_number:02d}: [[Sessions/Notes/{session.note_title}|Session {session.session_number:02d} Notes]]"
    )
    summary.append("")
    summary.append(f"**Date:** {session.date}")
    summary.append(f"**Location(s):** {location_links}")
    summary.append(f"**Party Composition:** {choose_party_links(resolver)}")
    summary.append(f"**Player Character:** [[{focus_entry.get('canonical_title', focus)}]]")
    summary.append("")
    summary.append("## 🎲 Summary")
    summary.append("")
    recap = " ".join(e["text"].rstrip(".") + "." for e in events[:4])
    summary.append(recap)
    summary.append("")
    summary.append("## 🎯 Player Lens")
    summary.append("")
    summary.append("- **Personal Stakes:**")
    for ev in focus_events[:2]:
        summary.append(f"  - {ev['text']}")
    summary.append("- **Character Signals:**")
    for ev in focus_events[1:3]:
        summary.append(f"  - {ev['text']}")
    summary.append("- **Forward Pressure:**")
    summary.append(f"  - Which active threads should {focus} push in the next session?")
    summary.append("")
    summary.append("## 🔑 Key Events")
    summary.append("")
    for idx, ev in enumerate(key_events[:5], start=1):
        summary.append(f"{idx}. **Event {idx}:** {ev['text']}")
    summary.append("")
    summary.append("## 📍 Locations Visited")
    summary.append("")
    if locations:
        for loc in locations:
            summary.append(f"- **[[{loc}]]:** Referenced during the session.")
    else:
        summary.append("- **[[Unknown Location]]:** Location details require confirmation.")
    summary.append("")
    summary.append("## 🧑‍🤝‍🧑 NPCs & Factions")
    summary.append("")
    summary.append("| NPC / Faction | Role & Notes |")
    summary.append("|---|---|")
    for e in analysis.get("entities", [])[:10]:
        canonical = e.get("canonical_title") or e.get("mention")
        summary.append(f"| [[{canonical}]] | Mentioned in session events. |")
    summary.append("")
    summary.append("## 🗡️ Items & Treasure")
    summary.append("")
    summary.append("| Item | Source / Holder | Notes |")
    summary.append("|---|---|---|")
    for e in analysis.get("entities", []):
        if e.get("entity_type") == "item":
            canonical = e.get("canonical_title") or e.get("mention")
            summary.append(f"| [[{canonical}]] | Session events | Track custody in world notes. |")
    summary.append("")
    summary.append("## 🧩 Plot Threads & Hooks")
    summary.append("")
    for quest in analysis.get("quests", [])[:5]:
        qtitle = normalize_space(quest.get("title") or title_case_slug(quest["key"]))
        summary.append(f"- **Ongoing:** [[Quests/Active/{qtitle}|{qtitle}]] — {quest['description']}")
    summary.append("- **To-Do / Next Steps:**")
    for quest in analysis.get("quests", [])[:3]:
        qtitle = normalize_space(quest.get("title") or title_case_slug(quest["key"]))
        summary.append(f"  1. [[Quests/Active/{qtitle}|{qtitle}]]")
    summary.append("")
    summary.append("## ❓ Open Questions & Uncertain Facts")
    summary.append("")
    for name in analysis.get("uncertainties", [])[:6]:
        summary.append(f"- {name} (confidence: low)")
    summary.append("")
    summary.append("## 🏅 Session Highlights")
    summary.append("")
    summary.append("- **Player Spotlights:** Documented in key events.")
    summary.append("- **Memorable Moments/Quotes:** Pull direct quotes during review pass.")
    summary.append("- **Session Rating:** 8/10 — Strong narrative momentum.")
    summary.append("")
    summary.append("## 🕰️ Session Timeline")
    summary.append("")
    for ev in events[:10]:
        summary.append(f"- {ev['text']}")

    linked = linkify_text("\n".join(summary), resolver)
    return linked.rstrip() + "\n"


def upsert_managed_block(existing: str, managed_block: str) -> str:
    pattern = re.compile(
        re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END),
        re.DOTALL,
    )
    replacement = f"{MANAGED_START}\n{managed_block.rstrip()}\n{MANAGED_END}"
    if pattern.search(existing):
        return pattern.sub(replacement, existing)

    stripped = existing.rstrip()
    if stripped:
        return stripped + "\n\n" + replacement + "\n"
    return replacement + "\n"


def extract_managed_block(existing: str) -> Optional[str]:
    match = re.search(
        re.escape(MANAGED_START) + r"\n?(.*?)\n?" + re.escape(MANAGED_END),
        existing,
        re.DOTALL,
    )
    if not match:
        return None
    return match.group(1).strip()


def world_timeline_lines(canonical: str, analysis: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for ev in analysis.get("events", [])[:8]:
        text = ev.get("text", "")
        if item_in_text(canonical, text):
            lines.append(f"- {text}")
    if not lines:
        lines.append("- Mentioned in this session.")
    return lines


def merge_world_managed_block(
    existing_text: str,
    generated_block: str,
    session: SessionRef,
    canonical: str,
    analysis: Dict[str, Any],
) -> str:
    existing_block = extract_managed_block(existing_text)
    if existing_block is None:
        return generated_block

    merged = existing_block
    summary_ref = f"[[Sessions/Summaries/{summary_stem(session)}|Session {session.session_number:03d}]]"
    merged = re.sub(
        r"^- Last Updated Session:.*$",
        f"- Last Updated Session: {summary_ref}",
        merged,
        count=1,
        flags=re.MULTILINE,
    )

    session_heading = f"### {summary_ref}"
    if session_heading in merged:
        return merged.strip()

    entry_lines = [session_heading, *world_timeline_lines(canonical, analysis)]
    entry = "\n".join(entry_lines)

    timeline_pattern = re.compile(r"(## 🕰️ Session Timeline\s*\n)(.*?)(?=\n## |\Z)", re.DOTALL)
    match = timeline_pattern.search(merged)
    if match:
        body = match.group(2).strip()
        replacement_body = f"{body}\n\n{entry}\n" if body else f"{entry}\n"
        merged = timeline_pattern.sub(match.group(1) + replacement_body, merged, count=1)
        return merged.strip()

    return (merged.rstrip() + f"\n\n## 🕰️ Session Timeline\n\n{entry}\n").strip()


def parse_frontmatter_keywords(text: str) -> List[str]:
    match = re.match(r"\A---\n(.*?)\n---\n?", text, re.DOTALL)
    if not match:
        return []

    lines = match.group(1).splitlines()
    raw_keywords: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not re.match(r"^keywords:\s*", line):
            i += 1
            continue

        inline = line.split(":", 1)[1].strip()
        if inline.startswith("[") and inline.endswith("]"):
            inside = inline[1:-1].strip()
            if inside:
                for part in inside.split(","):
                    raw_keywords.append(part.strip().strip("'\""))
            break

        i += 1
        while i < len(lines) and re.match(r"^\s*-\s+", lines[i]):
            raw_keywords.append(re.sub(r"^\s*-\s+", "", lines[i]).strip().strip("'\""))
            i += 1
        break

    out = []
    for keyword in raw_keywords:
        normalized = normalize_keyword(keyword)
        if normalized:
            out.append(normalized)
    return dedupe_preserve(out)


def set_frontmatter_keywords(text: str, keywords: List[str]) -> str:
    normalized = dedupe_preserve(
        [kw for kw in [normalize_keyword(k) for k in keywords] if kw]
    )
    keyword_lines = ["keywords: []"] if not normalized else ["keywords:", *[f"  - {kw}" for kw in normalized]]

    match = re.match(r"\A---\n(.*?)\n---\n?", text, re.DOTALL)
    if not match:
        frontmatter = "\n".join(keyword_lines)
        return f"---\n{frontmatter}\n---\n{text.lstrip()}"

    frontmatter_lines = match.group(1).splitlines()
    rebuilt: List[str] = []
    i = 0
    replaced = False
    while i < len(frontmatter_lines):
        line = frontmatter_lines[i]
        if re.match(r"^keywords:\s*", line):
            rebuilt.extend(keyword_lines)
            replaced = True
            i += 1
            while i < len(frontmatter_lines) and re.match(r"^\s*-\s+", frontmatter_lines[i]):
                i += 1
            continue
        rebuilt.append(line)
        i += 1

    if not replaced:
        rebuilt.extend(keyword_lines)

    body = text[match.end() :]
    rebuilt_frontmatter = "\n".join(rebuilt).rstrip()
    return f"---\n{rebuilt_frontmatter}\n---\n{body.lstrip()}"


def render_quest(session: SessionRef, quest: Dict[str, Any], resolver: Dict[str, Any]) -> str:
    title = normalize_space(quest.get("title") or title_case_slug(quest["key"]))
    desc = quest["description"]
    keywords = quest.get("keywords", [])
    base = seed_template(
        TEMPLATES_DIR / "quest-template.md",
        {
            "{{Quest Name}}": title,
            "{{Alias 1}}": title,
            "{{not_started|active|blocked|completed|failed|abandoned}}": "active",
            "{{low|medium|high|critical}}": "medium",
        },
    )

    managed = []
    managed.append("## 🎯 Objective")
    managed.append(f"- {desc}")
    managed.append("")
    managed.append("## 👤 Owner")
    managed.append("- shared")
    managed.append("")
    managed.append("## 📌 Current Status")
    managed.append("- Active")
    managed.append("- **Blockers:** Pending verification")
    managed.append("")
    managed.append("## 🧾 Clues & Evidence")
    managed.append("")
    managed.append("| Clue | Source | Confidence |")
    managed.append("|---|---|---|")
    managed.append(
        f"| {desc} | [[Sessions/Summaries/{summary_stem(session)}|Session {session.session_number:03d}]] | medium |"
    )
    managed.append("")
    managed.append("## ✅ Action Plan (Next Steps)")
    managed.append("1. Verify latest clue chain")
    managed.append("2. Confirm stakeholders")
    managed.append("3. Track outcome next session")
    managed.append("")
    managed.append("## 🕰️ Session Timeline")
    managed.append("")
    managed.append(
        f"### [[Sessions/Summaries/{summary_stem(session)}|Session {session.session_number:03d}]]"
    )
    managed.append(f"- {desc}")

    body = base
    body = upsert_managed_block(body, "\n".join(managed))
    body = set_frontmatter_keywords(body, keywords)
    return linkify_text(body, resolver)


def update_quests(session: SessionRef, analysis: Dict[str, Any], resolver: Dict[str, Any]) -> List[str]:
    QUESTS_ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    QUESTS_COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
    quest_map = load_data(QUEST_MAP_PATH, {"schema_version": 1, "quests": {}})
    quests = quest_map.setdefault("quests", {})
    touched = []

    for quest in analysis.get("quests", []):
        key = quest["key"]
        title = normalize_space(quest.get("title") or title_case_slug(key))
        safe_title = re.sub(r'[\\/:*?"<>|]', "", title).strip() or title_case_slug(key)
        path_rel = quests.get(key, f"Quests/Active/{safe_title}.md")
        if isinstance(path_rel, str) and path_rel.startswith("Sessions/Quests/"):
            path_rel = f"Quests/Active/{Path(path_rel).name}"
        path = REPO_ROOT / path_rel
        content = render_quest(session, quest, resolver)
        new_keywords = quest.get("keywords", [])

        if path.exists():
            existing = read_text(path)
            existing_keywords = parse_frontmatter_keywords(existing)
            merged_keywords = dedupe_preserve(existing_keywords + new_keywords)
            managed_match = re.search(
                re.escape(MANAGED_START) + r"(.*?)" + re.escape(MANAGED_END),
                content,
                re.DOTALL,
            )
            managed = managed_match.group(1) if managed_match else ""
            merged = upsert_managed_block(existing, managed)
            final = linkify_text(merged, resolver)
            final = set_frontmatter_keywords(final, merged_keywords)
        else:
            final = content
            final = set_frontmatter_keywords(final, new_keywords)

        write_text(path, final)
        quests[key] = str(path.relative_to(REPO_ROOT))
        touched.append(str(path.relative_to(REPO_ROOT)))

    dump_data(QUEST_MAP_PATH, quest_map)
    return touched


def managed_world_block(
    session: SessionRef,
    entity: Dict[str, Any],
    analysis: Dict[str, Any],
) -> str:
    lines = []
    lines.append("## 🕰️ Session Timeline")
    lines.append("")
    lines.append(f"### [[Sessions/Summaries/{summary_stem(session)}|Session {session.session_number:03d}]]")
    lines.extend(world_timeline_lines(entity.get("canonical_title", ""), analysis))
    return "\n".join(lines)


def item_in_text(name: str, text: str) -> bool:
    return normalize_name(name) in normalize_name(text)


def seed_template(path: Path, replacements: Dict[str, str]) -> str:
    template = read_text(path)
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def base_world_replacements(entity_type: str, canonical: str) -> Dict[str, str]:
    common = {
        "{{Alias 1}}": canonical,
        "{{Alias 2}}": canonical,
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


def update_world(session: SessionRef, analysis: Dict[str, Any], resolver: Dict[str, Any]) -> List[str]:
    touched = []
    by_canonical: Dict[str, Dict[str, Any]] = {}

    for entity in analysis.get("entities", []):
        canonical = entity.get("canonical_title")
        if not canonical:
            continue
        by_canonical[canonical] = entity

    for canonical, entity in by_canonical.items():
        entity_type = entity.get("entity_type", "unknown")
        if entity_type not in WORLD_TYPE_DIR:
            continue
        folder = WORLD_TYPE_DIR[entity_type]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{canonical}.md"
        managed = managed_world_block(
            session,
            {"canonical_title": canonical},
            analysis,
        )

        if path.exists():
            existing = read_text(path)
            merged_managed = merge_world_managed_block(existing, managed, session, canonical, analysis)
            merged = upsert_managed_block(existing, merged_managed)
            final = linkify_text(merged, resolver)
        else:
            template_path = WORLD_TEMPLATE[entity_type]
            base = seed_template(template_path, base_world_replacements(entity_type, canonical))
            merged = upsert_managed_block(base, managed)
            final = linkify_text(merged, resolver)

        write_text(path, final)
        touched.append(str(path.relative_to(REPO_ROOT)))

    return touched


def update_next_session_previously(session: SessionRef) -> Optional[str]:
    sessions = discover_sessions()
    next_candidates = [s for s in sessions if s.session_number == session.session_number + 1]
    if not next_candidates:
        return None
    next_session = sorted(next_candidates, key=lambda s: (s.date, s.filename))[0]
    path = next_session.path
    text = read_text(path)

    heading_pattern = re.compile(r"^(#{1,6})\s*Previously\b.*$", re.IGNORECASE | re.MULTILINE)
    summary_embed = f"![[{summary_stem(session)}#🎲 Summary]]"

    match = heading_pattern.search(text)
    if not match:
        injected = f"## Previously\n\n{summary_embed}\n\n" + text
        write_text(path, injected)
        return str(path.relative_to(REPO_ROOT))

    start = match.end()
    next_heading = re.search(r"^#{1,6}\s+", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    section = text[start:end]

    link_match = re.search(r"!?\[\[[^\]]*Session[^\]]*\]\]", section)
    if link_match:
        replacement = summary_embed
        new_section = section[: link_match.start()] + replacement + section[link_match.end() :]
        updated = text[:start] + new_section + text[end:]
        write_text(path, updated)
        return str(path.relative_to(REPO_ROOT))

    return None


def resolve_lint_paths(path_args: List[str]) -> List[Path]:
    if not path_args:
        roots = [SUMMARIES_DIR, QUESTS_ACTIVE_DIR, QUESTS_COMPLETED_DIR, *WORLD_TYPE_DIR.values()]
        files: List[Path] = []
        for root in roots:
            if root.exists():
                files.extend(sorted(root.rglob("*.md")))
        return files

    files: List[Path] = []
    for arg in path_args:
        target = (REPO_ROOT / arg).resolve() if not Path(arg).is_absolute() else Path(arg)
        if target.is_dir():
            files.extend(sorted(target.rglob("*.md")))
        elif target.suffix.lower() == ".md":
            files.append(target)
    return files


def yaml_candidates_for_conversion() -> List[Path]:
    candidates = [
        RESOLVER_PATH,
        TRIAGE_DECISIONS_PATH,
        QUEST_MAP_PATH,
        QUEST_SIGNALS_PATH,
        QUEST_DECISIONS_PATH,
    ]
    if META_SESSIONS_DIR.exists():
        candidates.extend(sorted(META_SESSIONS_DIR.rglob("*.yaml")))
    candidates.extend(sorted(SUMMARIES_DIR.glob("*.yaml")))
    candidates.extend(sorted(SUMMARIES_DIR.glob(".*.yaml")))
    return dedupe_path_list(candidates)


def dedupe_path_list(paths: List[Path]) -> List[Path]:
    out: List[Path] = []
    seen = set()
    for p in paths:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def command_analyze(args: argparse.Namespace) -> int:
    session = select_session(args.session)
    ensure_quest_signal_model()
    analysis, world_data = load_analysis_or_stage1(
        session, args.context_window, refresh=True
    )
    triage_state = world_triage_state(world_data)
    events_path = events_path_for(session)
    world_path = world_path_for(session)

    lines = [
        "## Stage Outcome",
        "",
        "- Stage: analyze",
        "- Source: dnd-session-analyze Stage 1 artifacts",
        f"- Events Source: `{events_path.relative_to(REPO_ROOT)}`",
        f"- World Source: `{world_path.relative_to(REPO_ROOT)}`",
        f"- Events: {analysis['quality']['events_count']}",
        f"- Mentions: {analysis['quality']['mentions_count']}",
        f"- Triage Candidates: {analysis['quality']['triage_candidates']}",
        f"- Triage Open Items: {triage_state['open_count']}",
        f"- Triage Blocking Items: {triage_state['blocking_count']}",
        f"- Quest Candidates: {analysis['quality']['quest_candidates']}",
        f"- Quests Selected: {analysis['quality']['quests_selected']}",
    ]
    write_run_report(session, "Session Processing Report", lines)

    print(f"Stage 1 artifacts verified for Session {session.session_number:02d}")
    return 0


def command_triage(args: argparse.Namespace) -> int:
    session = select_session(args.session)
    world_data = load_data(world_path_for(session), None)
    if not isinstance(world_data, dict):
        raise PipelineError(
            f"Missing world artifact for triage: `{world_path_for(session).relative_to(REPO_ROOT)}`"
        )
    outcome = world_triage_state(world_data)
    lines = [
        "## Stage Outcome",
        "",
        "- Stage: triage",
        f"- Open Items: {outcome['open_count']}",
        f"- Blocking Open Items: {outcome['blocking_count']}",
        f"- Resolved Items: {outcome['resolved_count']}",
    ]
    if outcome["open_count"] > 0:
        lines.append(
            "- Action: resolve remaining triage interactively in `$dnd-session-analyze` (world.yaml loop)"
        )
    write_run_report(session, "Session Processing Report", lines)
    if outcome["open_count"] > 0:
        print("Open triage items remain in world.yaml. Resolve them in dnd-session-analyze.")
        return 2
    return 0


def refresh_selected_quests(session: SessionRef, analysis: Dict[str, Any]) -> Dict[str, Any]:
    quest_model = ensure_quest_signal_model()
    quest_decisions = load_quest_decisions()
    candidates = analysis.get("quest_candidates")
    if not isinstance(candidates, list):
        candidates = analysis.get("quests", []) or []
    selected = select_quests_from_candidates(session, candidates, quest_model, quest_decisions)
    analysis["quest_candidates"] = candidates
    analysis["quests"] = selected
    analysis.setdefault("quality", {})
    analysis["quality"]["quest_candidates"] = len(candidates)
    analysis["quality"]["quests_selected"] = len(selected)
    return analysis


def command_quest_review(args: argparse.Namespace) -> int:
    session = select_session(args.session)
    analysis, _ = load_analysis_or_stage1(session, args.context_window, refresh=False)

    outcome = run_interactive_quest_review(session, analysis)
    updated = refresh_selected_quests(session, analysis)

    lines = [
        "## Stage Outcome",
        "",
        "- Stage: quest-review",
        f"- Events Source: `{events_path_for(session).relative_to(REPO_ROOT)}`",
        f"- Accepted: {outcome['accepted']}",
        f"- Rejected: {outcome['rejected']}",
        f"- Deferred: {outcome['deferred']}",
        f"- Pending: {outcome['pending']}",
        f"- Quests Selected: {len(updated.get('quests', []))}",
    ]
    write_run_report(session, "Session Processing Report", lines)
    if outcome["pending"] > 0:
        return 2
    return 0


def command_summarize_quests(args: argparse.Namespace) -> int:
    session = select_session(args.session)
    analysis, world_data = load_analysis_or_stage1(session, args.context_window, refresh=False)

    quest_review_outcome = run_interactive_quest_review(session, analysis)
    if quest_review_outcome["pending"] > 0:
        raise PipelineError(
            "Quest review gate: pending quest candidates remain unresolved. Run `quest-review` before summarize-quests."
        )

    analysis = refresh_selected_quests(session, analysis)

    triage_state = world_triage_state(world_data)
    if triage_state["open_count"] > 0:
        raise PipelineError(
            "Risk gate: open triage items remain in world.yaml. Resolve triage in `$dnd-session-analyze`."
        )

    ensure_summary_quality(analysis)
    resolver = ensure_resolver_defaults()

    summary_path = SUMMARIES_DIR / summary_filename(session)
    summary_text = generate_summary(session, analysis, resolver)
    write_text(summary_path, summary_text)

    quest_touched = update_quests(session, analysis, resolver)
    next_note = update_next_session_previously(session)
    lint_targets = [summary_path, *(REPO_ROOT / q for q in quest_touched)]
    if next_note:
        lint_targets.append(REPO_ROOT / next_note)
    lint_result = lint_files(lint_targets)
    lint_report_path = write_lint_report(
        lint_result, session_meta_dir(session) / "markdown-lint-report.md"
    )

    lines = [
        "## Stage Outcome",
        "",
        "- Stage: summarize-quests",
        f"- Summary: `{summary_path.relative_to(REPO_ROOT)}`",
        f"- Quest Files Updated: {len(quest_touched)}",
        f"- Markdown Lint Errors: {len(lint_result['errors'])}",
        f"- Markdown Lint Warnings: {len(lint_result['warnings'])}",
        f"- Markdown Lint Report: `{lint_report_path.relative_to(REPO_ROOT)}`",
    ]
    for q in quest_touched:
        lines.append(f"  - `{q}`")
    if next_note:
        lines.append(f"- Updated Next Session Previously Link: `{next_note}`")
    else:
        lines.append("- Updated Next Session Previously Link: none")
    write_run_report(session, "Session Processing Report", lines)

    print(f"Wrote summary: {summary_path}")
    return 0


def command_world_update(args: argparse.Namespace) -> int:
    session = select_session(args.session)
    analysis, world_data = load_analysis_or_stage1(session, args.context_window, refresh=False)

    triage_state = world_triage_state(world_data)
    if triage_state["open_count"] > 0:
        raise PipelineError(
            "Risk gate: open triage items remain in world.yaml. Resolve triage in `$dnd-session-analyze`."
        )

    resolver = ensure_resolver_defaults()
    touched = update_world(session, analysis, resolver)
    lint_targets = [REPO_ROOT / item for item in touched]
    lint_result = lint_files(lint_targets)
    lint_report_path = write_lint_report(
        lint_result, session_meta_dir(session) / "markdown-lint-report.md"
    )

    lines = [
        "## Stage Outcome",
        "",
        "- Stage: world-update",
        f"- World Files Updated: {len(touched)}",
        f"- Markdown Lint Errors: {len(lint_result['errors'])}",
        f"- Markdown Lint Warnings: {len(lint_result['warnings'])}",
        f"- Markdown Lint Report: `{lint_report_path.relative_to(REPO_ROOT)}`",
    ]
    for item in touched:
        lines.append(f"  - `{item}`")
    write_run_report(session, "Session Processing Report", lines)

    print(f"Updated world files: {len(touched)}")
    return 0


def command_run_all(args: argparse.Namespace) -> int:
    session = select_session(args.session)

    statuses = []

    ensure_resolver_defaults()
    ensure_quest_signal_model()
    analysis, world_data = load_analysis_or_stage1(
        session, args.context_window, refresh=True
    )
    quest_review_outcome = run_interactive_quest_review(session, analysis)
    analysis = refresh_selected_quests(session, analysis)
    statuses.append("- analyze: consumed Stage 1 artifacts")
    statuses.append(f"- analyze: events_source=`{events_path_for(session).relative_to(REPO_ROOT)}`")
    statuses.append(f"- analyze: world_source=`{world_path_for(session).relative_to(REPO_ROOT)}`")
    statuses.append(
        f"- quest-review: accepted={quest_review_outcome['accepted']}, rejected={quest_review_outcome['rejected']}, deferred={quest_review_outcome['deferred']}, pending={quest_review_outcome['pending']}"
    )
    if quest_review_outcome["pending"] > 0:
        statuses.append("- pause: quest review gate active; resolve pending quest candidates before downstream stages")
        write_run_report(session, "Session Processing Report", ["## Pipeline Outcome", "", *statuses])
        return 2

    triage_outcome = world_triage_state(world_data)
    statuses.append(
        f"- triage: open={triage_outcome['open_count']}, blocking_open={triage_outcome['blocking_count']}, resolved={triage_outcome['resolved_count']}"
    )

    if triage_outcome["open_count"] > 0:
        statuses.append("- pause: open triage items remain in world.yaml; downstream stages skipped")
        write_run_report(session, "Session Processing Report", ["## Pipeline Outcome", "", *statuses])
        return 2

    ensure_summary_quality(analysis)
    resolver = ensure_resolver_defaults()
    summary_path = SUMMARIES_DIR / summary_filename(session)
    summary_text = generate_summary(session, analysis, resolver)
    write_text(summary_path, summary_text)
    quest_touched = update_quests(session, analysis, resolver)
    next_note = update_next_session_previously(session)
    statuses.append(f"- summarize-quests: wrote `{summary_path.relative_to(REPO_ROOT)}`")
    statuses.append(f"- summarize-quests: quest_files={len(quest_touched)}")
    if next_note:
        statuses.append(f"- summarize-quests: updated_next_previously=`{next_note}`")

    world_touched = update_world(session, analysis, resolver)
    statuses.append(f"- world-update: world_files={len(world_touched)}")

    lint_targets = [summary_path, *(REPO_ROOT / q for q in quest_touched), *(REPO_ROOT / w for w in world_touched)]
    if next_note:
        lint_targets.append(REPO_ROOT / next_note)
    lint_result = lint_files(lint_targets)
    lint_report_path = write_lint_report(
        lint_result, session_meta_dir(session) / "markdown-lint-report.md"
    )
    statuses.append(
        f"- markdown-lint: errors={len(lint_result['errors'])}, warnings={len(lint_result['warnings'])}"
    )

    report_lines = ["## Pipeline Outcome", "", *statuses, "", "## Changed Files"]
    report_lines.append(f"- `{summary_path.relative_to(REPO_ROOT)}`")
    for path in quest_touched:
        report_lines.append(f"- `{path}`")
    for path in world_touched:
        report_lines.append(f"- `{path}`")
    if next_note:
        report_lines.append(f"- `{next_note}`")
    report_lines.append(f"- `{lint_report_path.relative_to(REPO_ROOT)}`")
    write_run_report(session, "Session Processing Report", report_lines)

    print(f"Pipeline complete for Session {session.session_number:02d}")
    return 0


def command_lint_markdown(args: argparse.Namespace) -> int:
    targets = resolve_lint_paths(args.paths or [])
    result = lint_files(targets)
    report_path = write_lint_report(result, LINT_REPORT_PATH)
    print(
        f"Markdown lint checked={result['checked_files']} errors={len(result['errors'])} warnings={len(result['warnings'])}"
    )
    print(f"Report: {report_path}")
    return 1 if result["errors"] else 0


def command_convert_yaml(args: argparse.Namespace) -> int:
    migrate_metadata_layout()
    converted = 0
    skipped = 0
    for path in yaml_candidates_for_conversion():
        if not path.exists():
            continue
        if convert_yaml_file(path):
            converted += 1
        else:
            skipped += 1
    print(f"YAML conversion complete: converted={converted} skipped={skipped}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="D&D vault skill pipeline")
    sub = p.add_subparsers(dest="command", required=True)

    for cmd in ["analyze", "triage", "quest-review", "summarize-quests", "world-update", "run-all"]:
        sp = sub.add_parser(cmd)
        sp.add_argument("--session", default="latest session")
        sp.add_argument("--context-window", type=int, default=4)
        sp.add_argument("--dry-run", action="store_true")

    lint = sub.add_parser("lint-markdown")
    lint.add_argument("paths", nargs="*")
    lint.add_argument("--dry-run", action="store_true")

    convert = sub.add_parser("convert-yaml")
    convert.add_argument("--dry-run", action="store_true")

    return p


def main() -> int:
    global DRY_RUN
    args = parser().parse_args()
    os.chdir(REPO_ROOT)
    DRY_RUN = bool(args.dry_run)
    migrate_metadata_layout()

    try:
        if args.command == "analyze":
            return command_analyze(args)
        if args.command == "triage":
            return command_triage(args)
        if args.command == "quest-review":
            return command_quest_review(args)
        if args.command == "summarize-quests":
            return command_summarize_quests(args)
        if args.command == "world-update":
            return command_world_update(args)
        if args.command == "run-all":
            return command_run_all(args)
        if args.command == "lint-markdown":
            return command_lint_markdown(args)
        if args.command == "convert-yaml":
            return command_convert_yaml(args)
    except PipelineError as exc:
        print(f"ERROR: {exc}")
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
