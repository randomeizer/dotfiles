#!/usr/bin/env bash
set -euo pipefail

# Ensure ~/.copilot/skills/<subfolder> symlinks point to the repo-managed agents/skills subfolders
# Only run if copilot CLI is installed

if ! command -v copilot >/dev/null 2>&1; then
  exit 0
fi

SOURCE="$HOME/.config/agents/skills"
COPILOT_HOME="${COPILOT_HOME:-$HOME/.copilot}"
TARGET="$COPILOT_HOME/skills"

# Only act if the managed skills folder exists
if [[ ! -d "$SOURCE" ]]; then
  exit 0
fi

mkdir -p "$TARGET"

# Clean up dead symlinks (symlinks pointing to non-existent SOURCE subdirs)
for link in "$TARGET"/*; do
  if [[ -L "$link" ]]; then
    if [[ ! -d "$link" ]]; then
      rm "$link"
    fi
  fi
done

# Create symlinks for each subfolder in SOURCE
for subfolder in "$SOURCE"/*; do
  if [[ -d "$subfolder" ]]; then
    basename=$(basename "$subfolder")
    target_link="$TARGET/$basename"

    if [[ -L "$target_link" ]]; then
      # Already a symlink, verify it points to the right place
      dest=$(readlink "$target_link")
      [[ "$dest" == "$subfolder" ]] && continue
      rm "$target_link"
    elif [[ -e "$target_link" ]]; then
      # Something else exists here (file or dir), skip it to preserve existing content
      continue
    fi

    ln -s "$subfolder" "$target_link"
  fi
done
