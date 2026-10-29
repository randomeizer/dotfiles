# Dotfiles

- Use `just --list` to discover project commands and `just --show <recipe>` to inspect them. Run `just check` before handing off changes.
- Keep implementation logic in the existing scripts; recipes in `justfile` are thin entry points. Direct script commands remain supported for bootstrapping without `just`.
- `just doctor` and `just preview` are read-only. `just install` deploys configuration, and `just sync` updates shared links; run these only when the requested work includes those changes.
