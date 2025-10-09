# Data Model: Fast, Cross-Shell Prompt with Right-Aligned Context

## Entities

### Prompt Context Module
- **Attributes:**
  - type (e.g., git, Azure, Go, Swift, Java)
  - visibility (boolean)
  - content (string)
  - gating variable (string, optional)

### Prompt Theme
- **Attributes:**
  - name (e.g., Catppuccin)
  - color scheme (object)
  - compatibility (list of shells)

## Relationships
- Each prompt can have multiple context modules, each with its own visibility and gating logic.
- The prompt theme is applied globally to all modules.

## Validation Rules
- Only show modules if their context is present (e.g., git repo, Azure login, language project directory).
- Optional modules (Go, Swift, Java) are shown only if enabled by environment variable.
- If a required module is missing, attempt auto-install; if that fails, show error.
- If gating env var is unset/incorrect, show configuration error.

## State Transitions
- Module visibility: hidden → visible (when context detected and gating allows)
- Module visibility: visible → hidden (when context lost or gating disables)

## Notes
- No persistent storage; all state is runtime in shell environment.
