# Thin wrapper only -- no business logic belongs here.
# Every verb below just calls `uv run python -m adopt_hokkaido_lidar <verb>`.
# The CLI is directly runnable without just: `uv run python -m adopt_hokkaido_lidar <verb>`.

default:
    just --list

# Install dependencies (including dev/test deps).
setup:
    uv sync --extra dev

# Run the test suite.
test:
    uv run pytest

# Create/upgrade the local SQLite state database.
init-db *ARGS:
    uv run python -m adopt_hokkaido_lidar init-db {{ARGS}}

# Dry-run only: report what a real clean would remove, without deleting anything.
clean:
    @echo "dry-run: nothing is deleted by 'just clean'. Showing what would be removed:"
    @find . -name "__pycache__" -o -name "*.pyc" -o -name ".pytest_cache" | grep -v '^\./\.git' || true

# Remove ONLY disposable build/cache artifacts. Never touches state.sqlite3,
# manifests, checksums, provenance records, validation reports, or the
# published catalog -- see docs-src/provenance-policy.md.
clean-apply:
    find . -name "__pycache__" -not -path "./.git/*" -exec rm -rf {} +
    find . -name "*.pyc" -not -path "./.git/*" -delete
    rm -rf .pytest_cache
