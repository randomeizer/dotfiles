# Dotfiles

## Rebuild a Mac

This setup targets macOS, primarily Apple Silicon. On a new machine, install the
Apple command line tools if Git is unavailable, then install [Homebrew](https://brew.sh/)
and add it to your shell's PATH using its installation instructions. Clone this
repository and run the read-only check from the checkout:

```bash
git clone https://github.com/randomeizer/dotfiles.git
cd dotfiles
./bootstrap.sh check
```

The check reports GNU Stow, optional tools and standard desktop-app locations,
then previews configuration conflicts without changing your home or target.
It also inspects current-user sync collisions without performing sync; skill
checks are deferred if the shared source has not yet been installed. Missing
Stow, a config conflict, or a sync collision makes it return nonzero. Select any
groups you intend to use to treat their missing commands/apps as failures:

```bash
./bootstrap.sh check --group shell --group desktop
```

Once Homebrew is available, install GNU Stow and any selected groups, deploy the
config, and run strict sync for the current user:

```bash
./bootstrap.sh install --install-packages --group shell --group desktop
```

Package installation is explicit: without `--install-packages`, `install` only
deploys the config and runs sync. The groups are independent and repeatable:

| Group | Packages |
| --- | --- |
| Core | GNU Stow; installed whenever `--install-packages` is used. |
| `shell` | Nushell, Starship, Carapace, eza, fzf, zoxide, Atuin, direnv, tmux, and JetBrains Mono fonts. |
| `desktop` | AeroSpace, SketchyBar and Hammerspoon on macOS. |
| `work` | kubectl, Azure CLI, GitHub CLI, Difftastic, jless, ast-grep, and just. |

The manifests are in `bootstrap/Brewfile.*`. Homebrew is invoked with
`--no-upgrade`; it may still need to update a dependency during installation.
The check looks for commands on PATH and desktop apps in `/Applications`; it
does not verify fonts or detect apps installed elsewhere. Install additional fonts
or apps used by your particular setup separately. Optional integrations need
their tools installed before they can work.

The work tools include Difftastic for structural Git diffs, `jless` for interactive
JSON exploration, and `ast-grep` for syntax-aware code search. Enable Difftastic
as the default for `git diff` with `git config --global diff.external difft`.
This Git setting is maintained separately from the Stow-managed configuration.
Zsh provides `gdifft` to select Difftastic explicitly and `gdiffplain` for plain
patches (`git diff --no-ext-diff --no-textconv`). Shared agent instructions in
`agents/AGENTS.md` describe when to use these tools; active agent instructions
maintained separately need the same guidance.

For a disposable config-only trial, pass `--home` to either command:

```bash
./bootstrap.sh check --home /tmp/dotfiles-home
./bootstrap.sh install --home /tmp/dotfiles-home
```

An alternate home skips config sync because the sync scripts use the current
user's `$HOME`; package installation, if requested, still affects the current
machine. Its check also skips the current-user sync collision preview. The trial
does not change `$HOME` or test launching applications.

After installation, grant macOS Accessibility permissions to desktop tools as
needed, sign into services separately, and integrate any preserved `.zshrc` or
other existing files manually. SSH setup is opt-in through `setup.sh --with-ssh`
after reviewing its configuration. The `--home` trial and automated tests do not
replace a clean-account or live desktop check.

### Recovery

If a check or install reports a Stow conflict, inspect the named existing path;
the installer will not adopt or overwrite it. Resolve it manually and rerun the
check. If strict sync reports collisions, inspect the named links before changing
them; it performs synchronization even when it returns a failure. A failure after
config installation does not roll back the links already created.

To remove Stow-managed config links deliberately, from the checkout run:

```bash
stow --delete --dir "$(pwd -P)" --target "$HOME/.config" .
```

This removes all matching managed links, including ones that existed before the
most recent install; it is not a last-run undo. Review native `.zshrc` and
`.hammerspoon` links separately and remove them only if they point to the managed
configuration. Old repository-only links from previous broad installs are not
removed automatically.

## Install

Install GNU Stow first. Then invoke the installer from any working directory:

```bash
/path/to/dotfiles/setup.sh --dry-run
/path/to/dotfiles/setup.sh
```

The installer resolves its checkout, passes explicit Stow source/target paths,
and installs only the configuration directories listed in
[.stow-local-ignore](.stow-local-ignore). Repository metadata, setup scripts,
root documentation, the top-level `tests/` directory, and unknown top-level
directories are excluded.
`atuin/config.toml` is the single managed Atuin configuration.

The default target is `$HOME/.config`. Most configs assume this runtime location.
For isolated validation, use `--home` and optionally `--target`; these options
change installation destinations without changing the process's `$HOME`.

```bash
./setup.sh --dry-run --home /tmp/dotfiles-home
./setup.sh --home /tmp/dotfiles-home
```

`--target DIR` changes the configuration destination, defaulting to `<home>/.config`.
It is useful for deployment tests; configs containing `~/.config` paths still need
that location to resolve correctly when used on a real machine.

## Native application paths

| Application | Managed configuration | Native destination / behavior |
| --- | --- | --- |
| XDG-aware apps and shared scripts | `<target>/<app>` | Installed by Stow; no extra native bridge needed. |
| Zsh | `<target>/zshrc/.zshrc` | Linked from `<home>/.zshrc` if absent. |
| Hammerspoon | `<target>/hammerspoon` | Linked from `<home>/.hammerspoon` if absent; no macOS preference changes. |
| SSH | `<target>/ssh/ssh-config` | Reference only by default. `--with-ssh` links `<home>/.ssh/config` if absent. Review the SSH settings before opting in. |

When the repository SSH config is active, put private host entries and any
per-host compatibility exceptions in `~/.ssh/config.local`. That optional file
is read before the repository’s general defaults.

Existing native files, directories, and unrelated symlinks (including dangling
ones) are preserved and reported. If a preserved native path needs to load this
configuration, integrate it manually after reviewing your existing contents.
Stow config conflicts abort installation rather than adopting or overwriting
files; native bridges are only attempted after Stow succeeds. A repeated install
keeps existing correct links. A dry run never creates the home, target, or links.
Links left behind by older broad `stow .` installs are not deleted automatically;
review any obsolete repository-only links separately.

`setup-shells.sh` remains available to create just the Zsh bridge after the config
tree is installed. It shares the same options and preservation rules through
`setup.sh --shells-only`; Nushell and Starship need not be installed just to make
the link. Application dependencies must still be installed before using configs.

## Validate changes

With `just` installed (`brew install just`, or the `work` package group), run
`just` to list project commands or `just --show <recipe>` to inspect one. Recipes
delegate to the existing scripts and run from the repository root, including
when invoked from a subdirectory.

| Command | Behavior |
| --- | --- |
| `just check` | Run repository checks and require the behavioral tests. |
| `just doctor` | Check dependencies and preview configuration conflicts. |
| `just preview` | Preview configuration deployment without changing your home. |
| `just preview --home /tmp/dotfiles-home` | Preview deployment into an alternate home. |
| `just install` | Deploy configuration and run strict sync. |
| `just install --install-packages --group work` | Install work packages, deploy configuration, and run strict sync. |
| `just sync` | Synchronize shared skills and `azt`, reporting failures. |

Use `just check` before committing. Direct scripts remain available when `just`
is not installed, including during initial setup:

```bash
bash scripts/check.sh --require-tests
```

The command requires Git, Bash, Zsh, GNU Stow, Nushell, PowerShell, and Lua
(`luac`). It checks tracked and unignored new shell, Lua, JSON and TOML files.
The existing behavioral tests also run when Python 3 is available; otherwise the
script reports that they were skipped unless `--require-tests` is passed.
`just check` and GitHub Actions require those tests until they are migrated away
from Python ([issue #23](https://github.com/randomeizer/dotfiles/issues/23)).
Other missing tools and failed checks return a nonzero status.

These checks do not install into your live home or contact cloud services. They
do not replace a clean-account installation or a live desktop application check.

## Config sync

`bootstrap.sh install` runs the repository's `scripts/config-sync.sh` to link shared
skills and the `azt` command. Shell startup does not run sync; after changing
shared skills or sync tasks, run the command below explicitly. Links are removed
only when they point to the expected managed
skill path and that path has disappeared. Existing files and unrelated links are
preserved; collisions and failed tasks are reported without interrupting shell
startup. The sync continues through all tasks after an error.

To synchronize and check for collisions or other failures explicitly, run:

```bash
~/.config/scripts/config-sync.sh --strict
```

Strict mode returns a nonzero status if any task fails. Add `--debug` to show
which tasks are run. Strict mode still performs synchronization.

## Shell startup caches

Interactive Zsh caches generated Starship, kubectl, fzf, direnv, zoxide and Atuin
initialization under `${XDG_CACHE_HOME:-$HOME/.cache}/dotfiles-shell/zsh`.
Interactive PowerShell caches Starship initialization under the corresponding
`dotfiles-shell/powershell` directory. Nushell keeps its generated Starship
autoload under its data directory and Carapace output under `~/.cache/carapace`.
Only installed tools are initialized; missing optional tools are skipped.

Caches are generated on first interactive use and refreshed when the executable
path or its modification time changes. Generation writes a temporary file before
replacing the old cache, and a failed generation leaves the previous file intact.
Delete the relevant generated cache to force a refresh. Nushell preserves unknown
user-managed autoload files. Noninteractive shells do not run these integrations
or sync the config. Starship still runs as needed to render the prompt itself.
