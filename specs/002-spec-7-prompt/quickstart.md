# Quickstart: Fast, Cross-Shell Prompt with Right-Aligned Context

## Prerequisites
- Supported shell (zsh, bash, fish, etc.)
- Starship installed (https://starship.rs/)
- Catppuccin theme files (optional, for best appearance)

## Steps
1. Remove or disable Oh-my-zsh if present (for zsh users).
2. Install Starship using the official instructions for your platform.
3. Add Starship initialization to your shell config (e.g., `.zshrc`, `.bashrc`, `.config/fish/config.fish`).
4. Copy the provided Starship configuration file to `~/.config/starship.toml`.
5. Set environment variable(s) to enable/disable optional modules (Go, Swift, Java, Kubernetes, etc.).
6. Open a new terminal to verify the prompt loads instantly with right-aligned context.
7. Confirm that modules appear only when their context is present (e.g., git repo, Azure login, language project directory).
8. Test prompt behavior with and without the module gating environment variable set.
9. Test prompt in a narrow terminal window to verify truncation/hiding of right-aligned modules.

## Troubleshooting
- If a required module is missing, Starship will attempt to auto-install; if that fails, a clear error message will be shown.
- If the module gating environment variable is unset or incorrect, a configuration error will be shown.

## References
- https://starship.rs/guide/#cross-shell-support
- https://starship.rs/config/
- https://catppuccin.com/docs/configs/starship
