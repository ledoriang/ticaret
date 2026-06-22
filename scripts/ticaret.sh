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
Usage: $(basename "$0") <command> [options]

Dev CLI shorthand for the trading stack.

Container management:
  up                Start all containers (builds trading-engine image if needed)
  down              Tear down all containers
  build             Build (or rebuild) the trading-engine Docker image
  restart           Down then up
  logs [service]    Tail docker logs
  status            Show container states
  reset-db          Destroy timescaledb volume and recreate

Linting & testing:
  lint              Run ruff check + format check + mypy --strict
  fmt               Auto-fix ruff issues and format
  test [opts]       Run pytest (forwards extra args, use -- before pytest opts)
  check             Lint + test (full CI gate)

Database:
  db init [opts]    Create TimescaleDB schema
  db seed [opts]    Seed historical data
  db backfill [opts] Bulk data import

Data:
  seed [opts]       Shortcut for db seed
  backfill [opts]   Shortcut for db backfill

Trading:
  backtest [opts]   Run backtest (forwards args to trading CLI)
  paper-trade [opts] Paper-trade a strategy via paper adapter
  sentiment-ingest  Run sentiment ingester
  list-strategies   List registered strategies
  shell             Drop into Python REPL with trading package
  setup             Initial project setup (Python install, deps sync, rust stub build)

Testing:
  test-infra [opts] Run infra tests via Docker test profile (forwards pytest args)
  test-trading [opts] Run trading tests via Docker test profile (forwards pytest args)

Other:
  help              Show this help

Examples:
  ./scripts/ticaret.sh up
  ./scripts/ticaret.sh lint
  ./scripts/ticaret.sh test -- -v tests/unit/
  ./scripts/ticaret.sh test --cov
  ./scripts/ticaret.sh check
  ./scripts/ticaret.sh backtest --symbol BTC/USDT
  ./scripts/ticaret.sh setup
EOF
    exit 1
}

# Ensure docker compose is available for container commands
check_docker() {
    if ! command -v docker &>/dev/null; then
        error "docker is not installed"
        exit 1
    fi
}

case "${1:-help}" in
    up)
        check_docker
        exec "$SCRIPT_DIR/docker.sh" up
        ;;
    down)
        check_docker
        exec "$SCRIPT_DIR/docker.sh" down
        ;;
    build)
        check_docker
        exec "$SCRIPT_DIR/docker.sh" build
        ;;
    restart)
        check_docker
        exec "$SCRIPT_DIR/docker.sh" restart
        ;;
    logs)
        check_docker
        shift
        exec "$SCRIPT_DIR/docker.sh" logs "$@"
        ;;
    status)
        check_docker
        exec "$SCRIPT_DIR/docker.sh" status
        ;;
    reset-db)
        check_docker
        exec "$SCRIPT_DIR/docker.sh" reset-db
        ;;
    lint)
        exec "$SCRIPT_DIR/lint.sh"
        ;;
    fmt)
        exec "$SCRIPT_DIR/lint.sh" --fix
        ;;
    test)
        shift
        exec "$SCRIPT_DIR/test.sh" "$@"
        ;;
    check)
        "$SCRIPT_DIR/lint.sh" && "$SCRIPT_DIR/test.sh"
        ;;
    db)
        shift
        exec "$SCRIPT_DIR/db.sh" "$@"
        ;;
    seed)
        shift
        exec "$SCRIPT_DIR/db.sh" seed "$@"
        ;;
    backfill)
        shift
        exec "$SCRIPT_DIR/db.sh" backfill "$@"
        ;;
    backtest)
        shift
        if [[ $# -gt 0 && "$1" == "--" ]]; then
            shift
        fi
        uv run trading backtest "$@"
        ;;
    paper-trade|papertrade)
        shift
        uv run trading paper-trade "$@"
        ;;
    sentiment-ingest)
        shift
        uv run trading sentiment-ingest "$@"
        ;;
    list-strategies|strategies)
        uv run trading list-strategies
        ;;
    test-infra)
        shift
        check_docker
        docker compose --profile test run --rm test-runner tests/infra/ "$@"
        ;;
    test-trading)
        shift
        check_docker
        docker compose --profile test run --rm test-runner tests/trading/ "$@"
    shell)
        uv run python -c "import trading; print('trading package imported successfully')" && uv run python
        ;;
    setup)
        echo "Setting up project..."
        echo "  Installing Python 3.12..."
        uv python install 3.12
        echo "  Syncing dependencies..."
        uv sync
        echo "  Building rust_kernel stub..."
        if command -v cargo &>/dev/null; then
            (cd src/trading/rust_kernel && uv run maturin develop --release 2>/dev/null || warn "rust_kernel build skipped (maturin/cargo not available)")
        else
            warn "cargo not found — rust_kernel stub will use Python fallback"
        fi
        info "Setup complete"
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        error "Unknown command: $1"
        usage
        ;;
esac
