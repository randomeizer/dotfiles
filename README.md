# Dotfiles

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

## Validate installation changes

With GNU Stow and Python 3 available:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
bash -n setup.sh setup-shells.sh
```

Installer tests use a temporary checkout and home; they do not install into your
live configuration or launch applications. This install change does not modify
the other recommendations from the setup review.

## Config sync

Shell startup runs `~/.config/scripts/config-sync.sh` to link shared skills and
the `azt` command. Links are removed only when they point to the expected managed
skill path and that path has disappeared. Existing files and unrelated links are
preserved; collisions and failed tasks are reported without interrupting shell
startup. The sync continues through all tasks after an error.

To synchronize and check for collisions or other failures explicitly, run:

```bash
~/.config/scripts/config-sync.sh --strict
```

Strict mode returns a nonzero status if any task fails. Add `--debug` to show
which tasks are run. Strict mode still performs synchronization.
