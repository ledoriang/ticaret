#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; }

usage() {
    cat <<EOF
Usage: $(basename "$0") [--fix]

Commands:
  (no args)    Run ruff check + ruff format --check + mypy --strict
  --fix        Auto-fix ruff issues and format
  help         Show this help
EOF
    exit 1
}

FIX=false
if [ "${1:-}" = "--fix" ]; then
    FIX=true
    shift
fi

RC=0

if [ "$FIX" = true ]; then
    echo "Running ruff check --fix..."
    uv run ruff check --fix src/ tests/ || RC=1
    echo "Running ruff format..."
    uv run ruff format src/ tests/ || RC=1
else
    echo "Running ruff check..."
    uv run ruff check src/ tests/ || RC=1
    echo "Running ruff format --check..."
    uv run ruff format --check src/ tests/ || RC=1
fi

echo "Running mypy --strict..."
uv run mypy --strict src/ || RC=1

if [ $RC -eq 0 ]; then
    info "All checks passed"
else
    error "Some checks failed"
fi

exit $RC
