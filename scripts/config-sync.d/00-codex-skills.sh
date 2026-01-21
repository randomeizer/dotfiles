#!/usr/bin/env bash
set -euo pipefail

# Ensure ~/.codex/skills symlink points to the repo-managed agents/skills folder
# Only run if codex CLI is installed

if ! command -v codex >/dev/null 2>&1; then
  exit 0
fi

SOURCE="$HOME/.config/agents/skills"
TARGET="$HOME/.codex/skills"

# Only act if the managed skills folder exists
if [[ ! -d "$SOURCE" ]]; then
  exit 0
fi

mkdir -p "$HOME/.codex"

if [[ -L "$TARGET" ]]; then
  dest=$(readlink "$TARGET")
  [[ "$dest" == "$SOURCE" ]] && exit 0
  rm "$TARGET"
elif [[ -e "$TARGET" ]]; then
  # Respect a user-created directory/file
  exit 0
fi

ln -s "$SOURCE" "$TARGET"
