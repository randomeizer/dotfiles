#!/usr/bin/env bash
set -euo pipefail

# Expose the repo-managed skills through the shared agent discovery directory.
SOURCE="$HOME/.config/agents/skills"
TARGET="$HOME/.agents/skills"
[[ -d "$SOURCE" ]] || exit 0
mkdir -p "$TARGET"

for subfolder in "$SOURCE"/*; do
  [[ -d "$subfolder" ]] || continue
  target_link="$TARGET/$(basename "$subfolder")"
  if [[ -L "$target_link" ]]; then
    [[ "$(readlink "$target_link")" == "$subfolder" ]] && continue
    rm "$target_link"
  elif [[ -e "$target_link" ]]; then
    continue
  fi
  ln -s "$subfolder" "$target_link"
done
