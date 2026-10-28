#!/usr/bin/env bash
set -euo pipefail

SOURCE="$HOME/.config/scripts/azt"
TARGET_DIR="$HOME/.local/bin"
TARGET="$TARGET_DIR/azt"

if [[ ! -x "$SOURCE" ]]; then
  exit 0
fi

mkdir -p "$TARGET_DIR"

if [[ -L "$TARGET" ]]; then
  current_target="$(readlink "$TARGET")"
  if [[ "$current_target" == "$SOURCE" ]]; then
    exit 0
  fi
  printf 'config-sync: preserved conflicting path: %s\n' "$TARGET" >&2
  exit 1
elif [[ -e "$TARGET" ]]; then
  printf 'config-sync: preserved conflicting path: %s\n' "$TARGET" >&2
  exit 1
fi

ln -s "$SOURCE" "$TARGET"
