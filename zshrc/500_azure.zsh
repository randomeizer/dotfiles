# Azure tenant aliases and per-tenant Azure CLI profiles.

_azt_home() {
  printf '%s\n' "${AZT_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/azure-tenants}"
}

_azt_tenants_file() {
  printf '%s\n' "${AZT_TENANTS_FILE:-$(_azt_home)/tenants.tsv}"
}

_azt_profiles_dir() {
  printf '%s\n' "${AZT_PROFILES_DIR:-$(_azt_home)/profiles}"
}

_azt_profile_dir() {
  printf '%s/%s\n' "$(_azt_profiles_dir)" "$1"
}

_azt_usage() {
  cat <<'EOF'
Usage:
  azt add <alias> <tenant-id-or-domain>
  azt remove <alias>
  azt list
  azt id <alias>

  azt <alias>                 # show alias profile details
  azt <alias> login [az login args...]
  azt <alias> current
  azt <alias> subscriptions
  azt <alias> set <subscription-id-or-name>
  azt <alias> profile
  azt <alias> <az args...>

Compatibility forms:
  azt login <alias> [az login args...]
  azt current <alias>
  azt subscriptions <alias>

Examples:
  azt add qps 61c207dc-d4fe-40a3-8341-0f31daa4c62e
  azt qps login
  azt qps login --allow-no-subscriptions
  azt qps set SUB-PRD-VIMS
  azt qps group list
EOF
}

