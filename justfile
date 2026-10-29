set positional-arguments

# List available recipes.
default:
    @just --list

# Run syntax checks and require the behavioral tests.
check:
    bash scripts/check.sh --require-tests

# Check dependencies and preview configuration conflicts without changes.
doctor *args:
    bash bootstrap.sh check "$@"

# Preview config deployment without changing the target.
preview *args:
    bash setup.sh --dry-run "$@"

# Deploy config; package installation requires --install-packages.
install *args:
    bash bootstrap.sh install "$@"

# Synchronize shared skills and azt, reporting any failures.
sync *args:
    bash scripts/config-sync.sh --strict "$@"
