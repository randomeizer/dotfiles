---
name: dnd-session-triage
description: Check triage gate status for a session based on world.yaml. Interactive one-by-one triage resolution is performed in dnd-session-analyze.
---

# DnD Session Triage

## Shared Installation and Vault Scope

Read [vault layout and execution](../dnd-session-review/references/vault-layout.md) before running this skill in a new project.
Set `SKILLS_ROOT` to the absolute parent directory of the installed `dnd-session-*` skill folders, using the loaded skill's location. Keep the working directory in the target campaign vault; the installed skill directory is never the vault.

Check triage status for unresolved/ambiguous entities.

## Steps

1. Resolve target session (`Session XX` or `latest session`).
2. Run:

```bash
python3 "$SKILLS_ROOT/dnd-session-review/scripts/dnd_session_review.py" triage --session "<selector>"
```

3. If open items are reported, return to `$dnd-session-analyze` and resolve triage interactively one-by-one in `world.yaml`.
4. Confirm run report in `.dnd-meta/sessions/YYYY-MM-DD-sNNN/run-report.md`.
5. If open items remain, stop downstream stages.
