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
Usage: $(basename "$0") <command>

Commands:
  up             Start all containers, wait for health (builds if needed)
  build          Build (or rebuild) the trading-engine image
  down           Tear down all containers
  restart        Down then up
  logs [svc]    Tail logs (all services or specific one)
  status         Show container states
  reset-db       Destroy timescaledb volume and recreate
  help           Show this help
EOF
    exit 1
}

healthcheck() {
    local service="$1"
    local max=30
    local count=0
    while [ $count -lt $max ]; do
        case "$service" in
            redis)
                if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
                    info "redis is healthy"
                    return 0
                fi
                ;;
            timescaledb)
                if docker compose exec -T timescaledb pg_isready -U trading -d trading 2>/dev/null | grep -q "accepting"; then
                    info "timescaledb is healthy"
                    return 0
                fi
                ;;
            prometheus)
                if curl -sf http://localhost:9090/-/healthy >/dev/null 2>&1; then
                    info "prometheus is healthy"
                    return 0
                fi
                ;;
            grafana)
                if curl -sf http://localhost:3000/api/health >/dev/null 2>&1; then
                    info "grafana is healthy"
                    return 0
                fi
                ;;
            trading)
                if curl -sf http://localhost:8000/-/healthy >/dev/null 2>&1; then
                    info "trading-engine is healthy"
                    return 0
                fi
                ;;
        esac
        count=$((count + 1))
        sleep 1
    done
    error "$service failed health check after ${max}s"
    return 1
}

case "${1:-help}" in
    up)
        echo "Starting containers..."
        docker compose up -d --build
        echo "Waiting for services to become healthy..."
        healthcheck redis
        healthcheck timescaledb
        healthcheck trading
        healthcheck prometheus
        healthcheck grafana
        info "All containers are up and healthy"
        ;;
    build)
        docker compose build trading
        info "trading-engine image built"
        ;;
    down)
        docker compose down
        info "Containers stopped"
        ;;
    restart)
        "$0" down
        "$0" up
        ;;
    logs)
        shift
        docker compose logs -f "$@"
        ;;
    status)
        docker compose ps
        ;;
    reset-db)
        warn "This will DESTROY the timescaledb volume!"
        read -rp "Are you sure? (y/N) " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            docker compose down -v
            info "Volume destroyed. Run '$0 up' to recreate."
        else
            info "Cancelled"
        fi
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        error "Unknown command: $1"
        usage
        ;;
esac
