#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; }

usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [options]

Commands:
  init              Create TimescaleDB schema (hypertables)
  seed [opts]       Seed historical data (passes opts to seed script)
  backfill [opts]   Bulk import data (passes opts to backfill script)
  help              Show this help
EOF
    exit 1
}

case "${1:-help}" in
    init)
        shift
        uv run python scripts/py/db_init.py "$@" && info "Schema initialized"
        ;;
    seed)
        shift
        uv run python scripts/py/seed_historical_data.py "$@" && info "Data seeded"
        ;;
    backfill)
        shift
        uv run python scripts/py/backfill_timescaledb.py "$@" && info "Backfill complete"
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        error "Unknown command: $1"
        usage
        ;;
esac
