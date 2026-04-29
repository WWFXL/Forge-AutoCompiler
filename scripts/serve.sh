#!/usr/bin/env bash
#
# serve.sh — Unified DeerFlow service launcher
#
# Usage:
#   ./scripts/serve.sh [--dev|--prod] [--gateway] [--daemon] [--stop|--restart]
#
# Modes:
#   --dev       Development mode with hot-reload (default)
#   --prod      Production mode, pre-built frontend, no hot-reload
#   --gateway   Gateway mode (experimental): skip LangGraph server,
#               agent runtime embedded in Gateway API
#   --daemon    Run all services in background (nohup), exit after startup
#
# Actions:
#   --skip-install  Skip dependency installation (faster restart)
#   --stop      Stop all running services and exit
#   --restart   Stop all services, then start with the given mode flags
#
# Examples:
#   ./scripts/serve.sh --dev                 # Standard dev (4 processes)
#   ./scripts/serve.sh --dev --gateway       # Gateway dev  (3 processes)
#   ./scripts/serve.sh --prod --gateway      # Gateway prod (3 processes)
#   ./scripts/serve.sh --dev --daemon        # Standard dev, background
#   ./scripts/serve.sh --dev --gateway --daemon  # Gateway dev, background
#   ./scripts/serve.sh --stop                # Stop all services
#   ./scripts/serve.sh --restart --dev --gateway # Restart in gateway mode
#
# Must be run from the repo root directory.

set -e

REPO_ROOT="$(builtin cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd -P)"
cd "$REPO_ROOT"

if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

DEV_MODE=true
GATEWAY_MODE=false
DAEMON_MODE=false
SKIP_INSTALL=false
ACTION="start"

for arg in "$@"; do
    case "$arg" in
        --dev)     DEV_MODE=true ;;
        --prod)    DEV_MODE=false ;;
        --gateway) GATEWAY_MODE=true ;;
        --daemon)  DAEMON_MODE=true ;;
        --skip-install) SKIP_INSTALL=true ;;
        --stop)    ACTION="stop" ;;
        --restart) ACTION="restart" ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--dev|--prod] [--gateway] [--daemon] [--skip-install] [--stop|--restart]"
            exit 1
            ;;
    esac
done

stop_all() {
    echo "Stopping all services..."
    pkill -f "langgraph dev" 2>/dev/null || true
    pkill -f "uvicorn app.gateway.app:app" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "next start" 2>/dev/null || true
    pkill -f "next-server" 2>/dev/null || true
    nginx -c "$REPO_ROOT/docker/nginx/nginx.local.conf" -p "$REPO_ROOT" -s quit 2>/dev/null || true
    sleep 1
    pkill -9 nginx 2>/dev/null || true
    ./scripts/cleanup-containers.sh deer-flow-sandbox remove 2>/dev/null || true
    ./scripts/cleanup-containers.sh deerflow-compile remove 2>/dev/null || true
    echo "✓ All services stopped"
}

if [ "$ACTION" = "stop" ]; then
    stop_all
    exit 0
fi

ALREADY_STOPPED=false
if [ "$ACTION" = "restart" ]; then
    stop_all
    sleep 1
    ALREADY_STOPPED=true
fi

if $GATEWAY_MODE; then
    export SKIP_LANGGRAPH_SERVER=1
fi

if $DEV_MODE && $GATEWAY_MODE; then
    MODE_LABEL="DEV + GATEWAY (experimental)"
elif $DEV_MODE; then
    MODE_LABEL="DEV (hot-reload enabled)"
elif $GATEWAY_MODE; then
    MODE_LABEL="PROD + GATEWAY (experimental)"
else
    MODE_LABEL="PROD (optimized)"
fi

if $DAEMON_MODE; then
    MODE_LABEL="$MODE_LABEL [daemon]"
fi

if $DEV_MODE; then
    FRONTEND_CMD="pnpm run dev"
else
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    else
        echo "Python is required to generate BETTER_AUTH_SECRET."
        exit 1
    fi
    FRONTEND_CMD="env BETTER_AUTH_SECRET=$($PYTHON_BIN -c 'import secrets; print(secrets.token_hex(16))') pnpm run preview"
fi

LANGGRAPH_EXTRA_FLAGS="--no-reload"
if $DEV_MODE && ! $DAEMON_MODE; then
    GATEWAY_EXTRA_FLAGS="--reload --reload-include='*.yaml' --reload-include='.env' --reload-exclude='*.pyc' --reload-exclude='__pycache__' --reload-exclude='sandbox/' --reload-exclude='.deer-flow/'"
else
    GATEWAY_EXTRA_FLAGS=""
fi

if ! $ALREADY_STOPPED; then
    stop_all
    sleep 1
fi

if ! { \
        [ -n "$DEER_FLOW_CONFIG_PATH" ] && [ -f "$DEER_FLOW_CONFIG_PATH" ] || \
        [ -f backend/config.yaml ] || \
        [ -f config.yaml ]; \
    }; then
    echo "✗ No DeerFlow config file found."
    echo "  Run 'make config' to generate config.yaml."
    exit 1
fi

"$REPO_ROOT/scripts/config-upgrade.sh"

if ! $SKIP_INSTALL; then
    echo "Syncing dependencies..."
    (cd backend && uv sync --quiet) || { echo "✗ Backend dependency install failed"; exit 1; }
    (cd frontend && pnpm install --silent) || { echo "✗ Frontend dependency install failed"; exit 1; }
    echo "✓ Dependencies synced"
else
    echo "⏩ Skipping dependency install (--skip-install)"
fi

