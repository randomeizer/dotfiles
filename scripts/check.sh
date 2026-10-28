#!/usr/bin/env bash
# Validate repository files without installing into the user's home.
set -u
require_tests=false
case "${1:-}" in
  '') ;;
  --require-tests) require_tests=true; shift ;;
  *) printf 'Usage: bash scripts/check.sh [--require-tests]\n' >&2; exit 2 ;;
esac
if (( $# )); then
  printf 'Usage: bash scripts/check.sh [--require-tests]\n' >&2
  exit 2
fi
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$repo_dir" || exit 1
missing=()
for tool in git bash zsh stow nu pwsh luac; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if (( ${#missing[@]} )); then
  printf 'Missing required tools: %s\n' "${missing[*]}" >&2
  exit 1
fi
file_list="$(mktemp "${TMPDIR:-/tmp}/dotfiles-check.XXXXXX")" || exit 1
trap 'rm -f "$file_list"' EXIT
git ls-files -z --cached --others --exclude-standard > "$file_list" || exit 1
failures=0
while IFS= read -r -d '' file; do
  [[ -f "$file" && ! -L "$file" ]] || continue
  case "$file" in
    *.sh) label='Bash syntax'; command=(bash -n "$file") ;;
    *.zsh|*/.zshrc) label='Zsh syntax'; command=(zsh -n "$file") ;;
    *.lua) label='Lua syntax'; command=(luac -p "$file") ;;
    *.json) label='JSON parsing'; command=(nu --no-config-file -c 'open --raw $env.DOTFILES_CHECK_FILE | from json | ignore') ;;
    *.toml) label='TOML parsing'; command=(nu --no-config-file -c 'open --raw $env.DOTFILES_CHECK_FILE | from toml | ignore') ;;
    *.nu) label='Nushell syntax'; command=(nu --no-config-file -c 'if (nu-check $env.DOTFILES_CHECK_FILE) { exit 0 } else { exit 1 }') ;;
    *.ps1) label='PowerShell syntax'; command=(pwsh -NoLogo -NoProfile -NonInteractive -Command '$t=$null; $e=$null; [System.Management.Automation.Language.Parser]::ParseFile($env:DOTFILES_CHECK_FILE,[ref]$t,[ref]$e) > $null; if ($e.Count) { $e | Out-String | Write-Error; exit 1 }') ;;
    *) continue ;;
  esac
  if ! DOTFILES_CHECK_FILE="$repo_dir/$file" "${command[@]}"; then
    printf 'FAIL %s: %s\n' "$label" "$file" >&2
    failures=$((failures + 1))
  fi
done < "$file_list"
if command -v python3 >/dev/null 2>&1; then
  printf 'Running behavioral tests (Python)\n'
  if ! PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'; then
    failures=$((failures + 1))
  fi
elif "$require_tests"; then
  printf 'Python 3 is required for the behavioral tests.\n' >&2
  failures=$((failures + 1))
else
  printf 'Behavioral tests skipped: Python 3 not available.\n' >&2
fi
if (( failures )); then
  printf 'Checks failed: %s\n' "$failures" >&2
  exit 1
fi
printf 'Available checks passed.\n'
