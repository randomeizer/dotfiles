## Clarifications
### Session 2025-10-09
- Q: How should the prompt behave if a required module (e.g., Starship, Catppuccin theme) is not installed?
	→ A: Attempt to auto-install missing modules; if that fails, fail gracefully with a clear error message.
- Q: How should the prompt handle very narrow terminal widths?
	→ A: Truncate modules to fit; if still too narrow, hide right-aligned modules.
- Q: What should the default behavior be if the environment variable for module gating is unset or set incorrectly?
	→ A: Fail with a configuration error.

# Feature Specification: Fast, Cross-Shell Prompt with Right-Aligned Context

**Feature Branch**: `002-spec-7-prompt`  
**Created**: 2025-10-09  
**Status**: Draft  
**Input**: User description: "Spec 7 — Prompt (Starship)

Goal: Fast, cross-shell prompt with right-aligned context.
Scope/Constraints: Keep left prompt minimal; gate noisy modules. This will replace the current Oh-my-zsh utility for zsh.
Steps: Install Starship → configure modules: git, Azure (profile/tenant), Kubernetes (off by default), language indicators (Go, Swift, Java; optional) → apply Catppuccin → right-side segments.
Success: Context visible at a glance; prompt latency negligible.
Risks/Notes: Excess modules create noise—toggle by env var. Replaces Oh-my-zsh for zsh users.

## Execution Flow (main)

```plain
1. Parse user description from Input
2. Extract key concepts: prompt speed, cross-shell compatibility, right-aligned context, minimal left prompt, module gating, context visibility, prompt latency, noise control, Azure context, language indicators (Go, Swift, Java)
3. Mark ambiguities (see [NEEDS CLARIFICATION] below)
4. Define user scenarios and acceptance criteria
5. Generate functional requirements
6. Identify key entities (if any)
7. Review for business focus and completeness
8. Return: SUCCESS (spec ready for planning)
```

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story

As a user who works in multiple shells, I want my command prompt to be fast, visually clear, and show important context (git, Azure, language indicators) right-aligned, so I can see relevant information at a glance without prompt lag or clutter.

### Acceptance Scenarios

1. **Given** a supported shell, **When** the user opens a new terminal, **Then** the prompt appears instantly with minimal left-side content and right-aligned context modules (git, Azure, language indicators).
2. **Given** noisy modules are present, **When** the controlling environment variable is set, **Then** those modules are hidden or disabled from the prompt.
3. **Given** the user is not in a git repo, **When** the prompt is shown, **Then** git context is omitted from the right side.
4. **Given** the user is not using Azure or Kubernetes, **When** the prompt is shown, **Then** those modules are omitted or off by default.
5. **Given** the user has not enabled optional language indicators, **When** the prompt is shown, **Then** Go, Swift, and Java modules are hidden.
6. **Given** the user switches shell (e.g., zsh, bash, fish), **When** the prompt loads, **Then** the experience and context remain consistent.

### Edge Cases

- What happens if a required module (e.g., Starship, Catppuccin theme) is not installed? The system will attempt to auto-install missing modules; if that fails, it will fail gracefully with a clear error message.
- How does the system handle very narrow terminal widths? The prompt will truncate modules to fit; if still too narrow, it will hide right-aligned modules.
- What if the environment variable for module gating is unset or set incorrectly? The system will fail with a configuration error.

## Requirements *(mandatory)*

### Functional Requirements
- **FR-012**: The system MUST fail with a configuration error if the environment variable for module gating is unset or set incorrectly.

- **FR-001**: The system MUST provide a fast, cross-shell prompt with negligible latency for the user.
- **FR-002**: The prompt MUST display right-aligned context modules for git, Azure (profile/tenant), and language indicators (Go, Swift, Java; optional).
- **FR-003**: The left side of the prompt MUST remain minimal, showing only essential information (e.g., working directory, user/host if needed).
- **FR-004**: The prompt MUST allow noisy modules (e.g., Kubernetes, extra info, language indicators) to be toggled on/off via an environment variable.
- **FR-005**: The prompt MUST apply a visually appealing theme (Catppuccin or equivalent) to all modules.
- **FR-006**: The prompt MUST hide or disable modules (git, Azure, Kubernetes, language indicators) when their context is not present (e.g., not in a git repo, not using Azure, not in a relevant project directory).
- **FR-007**: The prompt MUST support consistent appearance and behavior across multiple shells (zsh, bash, fish, etc.).
- **FR-008**: The system MUST provide clear context at a glance, with no excessive visual noise.
- **FR-009**: The system MUST allow users to easily enable/disable right-aligned modules via configuration or environment variable.
- **FR-010**: The system MUST attempt to auto-install missing modules; if that fails, it MUST fail gracefully with a clear error message.
- **FR-011**: The system MUST handle narrow terminal widths by truncating modules to fit; if still too narrow, it MUST hide right-aligned modules.

### Key Entities

- **Prompt Context Module**: Represents a segment of the prompt that displays contextual information (e.g., git status, Azure profile, language version). Attributes: type, visibility, content, gating variable.
- **Prompt Theme**: Represents the visual style applied to the prompt and its modules. Attributes: name, color scheme, compatibility.

---

## Review & Acceptance Checklist

### Content Quality

- [ ] No implementation details (languages, frameworks, APIs)
- [ ] Focused on user value and business needs
- [ ] Written for non-technical stakeholders
- [ ] All mandatory sections completed

### Requirement Completeness

- [ ] No [NEEDS CLARIFICATION] markers remain
- [ ] Requirements are testable and unambiguous  
- [ ] Success criteria are measurable
- [ ] Scope is clearly bounded
- [ ] Dependencies and assumptions identified

---

## Execution Status

- [ ] User description parsed
- [ ] Key concepts extracted
- [ ] Ambiguities marked
- [ ] User scenarios defined
- [ ] Requirements generated
- [ ] Entities identified
- [ ] Review checklist passed

---
