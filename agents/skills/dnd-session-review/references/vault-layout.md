# Shared D&D skills

These eight skills, including `dnd-session-setup`, are installed together. Use their installed absolute paths for scripts and bundled resources; campaign files are relative to the target vault.

Set `SKILLS_ROOT` to the directory containing the installed `dnd-session-*` folders, as determined from the loaded `SKILL.md` path. For example, when a skill is loaded from `/shared/skills/dnd-session-review/SKILL.md`, set `SKILLS_ROOT=/shared/skills`.

Run commands with the working directory inside the intended vault. Scripts walk upwards from the working directory to find `Sessions/Notes`. To target a different vault, set `DND_VAULT_ROOT` to its path. An invalid explicit path fails; scripts never fall back to another vault or infer campaign data from the installation directory.

## Vault contract

- `Sessions/Notes/` contains canonical notes named `YYYY-MM-DD - Session NN.md`.
- `Sessions/Summaries/`, `Quests/Active/`, `Quests/Completed/`, and `World/{Characters,Locations,Factions,Items,Creatures}/` are output locations.
- `.dnd-meta/` contains campaign-specific metadata and per-session artifacts. It stays in the vault.
- `Templates/` contains that campaign's summary, quest, and world templates. Keep its headings and viewpoint conventions; do not import another campaign's characters or setting. When templates are missing, use `dnd-session-setup` before generating downstream outputs. Missing Stage 1 artifacts still require the analysis stage.
- Follow the target vault's `AGENTS.md`. Source notes are immutable except for expressly allowed next-session `Previously` updates. Use `Now` as primary scope, preserve manual prose, resolve blocking triage before downstream work, and use canonical Obsidian wikilinks.
- Scripts require Python 3 and Ruby with its standard YAML/JSON libraries. No extra Python packages are required by the workflow scripts.

Bundled `resources/*.yaml` files are schema examples. Their sample names and dates are illustrative; author all artifacts from the current vault's evidence.

## Shared templates and setup

The seven reusable defaults live in [dnd-session-setup/assets/templates](../../dnd-session-setup/assets/templates). The world templates describe entity structure without named campaign lore. The default summary uses `## 🎯 Player Lens` and reads the character identity from campaign settings; the quest owner choices contain no named player character.

`dnd-session-review` checks templates and the player's character before analysis. If either is missing, [dnd-session-setup](../../dnd-session-setup/SKILL.md) reuses established preferences or asks which character the user plays. Its helper saves `player_character` and copies only missing templates into the vault, leaving existing templates intact. The setup check recognizes required frontmatter, key headings, and managed/manual section boundaries; placeholders inside template sources are expected.

Campaign copies can refine narrative prompts and add sections while retaining the headings and fields required by the current scripts. The workflow assumes an Obsidian Markdown vault with the directory contract above; setup does not convert arbitrary folder structures or other note formats.

## Optional campaign settings

`.dnd-meta/skill-config.json` is a vault-local JSON object. The review requires a player character; the remaining settings default to empty lists/maps. Shared code contains no campaign seed roster or mandatory named entity remapping.

Supported keys:

- `resolver_seeds`: entity records with `canonical_title`, `entity_type`, and optional `true_aliases`, `observed_variants`, `last_seen_session`, `confidence_notes`.
- `party_members`: canonical character names for party-role classification.
- `summary_party`: canonical names for the legacy backend's party list; defaults to `party_members`.
- `player_character`: canonical name of the user's player character. Both model-authored summaries and the legacy summary backend use this for Player Lens and the summary's player-character link. For example: `{"player_character": "Canonical Character Name"}`.
- `focus_character`: legacy compatibility key. A non-Party value is accepted when `player_character` is absent; `init` migrates it to the preferred key.
- `forced_entity_types`: normalized lowercase canonical names mapped to `character`, `location`, `faction`, `item`, or `creature`. Configure only evidence-backed campaign overrides.

Existing `.dnd-meta/entity-resolver.yaml` remains the campaign's canonical resolver. Do not copy campaign metadata or templates into the shared installation.
