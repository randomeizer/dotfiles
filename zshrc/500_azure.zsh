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
  command cat <<'EOF'
azt manages Azure tenant aliases and runs az with a per-alias AZURE_CONFIG_DIR.
Plain az keeps using its default Azure CLI profile.

Usage:
  azt --add <alias> <tenant-id-or-domain>
  azt --add-login <alias> [az login args...]
  azt --remove <alias>
  azt --list
  azt --id <alias>
  azt --profile <alias>
  azt --login <alias> [az login args...]
  azt --current <alias>
  azt --subscriptions <alias>
  azt --set <alias> <subscription-id-or-name>
  azt --help

Azure CLI passthrough:
  azt <alias>                 # show alias profile details
  azt <alias> <az args...>    # run: az <az args...>, using the alias profile

Options:
  --add            create or replace an alias mapped to a tenant ID or domain
  --add-login      run az login in a new alias profile, then map its active tenant
  --remove         remove an alias; the alias profile directory is left in place
  --list           list configured aliases, tenant mappings, and profile paths
  --id             print the tenant ID or domain mapped to an alias
  --profile        show an alias's tenant and AZURE_CONFIG_DIR path
  --login          run az login for the alias's mapped tenant
  --current        show the active account inside the alias profile
  --subscriptions  list subscriptions cached inside the alias profile
  --set            set the active subscription inside the alias profile
  --help           show this help text

Examples:
  azt --add qps 61c207dc-d4fe-40a3-8341-0f31daa4c62e
  azt --add-login qps
  azt --add-login qps --allow-no-subscriptions
  azt --login qps
  azt --login qps --allow-no-subscriptions
  azt --set qps SUB-PRD-VIMS
  azt qps group list
EOF
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
  printf 'azt: run "azt --list" to see configured aliases\n' >&2
  return 1
}

