---
name: dnd-session-world-update
description: Upsert world entities (characters, locations, factions, items, creatures) from triaged session analysis using section-aware managed blocks while preserving non-managed manual prose.
---

# DnD Session World Update

## Shared Installation and Vault Scope

Read [vault layout and execution](../dnd-session-review/references/vault-layout.md) before running this skill in a new project.
Set `SKILLS_ROOT` to the absolute parent directory of the installed `dnd-session-*` skill folders, using the loaded skill's location. Keep the working directory in the target campaign vault; the installed skill directory is never the vault.

Run Stage 3 world updates.

## Steps

1. Ensure analysis exists and blocking triage items are resolved.
2. Scaffold files from templates (missing files only):

```bash
python3 "$SKILLS_ROOT/dnd-session-world-update/scripts/dnd_session_world_update.py" prepare --session "<selector>"
```

Optional category-scoped scaffold:

```bash
python3 "$SKILLS_ROOT/dnd-session-world-update/scripts/dnd_session_world_update.py" prepare --session "<selector>" --category character
python3 "$SKILLS_ROOT/dnd-session-world-update/scripts/dnd_session_world_update.py" prepare --session "<selector>" --category location
```

3. Build narrative evidence brief for model-authored prose:

```bash
python3 "$SKILLS_ROOT/dnd-session-world-update/scripts/dnd_session_world_update.py" build-brief --session "<selector>"
```

Optional category-scoped brief:

```bash
python3 "$SKILLS_ROOT/dnd-session-world-update/scripts/dnd_session_world_update.py" build-brief --session "<selector>" --category item
```

Brief output:
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/world-narrative-brief.yaml`

4. Run mandatory model-authored narrative pass for every in-scope entity (not only newly prepared files):

- This pass must be done by the model (agent-authored prose edits), not by `dnd_session_world_update.py`.
- Do not run `python3 ... dnd_session_world_update.py run` for narrative generation.
- This narrative pass is required even when `prepare` creates zero files.
- Process all resolved entities in the selected scope (`all` or the specified category), including pre-existing world files.
- For each in-scope entity file, update narrative sections from metadata + source evidence (`## 🌐 Overview`, descriptive bullets, motivations, relevance, risks, open questions).
- Keep claims evidence-backed and human-readable.
- For existing files, expand/replace placeholder/default text; preserve useful manual prose outside managed sections.
- Validate coverage explicitly: build the expected in-scope entity/file list from Stage 1 artifacts, then confirm each file received the narrative pass (none skipped).
- Use `world-narrative-brief.yaml` as canonical evidence input for prose decisions.

5. Run script structural pass (no prose overwrite):

```bash
python3 "$SKILLS_ROOT/dnd-session-world-update/scripts/dnd_session_world_update.py" run --session "<selector>" --structure-only
```

Optional category-scoped run:

```bash
python3 "$SKILLS_ROOT/dnd-session-world-update/scripts/dnd_session_world_update.py" run --session "<selector>" --category character --structure-only
python3 "$SKILLS_ROOT/dnd-session-world-update/scripts/dnd_session_world_update.py" run --session "<selector>" --category faction --structure-only
```

- Categories: `character`, `location`, `faction`, `item`, `creature` (`all` by default).
- `run` without `--structure-only` is intentionally blocked; narrative generation must be model-authored.
- Note: `item` runs can legitimately produce zero updates if no resolved item entities remain after canonical type remaps.

6. Verify updates only touch managed sections (`dnd-managed` markers) in:
- `World/Characters`
- `World/Locations`
- `World/Factions`
- `World/Items`
- `World/Creatures`

7. Verify template placeholder cleanup/population:
- Generated files should not retain `{{...}}` placeholders after model pass.
- Existing files keep manual prose; model-authored content is preserved by `--structure-only`.
- Do not add separate `Recent development` sub-paragraphs in `## 🌐 Overview`; integrate updates directly into the core overview paragraph.
- Character `## 🌐 Overview` should stay campaign-level (stable role, vibe, long-arc influence), not a session recap.
- Location `## 🌐 Overview` should be conditional:
- If location recurs across sessions, use broader campaign-level identity/relevance.
- If location is not yet recurring, use concrete fact-first wording from evidence (for example location type and relation like `city on [[Island]]`), and avoid generic placeholder prose.
- Apply only entity-type overrides explicitly configured in the target vault.

8. Preserve normalized template heading conventions (including emoji-prefixed `##` headings) when creating new world files.
 - For `item` entities, do not include a `## 🛠️ Managed Updates` section.

9. Confirm links are Obsidian wikilinks throughout managed content.
 - In Markdown tables, piped wikilinks must escape the pipe as `[[Target\|Label]]`.

10. Run structure lint (template conformance):

```bash
python3 "$SKILLS_ROOT/dnd-session-world-update/scripts/dnd_session_world_update.py" lint-structure World/Characters World/Locations World/Factions World/Items World/Creatures
```

11. Confirm markdown lint report:
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/markdown-lint-report.md`
