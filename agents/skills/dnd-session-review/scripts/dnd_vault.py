"""Locate campaign data independently of the shared skill installation."""

import json
import os
from pathlib import Path


def find_vault_root() -> Path:
    explicit = os.environ.get("DND_VAULT_ROOT")
    start = Path(explicit).expanduser().resolve() if explicit else Path.cwd().resolve()
    candidates = (start,) if explicit else (start, *start.parents)
    for candidate in candidates:
        if (candidate / "Sessions" / "Notes").is_dir():
            return candidate
    raise RuntimeError(
        "No D&D vault found. Run from a vault containing Sessions/Notes "
        "or set DND_VAULT_ROOT to its absolute path."
    )


def load_campaign_config(root: Path) -> dict:
    path = root / ".dnd-meta" / "skill-config.json"
    if not path.exists():
        return {}
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Campaign configuration must be an object: {path}")
    list_fields = ("resolver_seeds", "party_members", "summary_party")
    for field in list_fields:
        if field in config and not isinstance(config[field], list):
            raise ValueError(f"{field} must be a list: {path}")
    for field in ("party_members", "summary_party"):
        if any(not isinstance(value, str) for value in config.get(field, [])):
            raise ValueError(f"{field} must contain names: {path}")
    for seed in config.get("resolver_seeds", []):
        if not isinstance(seed, dict) or not isinstance(seed.get("canonical_title"), str):
            raise ValueError(f"resolver_seeds must contain canonical entity records: {path}")
        if not isinstance(seed.get("true_aliases", []), list):
            raise ValueError(f"Seed true_aliases must be a list: {path}")
    overrides = config.get("forced_entity_types", {})
    allowed = {"character", "location", "faction", "item", "creature"}
    if not isinstance(overrides, dict) or any(value not in allowed for value in overrides.values()):
        raise ValueError(f"forced_entity_types must map normalized names to entity types: {path}")
    if "focus_character" in config and not isinstance(config["focus_character"], str):
        raise ValueError(f"focus_character must be a name: {path}")
    if "player_character" in config:
        value = config["player_character"]
        if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value or value.strip() == "Party":
            raise ValueError(f"player_character must name the player's character: {path}")
    return config


def configured_player_character(config: dict):
    """Read the campaign setting, accepting older focus_character configurations."""
    value = config.get("player_character", config.get("focus_character"))
    if not value or value.strip() == "Party":
        return None
    return value.strip()
