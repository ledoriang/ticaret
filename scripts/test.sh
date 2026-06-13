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
error() { echo -e "${RED}[✗]${NC} $*"; }

usage() {
    cat <<EOF
Usage: $(basename "$0") [options] [-- <pytest-args>]

Options:
  --cov        Include coverage report (implies --cov=trading)
  --help       Show this help

Any arguments after -- are forwarded to pytest.
EOF
    exit 1
}

COV=false
PYTEST_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --cov)
            COV=true
            shift
            ;;
        --help|-h)
            usage
            ;;
        --)
            shift
            PYTEST_ARGS+=("$@")
            break
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

if [ "$COV" = true ]; then
    PYTEST_ARGS+=( "--cov=trading" "--cov-report=term-missing" )
fi

echo "Running pytest${COV:+ with coverage}..."
uv run pytest "${PYTEST_ARGS[@]}" && info "All tests passed"
