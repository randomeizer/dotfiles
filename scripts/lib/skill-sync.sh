#!/usr/bin/env bash

# A link is managed only when its literal target is SOURCE/<link name>.
sync_skill_links() {
  local source="$1" target="$2" link name destination subfolder failed=0
  [[ -d "$source" ]] || return 0
  mkdir -p "$target"

  for link in "$target"/*; do
    [[ -L "$link" ]] || continue
    name="${link##*/}"
    destination="$(readlink "$link")"
    if [[ "$destination" == "$source/$name" && ! -d "$link" ]]; then
      rm -- "$link"
    fi
  done

  for subfolder in "$source"/*; do
    [[ -d "$subfolder" ]] || continue
    name="${subfolder##*/}"
    link="$target/$name"
    if [[ -L "$link" ]] && [[ "$(readlink "$link")" == "$subfolder" ]]; then
      continue
    elif [[ -e "$link" || -L "$link" ]]; then
      printf 'config-sync: preserved conflicting path: %s\n' "$link" >&2
      failed=1
      continue
    fi
    ln -s "$subfolder" "$link"
  done
  return "$failed"
}
