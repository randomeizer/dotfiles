---
name: dnd-session-setup
description: Configure the player's character and check a D&D vault's seven required templates, creating missing ones from shared defaults. Use for campaign setup or when dnd-session-review finds missing settings or templates. Preserve existing templates and campaign data.
---

# DnD Session Setup

Prepare the template prerequisites for the shared session-review workflow. Shared defaults live in [assets/templates](assets/templates); generated campaign copies live in the target vault's `Templates/` directory.

## Inspect the Vault

Read [vault layout and execution](../dnd-session-review/references/vault-layout.md) and the target vault's `AGENTS.md`. Set `SKILLS_ROOT` from the installed skill location, and keep the working directory in the campaign vault. `DND_VAULT_ROOT` can explicitly select another vault.

Run this read-only check:

```bash
python3 "$SKILLS_ROOT/dnd-session-setup/scripts/dnd_session_setup.py" check
```

Exit 0 means templates and the player-character setting are ready; exit 1 reports missing settings or missing/incompatible templates. The check writes nothing. If ready, return immediately to the calling review without asking setup questions or changing existing templates.

Required files:

- `Templates/session-summary-template.md`
- `Templates/quest-template.md`
- `Templates/character-template.md`
- `Templates/location-template.md`
- `Templates/faction-template.md`
- `Templates/item-template.md`
- `Templates/creature-template.md`

## Work with the User

Report missing templates and whether the player's character is configured. Inspect existing templates, `.dnd-meta/skill-config.json` if present, and the user's stated preferences before asking for information.

If the player's character is not established, ask one concise question: which character do you play in this campaign? This applies even when all templates already exist. Use the canonical character title from this vault's resolver when the match is clear. Reuse a configured `player_character`, an older non-Party `focus_character`, or an answer already given in the conversation without asking again. Do not infer the player's character merely from note frequency, and do not substitute the whole party while awaiting an answer.

Use neutral defaults for missing templates unless the user requests specific changes. If the user requests customization, clarify only choices that materially change the result, such as an extra narrative section or different tone. Preserve the structural contract below. Do not ask for a campaign roster or setting lore just to install generic templates; add campaign facts only from the user's evidence or explicit instructions.

## Create Missing Templates

Save the player's character and create any missing templates:

```bash
python3 "$SKILLS_ROOT/dnd-session-setup/scripts/dnd_session_setup.py" init --player-character "Canonical Character Name"
```

If the character is already configured, reuse that setting:

```bash
python3 "$SKILLS_ROOT/dnd-session-setup/scripts/dnd_session_setup.py" init
```

The authoritative setting is `player_character` in `.dnd-meta/skill-config.json`. An explicit choice updates this field even when templates already exist, without editing those templates. Older `focus_character` settings are accepted for compatibility and migrated by `init`; unrelated config keys remain intact. The shared summary heading is always `## 🎯 Player Lens`; the character name belongs in campaign settings, not in the template heading or prose prompts.

The helper creates only missing files and never overwrites existing templates. It refuses initialization if existing templates are incompatible; resolve the reported issue within the user's edit scope before continuing. Never use wholesale replacement to repair a template. It does not create or change session notes, summaries, quests, world entities, resolver records, or triage decisions.

Apply any requested prompt or optional-section customizations only to the newly created templates. Preserve existing templates byte-for-byte unless the user requests edits to them.

## Structural Contract and Handoff

- Templates are Markdown source: `{{...}}` placeholders are intentional here. Generated summaries, quests, and world pages must fill or remove them using evidence, with uncertainty stated plainly.
- Keep frontmatter field names, machine enum values, emoji headings, and Obsidian wikilinks compatible with the existing scripts.
- Quest and world templates require one ordered `dnd-managed:start`/`dnd-managed:end` pair. Keep `## 📝 Notes` outside the managed block. World templates need `## 🌐 Overview` and `## 🕰️ Session Timeline`; quests need `## 🎯 Objective` and `## 🧵 Progress Log`.
- The summary keeps its timeline and key events. `## 🎯 Player Lens` interprets the configured player's character: personal stakes, character signals, and forward pressure. Fill `{{player_character}}` from campaign settings when writing a summary.
- Do not import campaign names or entity overrides from another vault. A missing player character requires a user answer before the review resumes.

Re-run `check` after configuration, creation, and any customizations. Report created files, preserved files, the configured player character, and validation result. If called by `$dnd-session-review`, continue directly with its original session selector after the check passes; setup does not replace the analysis/triage/summary/quest/world pipeline.
