#!/usr/bin/env bash
set -euo pipefail

# Dry-run script to validate stow symlinks for this dotfiles repo.
# Usage: ./scripts/test-stow.sh

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

if ! command -v stow >/dev/null 2>&1; then
  echo "ERROR: 'stow' not found in PATH. Install GNU Stow (brew install stow) and retry." >&2
  exit 2
fi

TARGET="$HOME"

packages=(
  starship
  zshrc
  nushell
  bashrc
  fish
  tmux
  wezterm
  sketchybar
)

found=()
for p in "${packages[@]}"; do
  if [ -d "$p" ]; then
    echo "-- dry-run: stow -n -t $TARGET $p"
    stow -n -v -t "$TARGET" "$p" || true
    found+=("$p")
  fi
done

if [ ${#found[@]} -eq 0 ]; then
  echo "No stowable packages found in repo root. Nothing to test." >&2
  exit 1
fi

echo
echo "Dry-run complete for: ${found[*]}"
echo "If the output looks correct, run: stow -t $TARGET ${found[*]}"

exit 0
