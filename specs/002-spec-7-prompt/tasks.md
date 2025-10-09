# Tasks: Fast, Cross-Shell Prompt with Right-Aligned Context

**Input**: Design documents from `/specs/002-spec-7-prompt/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/

## Execution Flow (main)

```plain
1. Load plan.md from feature directory
2. Load optional design documents: data-model.md, contracts/, research.md, quickstart.md
3. Generate tasks by category: setup, tests, core, integration, polish
4. Apply task rules: parallelization, TDD, dependencies
5. Number tasks sequentially (T001, T002...)
6. Generate dependency graph
7. Create parallel execution examples
8. Validate task completeness
9. Return: SUCCESS (tasks ready for execution)
```

## Phase 3.1: Setup

- [X] T001 Audit existing CLI config directories for Starship and prompt-related files; document what is already covered.
- [X] T002 [P] Update or create `starship/starship.toml` to match spec (right-aligned context, minimal left, Azure, language indicators, gating, Catppuccin theme).
- [X] T003 [P] Ensure shell config files (`zshrc/`, `bashrc/`, `nushell/`, etc.) initialize Starship and remove Oh-my-zsh for zsh users.
- [ ] T004 [P] Ensure all config files are compatible with `stow` and symlinked correctly.

## Phase 3.2: Tests First (TDD)

- [ ] T005 [P] Contract test: GET /prompt/context in tests/contract/test_prompt_context.py
- [ ] T006 [P] Contract test: GET /prompt/theme in tests/contract/test_prompt_theme.py
- [ ] T007 [P] Contract test: POST /prompt/modules in tests/contract/test_prompt_modules.py
- [ ] T008 [P] Integration test: prompt loads instantly with right-aligned context in tests/integration/test_prompt_load.py
- [ ] T009 [P] Integration test: modules appear only when context is present in tests/integration/test_module_visibility.py
- [ ] T010 [P] Integration test: module gating env var disables noisy modules in tests/integration/test_module_gating.py
- [ ] T011 [P] Integration test: prompt truncates/hides modules in narrow terminal in tests/integration/test_narrow_terminal.py
- [ ] T012 [P] Integration test: missing module triggers auto-install or error in tests/integration/test_missing_module.py
- [ ] T013 [P] Integration test: gating env var unset/incorrect triggers config error in tests/integration/test_gating_env.py

## Phase 3.3: Core Implementation

- [ ] T014 [P] Implement Prompt Context Module logic in starship/starship.toml
- [ ] T015 [P] Implement Prompt Theme logic (Catppuccin) in starship/starship.toml
- [ ] T016 [P] Implement language indicator modules (Go, Swift, Java) as optional in starship/starship.toml
- [ ] T017 [P] Implement Azure context module in starship/starship.toml
- [ ] T018 [P] Implement module gating via environment variable in starship/starship.toml and shell configs
- [ ] T019 [P] Implement auto-install logic for Starship in setup.sh
- [ ] T020 [P] Implement error handling for gating env var in shell configs

## Phase 3.4: Integration

- [ ] T021 Integrate prompt config with all relevant shell startup files (zshrc/, bashrc/, nushell/, etc.)
- [ ] T022 Integrate stow workflow: verify all prompt-related configs are symlinked and managed centrally

## Phase 3.5: Polish

- [ ] T023 [P] Unit tests for prompt context module in tests/unit/test_prompt_context_module.py
- [ ] T024 [P] Unit tests for theme logic in tests/unit/test_prompt_theme.py
- [ ] T025 [P] Unit tests for gating logic in tests/unit/test_gating.py
- [ ] T026 [P] Performance test: prompt latency <100ms in tests/unit/test_performance.py
- [ ] T027 [P] Update documentation in specs/002-spec-7-prompt/quickstart.md

## Dependencies

- Setup (T001-T004) before tests (T005-T013)
- Tests (T005-T013) before implementation (T014-T020)
- Core (T014-T020) before integration (T021-T022)
- Integration before polish (T023-T027)

## Parallel Example

```plain
# Launch T002-T004 together:
Task: "Update or create starship/starship.toml to match spec"
Task: "Ensure shell config files initialize Starship and remove Oh-my-zsh for zsh users"
Task: "Ensure all config files are compatible with stow and symlinked correctly"

# Launch T005-T013 together:
Task: "Contract test: GET /prompt/context in tests/contract/test_prompt_context.py"
Task: "Contract test: GET /prompt/theme in tests/contract/test_prompt_theme.py"
Task: "Contract test: POST /prompt/modules in tests/contract/test_prompt_modules.py"
Task: "Integration test: prompt loads instantly with right-aligned context in tests/integration/test_prompt_load.py"
... (other integration tests)
```


## Config Audit

**starship/starship.toml**
- Exists and is configured for a minimal left prompt, right-aligned context, Catppuccin theme, and command timeout.
- Modules present: directory, character, git_branch, aws, golang, kubernetes (disabled), docker_context (disabled).
- Right prompt uses `$all`, but AWS is enabled (should be Azure per spec), and language indicators for Swift/Java are missing.
- Gating for noisy modules is partially present (Kubernetes disabled, but not via env var).
- Catppuccin palette is defined.

**zshrc/.zshrc**
- Starship is initialized and configured via `eval "$(starship init zsh)"` and `STARSHIP_CONFIG`.
- Oh-my-zsh is not explicitly present, but check for any remaining OMZ-specific config.
- Aliases and environment variables are present; no direct Starship or prompt logic outside of Starship.

**nushell/config.nu**
- No explicit Starship integration found.
- Uses its own prompt and theming system.
- No prompt context modules or right-aligned context as in Starship.

**bashrc** (not found)
- No bashrc directory or file present.

**stow compatibility**
- All config files are in their respective directories, suitable for symlinking with `stow`.

**Summary:**
- Starship is present and mostly configured, but AWS should be replaced with Azure, and language indicators for Swift/Java should be added.
- Gating for noisy modules should be controlled via environment variable.
- Oh-my-zsh is not present, but confirm with user if any OMZ remnants exist elsewhere.
- Nushell does not use Starship; consider if Starship prompt should be enabled for nushell or left as-is.

---
## Notes

- [P] tasks = different files, no dependencies
- Only modify or add config where spec is not already covered
- Verify tests fail before implementing
- Commit after each task
- Avoid: vague tasks, same file conflicts
