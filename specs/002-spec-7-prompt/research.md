# Research: Fast, Cross-Shell Prompt with Right-Aligned Context

## Decision Log

- Decision: Use Starship as the prompt engine for all supported shells (zsh, bash, fish, etc.)
- Rationale: Starship is fast, cross-shell, highly configurable, and supports right-aligned segments and custom modules. It is widely adopted and actively maintained.
- Alternatives considered: oh-my-zsh (zsh only, less cross-shell), custom PS1 scripting (less maintainable, less feature-rich), powerlevel10k (zsh only, more complex).

- Decision: Replace Oh-my-zsh for zsh users with Starship.
- Rationale: Starship provides a unified experience across shells and is less intrusive than oh-my-zsh.
- Alternatives considered: Continue using oh-my-zsh for zsh only (would not meet cross-shell requirement).

- Decision: Use Azure (profile/tenant) as the cloud context module instead of AWS.
- Rationale: User requested Azure context; Starship supports Azure module.
- Alternatives considered: AWS (not required for this feature).

- Decision: Language indicators for Go, Swift, Java are optional modules, toggled by environment variable.
- Rationale: Reduces prompt noise and allows user control.
- Alternatives considered: Always show all language indicators (would add clutter).

- Decision: On narrow terminals, truncate modules to fit; if still too narrow, hide right-aligned modules.
- Rationale: Preserves usability and avoids prompt wrapping or overflow.
- Alternatives considered: Collapse to icons only, wrap to multiple lines (less clear or visually cluttered).

- Decision: If a required module is missing, attempt to auto-install; if that fails, fail gracefully with a clear error message.
- Rationale: Improves user experience and reduces setup friction.
- Alternatives considered: Fail immediately, show fallback prompt (less user-friendly).

- Decision: If the module gating environment variable is unset or incorrect, fail with a configuration error.
- Rationale: Prevents silent misconfiguration and ensures user is aware of the issue.
- Alternatives considered: Show all modules, hide all modules, show only essentials (less explicit, could confuse users).

## Open Questions

None. All critical clarifications resolved in the spec.

## References
- https://starship.rs/
- https://starship.rs/config/
- https://starship.rs/advanced-config/#right-prompt
- https://starship.rs/guide/#cross-shell-support
