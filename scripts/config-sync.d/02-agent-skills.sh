#!/usr/bin/env bash
set -euo pipefail

script_path="${BASH_SOURCE[0]}"
while [[ -L "$script_path" ]]; do
  link_dir="$(cd "$(dirname "$script_path")" && pwd -P)"
  link_target="$(readlink "$script_path")"
  if [[ "$link_target" == /* ]]; then script_path="$link_target"
  else script_path="$link_dir/$link_target"; fi
done
script_dir="$(cd "$(dirname "$script_path")" && pwd -P)"
source "$script_dir/../lib/skill-sync.sh"
sync_skill_links "$HOME/.config/agents/skills" "$HOME/.agents/skills"