FRONTEND_ENV_LOCAL="$REPO_ROOT/frontend/.env.local"
ENV_KEY="NEXT_PUBLIC_LANGGRAPH_BASE_URL"

sync_frontend_env() {
    if $GATEWAY_MODE; then
        if [ -f "$FRONTEND_ENV_LOCAL" ] && grep -q "^${ENV_KEY}=" "$FRONTEND_ENV_LOCAL"; then
            sed -i.bak "s|^${ENV_KEY}=.*|${ENV_KEY}=/api/langgraph-compat|" "$FRONTEND_ENV_LOCAL" && rm -f "${FRONTEND_ENV_LOCAL}.bak"
        else
            echo "${ENV_KEY}=/api/langgraph-compat" >> "$FRONTEND_ENV_LOCAL"
        fi
    else
        if [ -f "$FRONTEND_ENV_LOCAL" ] && grep -q "^${ENV_KEY}=" "$FRONTEND_ENV_LOCAL"; then
            sed -i.bak "/^${ENV_KEY}=/d" "$FRONTEND_ENV_LOCAL" && rm -f "${FRONTEND_ENV_LOCAL}.bak"
        fi
    fi
}

sync_frontend_env

echo ""
echo "=========================================="
echo "  Starting DeerFlow"
echo "=========================================="
echo ""
echo "  Mode: $MODE_LABEL"
echo ""
echo "  Services:"
if ! $GATEWAY_MODE; then
    echo "    LangGraph   → localhost:2024  (agent runtime)"
fi
echo "    Gateway     → localhost:8001  (REST API$(if $GATEWAY_MODE; then echo " + agent runtime"; fi))"
echo "    Frontend    → localhost:3000  (Next.js)"
echo "    Nginx       → localhost:8000  (reverse proxy)"
echo ""

cleanup() {
    trap - INT TERM
    echo ""
    stop_all
    exit 0
}

trap cleanup INT TERM

run_service() {
    local name="$1" cmd="$2" port="$3" timeout="$4"

    echo "Starting $name..."
    if $DAEMON_MODE; then
        nohup sh -c "$cmd" > /dev/null 2>&1 &
    else
        sh -c "$cmd" &
    fi

    ./scripts/wait-for-port.sh "$port" "$timeout" "$name" || {
        local logfile="logs/$(echo "$name" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')".log
        echo "✗ $name failed to start."
        [ -f "$logfile" ] && tail -20 "$logfile"
        cleanup
    }
    echo "✓ $name started on localhost:$port"
}

mkdir -p logs
mkdir -p temp/client_body_temp temp/proxy_temp temp/fastcgi_temp temp/uwsgi_temp temp/scgi_temp

if ! $GATEWAY_MODE; then
    CONFIG_LOG_LEVEL=$(grep -m1 '^log_level:' config.yaml 2>/dev/null | awk '{print $2}' | tr -d ' ')
    LANGGRAPH_LOG_LEVEL="${LANGGRAPH_LOG_LEVEL:-${CONFIG_LOG_LEVEL:-info}}"
    LANGGRAPH_JOBS_PER_WORKER="${LANGGRAPH_JOBS_PER_WORKER:-10}"
    LANGGRAPH_ALLOW_BLOCKING="${LANGGRAPH_ALLOW_BLOCKING:-0}"
    LANGGRAPH_ALLOW_BLOCKING_FLAG=""
    if [ "$LANGGRAPH_ALLOW_BLOCKING" = "1" ]; then
        LANGGRAPH_ALLOW_BLOCKING_FLAG="--allow-blocking"
    fi
    run_service "LangGraph" \
        "cd backend && NO_COLOR=1 uv run langgraph dev --no-browser $LANGGRAPH_ALLOW_BLOCKING_FLAG --n-jobs-per-worker $LANGGRAPH_JOBS_PER_WORKER --server-log-level $LANGGRAPH_LOG_LEVEL $LANGGRAPH_EXTRA_FLAGS > ../logs/langgraph.log 2>&1" \
        2024 60
else
    echo "⏩ Skipping LangGraph (Gateway mode — runtime embedded in Gateway)"
fi

run_service "Gateway" \
    "cd backend && PYTHONPATH=. uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 $GATEWAY_EXTRA_FLAGS > ../logs/gateway.log 2>&1" \
    8001 30

run_service "Frontend" \
    "cd frontend && $FRONTEND_CMD > ../logs/frontend.log 2>&1" \
    3000 120

run_service "Nginx" \
    "nginx -g 'daemon off;' -c '$REPO_ROOT/docker/nginx/nginx.local.conf' -p '$REPO_ROOT' > logs/nginx.log 2>&1" \
    8000 10

echo ""
echo "=========================================="
echo "  ✓ DeerFlow is running!  [$MODE_LABEL]"
echo "=========================================="
echo ""
echo "  🌐 http://localhost:8000"
echo ""
if $GATEWAY_MODE; then
    echo "  Routing: Frontend → Nginx → Gateway (embedded runtime)"
    echo "  API:     /api/langgraph-compat/*  →  Gateway agent runtime"
else
    echo "  Routing: Frontend → Nginx → LangGraph + Gateway"
    echo "  API:     /api/langgraph/*  →  LangGraph server (2024)"
fi
echo "           /api/*              →  Gateway REST API (8001)"
echo ""
echo "  📋 Logs: logs/{langgraph,gateway,frontend,nginx}.log"
echo ""

if $DAEMON_MODE; then
    echo "  🛑 Stop: make stop"
    trap - INT TERM
else
    echo "  Press Ctrl+C to stop all services"
    wait
fi