_azt_profile() {
  local name="$1"
  local tenant_id profile_dir

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt --profile <alias>\n' >&2
    return 2
  fi

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
    _azt_profile "$name"
    return
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

_azt_validate_alias_name() {
  local name="$1"

  if [[ ! "$name" =~ '^[A-Za-z0-9][A-Za-z0-9._-]*$' ]]; then
    printf 'azt: aliases must start with a letter or number and contain only letters, numbers, dot, underscore, or hyphen\n' >&2
    return 2
  fi
}

_azt_validate_tenant_id() {
  local tenant_id="$1"

  if [[ ! "$tenant_id" =~ '^[A-Za-z0-9._:-]+$' ]]; then
    printf 'azt: tenant IDs/domains can only contain letters, numbers, dot, underscore, colon, or hyphen\n' >&2
    return 2
  fi
}

_azt_store_alias() {
  local name="$1"
  local tenant_id="$2"
  local file dir temp

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

_azt_add() {
  local name="$1"
  local tenant_id="$2"

  if [[ -z "$name" || -z "$tenant_id" ]]; then
    printf 'azt: usage: azt --add <alias> <tenant-id-or-domain>\n' >&2
    return 2
  fi

  _azt_validate_alias_name "$name" || return
  _azt_validate_tenant_id "$tenant_id" || return
  _azt_store_alias "$name" "$tenant_id"
}

_azt_add_login() {
  local name="$1"
  local tenant_id profile_dir

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt --add-login <alias> [az login args...]\n' >&2
    return 2
  fi
  shift

  _azt_validate_alias_name "$name" || return

  profile_dir="$(_azt_profile_dir "$name")"
  mkdir -p "$profile_dir"

  (
    export AZURE_CONFIG_DIR="$profile_dir"
    export AZT_ACTIVE_ALIAS="$name"
    az login "$@"
  ) || return

  tenant_id="$(AZURE_CONFIG_DIR="$profile_dir" az account show --query tenantId -o tsv 2>/dev/null)"
  tenant_id="${tenant_id%%$'\n'*}"

  if [[ -z "$tenant_id" ]]; then
    tenant_id="$(AZURE_CONFIG_DIR="$profile_dir" az account tenant list --query '[0].tenantId' -o tsv 2>/dev/null)"
    tenant_id="${tenant_id%%$'\n'*}"
  fi

  if [[ -z "$tenant_id" ]]; then
    printf 'azt: login succeeded, but no tenant ID could be determined from the alias profile\n' >&2
    printf 'azt: inspect it with: AZURE_CONFIG_DIR=%s az account show\n' "$profile_dir" >&2
    return 1
  fi

  _azt_validate_tenant_id "$tenant_id" || return
  _azt_store_alias "$name" "$tenant_id"
}

_azt_remove() {
  local name="$1"
  local file temp

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt --remove <alias>\n' >&2
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

  printf 'azt: removed %s\n' "$name"
  printf 'azt: profile left in place: %s\n' "$(_azt_profile_dir "$name")"
}

_azt_list() {
  local file name tenant_id profile_dir found
  file="$(_azt_tenants_file)"
  found=false

  [[ -f "$file" ]] || {
    printf 'No Azure tenant aliases configured.\n'
    printf 'Add one with: azt --add <alias> <tenant-id-or-domain>\n'
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
    printf 'Add one with: azt --add <alias> <tenant-id-or-domain>\n'
  fi
}

_azt_id() {
  local name="$1"
  local tenant_id

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt --id <alias>\n' >&2
    return 2
  fi

  tenant_id="$(_azt_require_alias "$name")" || return
  printf '%s\n' "$tenant_id"
}

_azt_args_contain_tenant_option() {
  local arg

  for arg in "$@"; do
    case "$arg" in
      --tenant|--tenant=*|-t)
        return 0
        ;;
    esac
  done

  return 1
}

_azt_login() {
  local name="$1"
  local tenant_id

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt --login <alias> [az login args...]\n' >&2
    return 2
  fi
  shift

  if _azt_args_contain_tenant_option "$@"; then
    printf 'azt: --login uses the tenant mapped to the alias; do not pass --tenant or -t\n' >&2
    printf 'azt: for a raw Azure CLI login command, use: azt %s login ...\n' "$name" >&2
    return 2
  fi

  tenant_id="$(_azt_require_alias "$name")" || return
  _azt_az "$name" login --tenant "$tenant_id" "$@"
}

_azt_current() {
  local name="$1"

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt --current <alias>\n' >&2
    return 2
  fi

  _azt_az "$name" account show --query '{subscription:name, subscriptionId:id, tenantId:tenantId, user:user.name}' -o table
}

_azt_subscriptions() {
  local name="$1"

  if [[ -z "$name" ]]; then
    printf 'azt: usage: azt --subscriptions <alias>\n' >&2
    return 2
  fi

  _azt_az "$name" account list --all --query '[].{Name:name,SubscriptionId:id,TenantId:tenantId,State:state,Default:isDefault}' -o table
}

_azt_set_subscription() {
  local name="$1"
  local subscription="$2"

  if [[ -z "$name" || -z "$subscription" ]]; then
    printf 'azt: usage: azt --set <alias> <subscription-id-or-name>\n' >&2
    return 2
  fi

  _azt_az "$name" account set --subscription "$subscription" || return
  _azt_az "$name" account show --query '{subscription:name, subscriptionId:id, tenantId:tenantId, user:user.name}' -o table
}

azt() {
  local command="${1:-}"

  if [[ -z "$command" ]]; then
    _azt_usage
    return
  fi
  shift

  case "$command" in
    --add)
      _azt_add "$@"
      ;;
    --add-login|--login-add)
      _azt_add_login "$@"
      ;;
    --remove|--rm|--delete)
      _azt_remove "$@"
      ;;
    --list|--ls)
      _azt_list
      ;;
    --id|--tenant)
      _azt_id "$@"
      ;;
    --profile)
      _azt_profile "$@"
      ;;
    --login)
      _azt_login "$@"
      ;;
    --current)
      _azt_current "$@"
      ;;
    --subscriptions|--subs)
      _azt_subscriptions "$@"
      ;;
    --set|--subscription)
      _azt_set_subscription "$@"
      ;;
    --help|-h)
      _azt_usage
      ;;
    --*)
      printf 'azt: unknown option: %s\n' "$command" >&2
      _azt_usage >&2
      return 2
      ;;
    *)
      _azt_az "$command" "$@"
      ;;
  esac
}
