# Nushell Environment Config File
#
# version = "0.95.0"

let home = ($env.HOME? | default $nu.home-dir)

# Refresh generated integrations only when the executable or its path changes.
# An unknown existing file is left alone; previous generated files are migrated.
def dotfiles-refresh-nu-init [tool: string, target: path] {
    let found = (which $tool | where type == 'external')
    if ($found | is-empty) { return }
    let executable = ($found | first | get path)
    let header = $"# dotfiles executable: ($executable)\n"
    # Inspect the entry itself: a dangling user symlink does not pass path exists.
    let kind = (try { ls -l $target | get 0.type } catch { null })
    if $kind != null and $kind != 'file' { return }
    let exists = ($kind == 'file')
    let previous = if $exists { try { open --raw $target } catch { return } } else { '' }
    let owned = (($previous | str starts-with '# dotfiles executable: ') or
        (($tool == 'starship') and ($previous | str starts-with '# this file is both a valid')) or
        (($tool == 'carapace') and ($previous | str contains 'let carapace_completer') and ($previous | str contains 'CARAPACE_SHELL')))
    if $exists and (not $owned) { return }
    let stale = if $exists {
        try { (ls -l $executable | get 0.modified) > (ls -l $target | get 0.modified) } catch { true }
    } else { true }
    if $exists and ($previous | str starts-with $header) and (not $stale) { return }
    let generated = if $tool == 'starship' {
        do -i { ^$executable init nu } | complete
    } else {
        do -i { ^$executable _carapace nushell } | complete
    }
    if $generated.exit_code != 0 or ($generated.stdout | is-empty) { return }
    let parent = ($target | path dirname)
    let temporary = ($parent | path join $".($tool)-(random uuid).tmp")
    try {
        mkdir $parent
        $"($header)($generated.stdout)" | save --force $temporary
        mv --force $temporary $target
    } catch {
        if ($temporary | path exists) { rm --force $temporary }
    }
}

def create_left_prompt [] {
    let dir = match (do --ignore-errors { $env.PWD | path relative-to $home }) {
        null => $env.PWD
        '' => '~'
        $relative_pwd => ([~ $relative_pwd] | path join)
    }

    let path_color = (if (is-admin) { ansi red_bold } else { ansi green_bold })
    let separator_color = (if (is-admin) { ansi light_red_bold } else { ansi light_green_bold })
    let path_segment = $"($path_color)($dir)"

    $path_segment | str replace --all (char path_sep) $"($separator_color)(char path_sep)($path_color)"
}

def create_right_prompt [] {
    # create a right prompt in magenta with green separators and am/pm underlined
    let time_segment = ([
        (ansi reset)
        (ansi magenta)
        (date now | format date '%x %X') # try to respect user's locale
    ] | str join | str replace --regex --all "([/:])" $"(ansi green)${1}(ansi magenta)" |
        str replace --regex --all "([AP]M)" $"(ansi magenta_underline)${1}")

    let last_exit_code = if ($env.LAST_EXIT_CODE != 0) {([
        (ansi rb)
        ($env.LAST_EXIT_CODE)
    ] | str join)
    } else { "" }

    ([$last_exit_code, (char space), $time_segment] | str join)
}

# Use nushell functions to define your right and left prompt
$env.PROMPT_COMMAND = {|| create_left_prompt }
# FIXME: This default is not implemented in rust code as of 2023-09-08.
$env.PROMPT_COMMAND_RIGHT = {|| create_right_prompt }

# The prompt indicators are environmental variables that represent
# the state of the prompt
$env.PROMPT_INDICATOR = {|| "> " }
$env.PROMPT_INDICATOR_VI_INSERT = {|| ": " }
$env.PROMPT_INDICATOR_VI_NORMAL = {|| "> " }
$env.PROMPT_MULTILINE_INDICATOR = {|| "::: " }

# If you want previously entered commands to have a different prompt from the usual one,
# you can uncomment one or more of the following lines.
# This can be useful if you have a 2-line prompt and it's taking up a lot of space
# because every command entered takes up 2 lines instead of 1. You can then uncomment
# the line below so that previously entered commands show with a single `🚀`.
# $env.TRANSIENT_PROMPT_COMMAND = {|| "🚀 " }
# $env.TRANSIENT_PROMPT_INDICATOR = {|| "" }
# $env.TRANSIENT_PROMPT_INDICATOR_VI_INSERT = {|| "" }
# $env.TRANSIENT_PROMPT_INDICATOR_VI_NORMAL = {|| "" }
# $env.TRANSIENT_PROMPT_MULTILINE_INDICATOR = {|| "" }
# $env.TRANSIENT_PROMPT_COMMAND_RIGHT = {|| "" }

# Specifies how environment variables are:
# - converted from a string to a value on Nushell startup (from_string)
# - converted from a value back to a string when running external commands (to_string)
# Note: The conversions happen *after* config.nu is loaded
$env.ENV_CONVERSIONS = {
    "PATH": {
        from_string: { |s| $s | split row (char esep) | path expand --no-symlink }
        to_string: { |v| $v | path expand --no-symlink | str join (char esep) }
    }
    "Path": {
        from_string: { |s| $s | split row (char esep) | path expand --no-symlink }
        to_string: { |v| $v | path expand --no-symlink | str join (char esep) }
    }
}

# Directories to search for scripts when calling source or use
# The default for this is $nu.default-config-dir/scripts
$env.NU_LIB_DIRS = [
    ($nu.default-config-dir | path join 'scripts') # add <nushell-config-dir>/scripts
    ($nu.data-dir | path join 'completions') # default home for nushell completions
]

# Directories to search for plugin binaries when calling register
# The default for this is $nu.default-config-dir/plugins
$env.NU_PLUGIN_DIRS = [
    ($nu.default-config-dir | path join 'plugins') # add <nushell-config-dir>/plugins
]

# To add entries to PATH (on Windows you might use Path), you can use the following pattern:
# $env.PATH = ($env.PATH | split row (char esep) | prepend '/some/path')
# An alternate way to add entries to $env.PATH is to use the custom command `path add`
# which is built into the nushell stdlib:
use std "path add"
# $env.PATH = ($env.PATH | split row (char esep))
# path add /some/path
# path add ($env.CARGO_HOME | path join "bin")
# path add ($env.HOME | path join ".local" "bin")
# $env.PATH = ($env.PATH | uniq)
path add /opt/homebrew/bin
path add '~/.local/bin'
path add ($env.HOME | path join 'go' 'bin')
if ('/opt/homebrew/opt/ruby/bin' | path exists) {
    path add /opt/homebrew/opt/ruby/bin
}

# To load from a custom file you can use:
# source ($nu.default-config-dir | path join 'custom.nu')

# zoxide init nushell | save -f ~/.zoxide.nu
$env.CARAPACE_BRIDGES = 'zsh,fish,bash,inshellisense' # optional
let _carapace_cache = ($home | path join '.cache' 'carapace')
if $nu.is-interactive {
    dotfiles-refresh-nu-init 'carapace' ($_carapace_cache | path join 'init.nu')
}
