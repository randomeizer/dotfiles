# Starship prompt configuration

This directory contains the centrally-managed Starship configuration used across shells.

Files:

- `starship.toml` — main Starship configuration (right-aligned context, Catppuccin palette, language indicators)

## Environment variables

The configuration uses a couple of gating environment variables to control optional/"noisy" modules:

- `STARSHIP_NOISY_MODULES` — set to `1` to enable noisy modules (kubernetes, docker), `0` to disable.
- `STARSHIP_LANG_INDICATORS` — set to `1` to enable language indicators (Go, Swift, Java), `0` to disable.

Both variables should be set to `0` or `1`. Some shell init files validate these and will fail with a clear message if they are unset or invalid.

## Stow usage

This repo is designed to be managed with `stow`.

From the repo root:

```sh
# create symlinks for this machine
stow -t ~ starship zshrc nushell
```

This will create `~/.config/starship` pointing to this directory, and will install the shell dotfiles.

## Shell wiring

- zsh: `zshrc/.zshrc` initializes Starship and validates gating env vars. It sets `STARSHIP_CONFIG` to `~/.config/starship/starship.toml`.
- nushell: `nushell/config.nu` sets `STARSHIP_CONFIG` and provides sane defaults for the gating env vars if they're not set.

## Testing

Point Starship at the repo config and run a quick check:

```sh
export STARSHIP_CONFIG="$PWD/starship/starship.toml"
/opt/homebrew/bin/starship prompt  # prints the prompt
/opt/homebrew/bin/starship explain # human-readable breakdown of modules
```

## Troubleshooting

- If Starship reports a TOML parse error, open `starship/starship.toml` and look for invalid expressions like `"$VAR" != "1"` — Starship/TOML doesn't accept expressions. Use `custom` modules with `when` clauses instead.
- If a module shows but you don't want it, explicitly disable it in `starship.toml` (e.g., `[ruby] disabled = true`).
- If the shell doesn't pick up the config, ensure `STARSHIP_CONFIG` is set in your shell init and that `stow` has linked the `~/.config/starship` directory.