_azt_print_aliases() {
  local file name tenant_id
  file="$(_azt_tenants_file)"

  [[ -f "$file" ]] || return 0

  while IFS=$'\t' read -r name tenant_id; do
    [[ -z "$name" || "$name" == \#* ]] && continue
    printf '%s\n' "$name"
  done < "$file"
}

_azt_lookup() {
  local requested="$1"
  local file name tenant_id
  file="$(_azt_tenants_file)"

  [[ -f "$file" ]] || return 1

  while IFS=$'\t' read -r name tenant_id; do
    [[ -z "$name" || "$name" == \#* ]] && continue
    if [[ "$name" == "$requested" ]]; then
      printf '%s\n' "$tenant_id"
      return 0
    fi
  done < "$file"

  return 1
}

_azt_require_alias() {
  local name="$1"
  local tenant_id

  if tenant_id="$(_azt_lookup "$name")"; then
    printf '%s\n' "$tenant_id"
    return 0
  fi

  printf 'azt: unknown tenant alias: %s\n' "$name" >&2
  printf 'azt: run "azt list" to see configured aliases\n' >&2
  return 1
}

_azt_profile() {
  local name="$1"
  local tenant_id profile_dir

  tenant_id="$(_azt_require_alias "$name")" || return
  profile_dir="$(_azt_profile_dir "$name")"
  mkdir -p "$profile_dir"

  printf 'azt: alias: %s\n' "$name"
  printf 'azt: tenant: %s\n' "$tenant_id"
  printf 'azt: AZURE_CONFIG_DIR=%s\n' "$profile_dir"
}

_azt_az() {
  local name="$1"
  local tenant_id profile_dir

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt <alias> <az args...>\n' >&2
    return 2
  fi
  shift

  if [[ $# -eq 0 ]]; then
    printf 'azt: usage: azt <alias> <az args...>\n' >&2
    return 2
  fi

  tenant_id="$(_azt_require_alias "$name")" || return
  profile_dir="$(_azt_profile_dir "$name")"
  mkdir -p "$profile_dir"

  (
    export AZURE_CONFIG_DIR="$profile_dir"
    export AZT_ACTIVE_ALIAS="$name"
    export AZT_ACTIVE_TENANT_ID="$tenant_id"
    az "$@"
  )
}

_azt_add() {
  local name="$1"
  local tenant_id="$2"
  local file dir temp

  if [[ -z "$name" || -z "$tenant_id" ]]; then
    printf 'azt: usage: azt add <alias> <tenant-id-or-domain>\n' >&2
    return 2
  fi

  if [[ ! "$name" =~ '^[A-Za-z0-9][A-Za-z0-9._-]*$' ]]; then
    printf 'azt: aliases must start with a letter or number and contain only letters, numbers, dot, underscore, or hyphen\n' >&2
    return 2
  fi

  if [[ ! "$tenant_id" =~ '^[A-Za-z0-9._:-]+$' ]]; then
    printf 'azt: tenant IDs/domains can only contain letters, numbers, dot, underscore, colon, or hyphen\n' >&2
    return 2
  fi

  file="$(_azt_tenants_file)"
  dir="$(dirname "$file")"
  mkdir -p "$dir"
  mkdir -p "$(_azt_profile_dir "$name")"

  temp="${file}.$$"
  {
    if [[ -f "$file" ]]; then
      awk -F '\t' -v name="$name" '$1 != name { print }' "$file"
    fi
    printf '%s\t%s\n' "$name" "$tenant_id"
  } > "$temp"

  mv "$temp" "$file"
  printf 'azt: mapped %s -> %s\n' "$name" "$tenant_id"
  printf 'azt: profile: %s\n' "$(_azt_profile_dir "$name")"
}

_azt_remove() {
  local name="$1"
  local file temp

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt remove <alias>\n' >&2
    return 2
  fi

  file="$(_azt_tenants_file)"
  [[ -f "$file" ]] || {
    printf 'azt: no tenant aliases configured\n' >&2
    return 1
  }

  if ! _azt_lookup "$name" >/dev/null; then
    printf 'azt: unknown tenant alias: %s\n' "$name" >&2
    return 1
  fi

  temp="${file}.$$"
  awk -F '\t' -v name="$name" '$1 != name { print }' "$file" > "$temp"
  mv "$temp" "$file"

  if [[ "${AZT_ACTIVE_ALIAS:-}" == "$name" ]]; then
    unset AZT_ACTIVE_ALIAS AZT_ACTIVE_TENANT_ID
  fi

  printf 'azt: removed %s\n' "$name"
  printf 'azt: profile left in place: %s\n' "$(_azt_profile_dir "$name")"
}

_azt_list() {
  local file name tenant_id profile_dir found
  file="$(_azt_tenants_file)"
  found=false

  [[ -f "$file" ]] || {
    printf 'No Azure tenant aliases configured.\n'
    printf 'Add one with: azt add <alias> <tenant-id-or-domain>\n'
    return 0
  }

  printf '%-18s %-38s %s\n' ALIAS TENANT CONFIG_DIR
  printf '%-18s %-38s %s\n' ----- ------ ----------

  while IFS=$'\t' read -r name tenant_id; do
    [[ -z "$name" || "$name" == \#* ]] && continue
    found=true
    profile_dir="$(_azt_profile_dir "$name")"
    printf '%-18s %-38s %s\n' "$name" "$tenant_id" "$profile_dir"
  done < "$file"

  if [[ "$found" != true ]]; then
    printf 'No Azure tenant aliases configured.\n'
    printf 'Add one with: azt add <alias> <tenant-id-or-domain>\n'
  fi
}

_azt_id() {
  local tenant_id
  tenant_id="$(_azt_require_alias "$1")" || return
  printf '%s\n' "$tenant_id"
}

_azt_login() {
  local name="$1"
  local tenant_id

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt <alias> login [az login args...]\n' >&2
    return 2
  fi
  shift

  tenant_id="$(_azt_require_alias "$name")" || return
  _azt_az "$name" login --tenant "$tenant_id" "$@"
}

_azt_current() {
  local name="$1"

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt <alias> current\n' >&2
    return 2
  fi

  _azt_az "$name" account show --query '{subscription:name, subscriptionId:id, tenantId:tenantId, user:user.name}' -o table
}

_azt_subscriptions() {
  local name="$1"

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt <alias> subscriptions\n' >&2
    return 2
  fi

  _azt_az "$name" account list --all --query '[].{Name:name,SubscriptionId:id,TenantId:tenantId,State:state,Default:isDefault}' -o table
}

_azt_set_subscription() {
  local name="$1"
  local subscription="$2"

  if [[ -z "$name" || -z "$subscription" ]]; then
    printf 'azt: usage: azt <alias> set <subscription-id-or-name>\n' >&2
    return 2
  fi

  _azt_az "$name" account set --subscription "$subscription" || return
  _azt_az "$name" account show --query '{subscription:name, subscriptionId:id, tenantId:tenantId, user:user.name}' -o table
}

_azt_run_az() {
  local name="$1"

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt <alias> <az args...>\n' >&2
    return 2
  fi
  shift

  if [[ $# -eq 0 ]]; then
    printf 'azt: usage: azt <alias> <az args...>\n' >&2
    return 2
  fi

  _azt_az "$name" "$@"
}

_azt_for_alias() {
  local name="$1"
  local action="${2:-profile}"

  shift
  [[ $# -gt 0 ]] && shift

  case "$action" in
    login)
      _azt_login "$name" "$@"
      ;;
    current)
      _azt_current "$name"
      ;;
    subscriptions|subs)
      _azt_subscriptions "$name"
      ;;
    set|subscription)
      _azt_set_subscription "$name" "$@"
      ;;
    profile)
      _azt_profile "$name"
      ;;
    id|tenant)
      _azt_id "$name"
      ;;
    use)
      printf 'azt: "use" does not change this shell; plain az keeps its default profile.\n' >&2
      printf 'azt: run "azt %s <az args...>" or "azt %s set <subscription>".\n' "$name" "$name" >&2
      return 2
      ;;
    help|-h|--help)
      _azt_usage
      ;;
    *)
      _azt_run_az "$name" "$action" "$@"
      ;;
  esac
}

azt() {
  local command="${1:-help}"

  [[ $# -gt 0 ]] && shift

  case "$command" in
    add)
      _azt_add "$@"
      ;;
    remove|rm|delete|del)
      _azt_remove "$@"
      ;;
    list|ls)
      _azt_list
      ;;
    id|tenant)
      _azt_id "$@"
      ;;
    login)
      _azt_login "$@"
      ;;
    current)
      _azt_current "$@"
      ;;
    subscriptions|subs)
      _azt_subscriptions "$@"
      ;;
    set|subscription)
      _azt_set_subscription "$@"
      ;;
    profile)
      _azt_profile "$@"
      ;;
    use)
      printf 'azt: "use" does not change this shell; plain az keeps its default profile.\n' >&2
      printf 'azt: run "azt <alias> <az args...>" or "azt <alias> set <subscription>".\n' >&2
      return 2
      ;;
    help|-h|--help)
      _azt_usage
      ;;
    *)
      if _azt_lookup "$command" >/dev/null; then
        _azt_for_alias "$command" "$@"
      else
        printf 'azt: unknown command or tenant alias: %s\n' "$command" >&2
        _azt_usage >&2
        return 2
      fi
      ;;
  esac
}
