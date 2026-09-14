#!/usr/bin/env bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_ROOT/docker"

# shellcheck source=require-ubuntu-native-docker.sh
source "$SCRIPT_DIR/require-ubuntu-native-docker.sh"

# The Compose services and nested compile containers both need the same path as
# seen by the host Docker daemon. In WSL2 this is the WSL path to the checkout.
export DEER_FLOW_ROOT="${DEER_FLOW_ROOT:-$PROJECT_ROOT}"

# Load optional mirror and timeout settings used by Compose build arguments.
# The same file is also injected into services through compose env_file.
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Docker Compose command with project name
COMPOSE_CMD="docker compose -p deer-flow-dev -f docker-compose-dev.yaml"
if [ -n "${FORGE_MODEL_PROXY_UPSTREAM:-}" ]; then
    COMPOSE_CMD="$COMPOSE_CMD -f docker-compose-model-proxy.yaml"
fi
MODEL_PROXY_BRIDGE_SCRIPT="$SCRIPT_DIR/model_proxy_bridge.py"
MODEL_PROXY_BRIDGE_ACTIVE=false

start_model_proxy_bridge() {
    if [ -z "${FORGE_MODEL_PROXY_UPSTREAM:-}" ]; then
        return 0
    fi
    local bridge_port="${FORGE_MODEL_PROXY_BRIDGE_PORT:-17897}"
    python3 "$MODEL_PROXY_BRIDGE_SCRIPT" start \
        --upstream "$FORGE_MODEL_PROXY_UPSTREAM" \
        --listen-port "$bridge_port"
    export MODEL_RUNTIME_HTTP_PROXY="http://host.docker.internal:${bridge_port}"
    export MODEL_RUNTIME_HTTPS_PROXY="http://host.docker.internal:${bridge_port}"
    export MODEL_RUNTIME_NO_PROXY="${MODEL_RUNTIME_NO_PROXY:-localhost,127.0.0.1,gateway,langgraph,nginx,frontend,host.docker.internal}"
    MODEL_PROXY_BRIDGE_ACTIVE=true
}

stop_model_proxy_bridge() {
    python3 "$MODEL_PROXY_BRIDGE_SCRIPT" stop >/dev/null
}

detect_sandbox_mode() {
    local config_file="$PROJECT_ROOT/config.yaml"
    local sandbox_use=""
    local provisioner_url=""

    if [ ! -f "$config_file" ]; then
        echo "local"
        return
    fi

    sandbox_use=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*use:[[:space:]]*/ {
            line=$0
            sub(/^[[:space:]]*use:[[:space:]]*/, "", line)
            print line
            exit
        }
    ' "$config_file")

    provisioner_url=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*provisioner_url:[[:space:]]*/ {
            line=$0
            sub(/^[[:space:]]*provisioner_url:[[:space:]]*/, "", line)
            print line
            exit
        }
    ' "$config_file")

    if [[ "$sandbox_use" == *"deerflow.sandbox.local:LocalSandboxProvider"* ]]; then
        echo "local"
    elif [[ "$sandbox_use" == *"deerflow.community.aio_sandbox:AioSandboxProvider"* ]]; then
        if [ -n "$provisioner_url" ]; then
            echo "provisioner"
        else
            echo "aio"
        fi
    else
        echo "local"
    fi
}

# Cleanup function for Ctrl+C
cleanup() {
    echo ""
    echo -e "${YELLOW}Operation interrupted by user${NC}"
    if $MODEL_PROXY_BRIDGE_ACTIVE; then
        stop_model_proxy_bridge
    fi
    exit 130
}

# Set up trap for Ctrl+C
trap cleanup INT TERM

docker_available() {
    require_ubuntu_native_docker --quiet
}

# Initialize: pre-pull the sandbox image so first Pod startup is fast
init() {
    echo "=========================================="
    echo "  DeerFlow Init — Pull Sandbox Image"
    echo "=========================================="
    echo ""

    SANDBOX_IMAGE="enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest"

    # Detect sandbox mode from config.yaml
    local sandbox_mode
    sandbox_mode="$(detect_sandbox_mode)"

    # Skip image pull for local sandbox mode (no container image needed)
    if [ "$sandbox_mode" = "local" ]; then
        echo -e "${GREEN}Detected local sandbox mode — no Docker image required.${NC}"
        echo ""

        if docker_available; then
            echo -e "${GREEN}✓ Docker environment is ready.${NC}"
            echo ""
            echo -e "${YELLOW}Next step: make docker-start${NC}"
        else
            echo -e "${YELLOW}Docker does not appear to be installed, or the Docker daemon is not reachable.${NC}"
            echo "Local sandbox mode itself does not require Docker, but Docker-based workflows (e.g., docker-start) will fail until Docker is available."
            echo ""
            echo -e "${YELLOW}Install and start Docker, then run: make docker-init && make docker-start${NC}"
        fi

        return 0
    fi

    if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${SANDBOX_IMAGE}$"; then
        echo -e "${BLUE}Pulling sandbox image: $SANDBOX_IMAGE ...${NC}"
        echo ""

        if ! docker pull "$SANDBOX_IMAGE" 2>&1; then
            echo ""
            echo -e "${YELLOW}⚠ Failed to pull sandbox image.${NC}"
            echo ""
            echo "This is expected if:"
            echo "  1. You are using local sandbox mode (default — no image needed)"
            echo "  2. You are behind a corporate proxy or firewall"
            echo "  3. The registry requires authentication"
            echo ""
            echo -e "${GREEN}The Docker development environment can still be started.${NC}"
            echo "If you need AIO sandbox (container-based execution):"
            echo "  - Ensure you have network access to the registry"
            echo "  - Or configure a custom sandbox image in config.yaml"
            echo ""
            echo -e "${YELLOW}Next step: make docker-start${NC}"
            return 0
        fi
    else
        echo -e "${GREEN}Sandbox image already exists locally: $SANDBOX_IMAGE${NC}"
    fi

    echo ""
    echo -e "${GREEN}✓ Sandbox image is ready.${NC}"
    echo ""
    echo -e "${YELLOW}Next step: make docker-start${NC}"
}

# Start Docker development environment
# Usage: start [--gateway]
start() {
    local sandbox_mode
    local services
    local gateway_mode=false

    # Check for --gateway flag
    for arg in "$@"; do
        if [ "$arg" = "--gateway" ]; then
            gateway_mode=true
        fi
    done

    echo "=========================================="
    echo "  Starting DeerFlow Docker Development"
    echo "=========================================="
    echo ""

    if ! docker_available; then
        echo -e "${YELLOW}The required Ubuntu native Docker Engine is not ready.${NC}"
        echo "Ask the user to restore Ubuntu docker.service, then rerun: make docker-start"
        exit 1
    fi

    mkdir -p "$PROJECT_ROOT/.compile-sessions"
    start_model_proxy_bridge

    sandbox_mode="$(detect_sandbox_mode)"

    if $gateway_mode; then
        services="frontend gateway nginx"
        if [ "$sandbox_mode" = "provisioner" ]; then
            services="frontend gateway provisioner nginx"
        fi
    else
        services="frontend gateway langgraph nginx"
        if [ "$sandbox_mode" = "provisioner" ]; then
            services="frontend gateway langgraph provisioner nginx"
        fi
    fi

    if $gateway_mode; then
        echo -e "${BLUE}Runtime: Gateway mode (experimental) — no LangGraph container${NC}"
    fi
    echo -e "${BLUE}Detected sandbox mode: $sandbox_mode${NC}"
    if [ "$sandbox_mode" = "provisioner" ]; then
        echo -e "${BLUE}Provisioner enabled (Kubernetes mode).${NC}"
    else
        echo -e "${BLUE}Provisioner disabled (not required for this sandbox mode).${NC}"
    fi
    echo ""
    
    echo -e "${BLUE}Host workspace root: $DEER_FLOW_ROOT${NC}"
    echo ""
    
    # Ensure config.yaml exists before starting.
    if [ ! -f "$PROJECT_ROOT/config.yaml" ]; then
        if [ -f "$PROJECT_ROOT/config.example.yaml" ]; then
            cp "$PROJECT_ROOT/config.example.yaml" "$PROJECT_ROOT/config.yaml"
            echo ""
            echo -e "${YELLOW}============================================================${NC}"
            echo -e "${YELLOW}  config.yaml has been created from config.example.yaml.${NC}"
            echo -e "${YELLOW}  Please edit config.yaml to set your API keys and model   ${NC}"
            echo -e "${YELLOW}  configuration before starting DeerFlow.                  ${NC}"
            echo -e "${YELLOW}============================================================${NC}"
            echo ""
            echo -e "${YELLOW}  Edit the file:  $PROJECT_ROOT/config.yaml${NC}"
            echo -e "${YELLOW}  Then run:        make docker-start${NC}"
            echo ""
            exit 0
        else
            echo -e "${YELLOW}✗ config.yaml not found and no config.example.yaml to copy from.${NC}"
            exit 1
        fi
    fi

    # Ensure extensions_config.json exists as a file before mounting.
    # Docker creates a directory when bind-mounting a non-existent host path.
    if [ ! -f "$PROJECT_ROOT/extensions_config.json" ]; then
        if [ -f "$PROJECT_ROOT/extensions_config.example.json" ]; then
            cp "$PROJECT_ROOT/extensions_config.example.json" "$PROJECT_ROOT/extensions_config.json"
            echo -e "${BLUE}Created extensions_config.json from example${NC}"
        else
            echo "{}" > "$PROJECT_ROOT/extensions_config.json"
            echo -e "${BLUE}Created empty extensions_config.json${NC}"
        fi
    fi

    # Set nginx routing for gateway mode (envsubst in nginx container)
    if $gateway_mode; then
        export LANGGRAPH_UPSTREAM=gateway:8001
        export LANGGRAPH_REWRITE=/api/
    fi

    echo "Building and starting containers..."
    if ! (cd "$DOCKER_DIR" && $COMPOSE_CMD up --build -d --remove-orphans $services); then
        if $MODEL_PROXY_BRIDGE_ACTIVE; then
            stop_model_proxy_bridge
        fi
        exit 1
    fi
    echo ""
    echo "=========================================="
    echo "  DeerFlow Docker is starting!"
    echo "=========================================="
    echo ""
    echo "  🌐 Application: http://localhost:8000"
    echo "  📡 API Gateway: http://localhost:8000/api/*"
    if $gateway_mode; then
        echo "  🤖 Runtime:     Gateway embedded"
        echo "  API:            /api/langgraph/* → Gateway (compat)"
    else
        echo "  🤖 LangGraph:   http://localhost:8000/api/langgraph/*"
    fi
    echo ""
    echo "  📋 View logs: make docker-logs"
    echo "  🛑 Stop:      make docker-stop"
    echo ""
}

# View Docker development logs
logs() {
    local service=""
    
    case "$1" in
        --frontend)
            service="frontend"
            echo -e "${BLUE}Viewing frontend logs...${NC}"
            ;;
        --gateway)
            service="gateway"
            echo -e "${BLUE}Viewing gateway logs...${NC}"
            ;;
        --nginx)
            service="nginx"
            echo -e "${BLUE}Viewing nginx logs...${NC}"
            ;;
        --provisioner)
            service="provisioner"
            echo -e "${BLUE}Viewing provisioner logs...${NC}"
            ;;
        "")
            echo -e "${BLUE}Viewing all logs...${NC}"
            ;;
        *)
            echo -e "${YELLOW}Unknown option: $1${NC}"
            echo "Usage: $0 logs [--frontend|--gateway|--nginx|--provisioner]"
            exit 1
            ;;
    esac
    
    cd "$DOCKER_DIR" && $COMPOSE_CMD logs -f $service
}

# Stop Docker development environment
stop() {
    # DEER_FLOW_ROOT is referenced in docker-compose-dev.yaml; set it before
    # running compose down to suppress "variable is not set" warnings.
    if [ -z "$DEER_FLOW_ROOT" ]; then
        export DEER_FLOW_ROOT="$PROJECT_ROOT"
    fi
    echo "Stopping Docker development services..."
    cd "$DOCKER_DIR" && $COMPOSE_CMD down
    echo "Cleaning up sandbox containers..."
    "$SCRIPT_DIR/cleanup-containers.sh" deer-flow-sandbox 2>/dev/null || true
    stop_model_proxy_bridge
    echo -e "${GREEN}✓ Docker services stopped${NC}"
}

# Restart Docker development environment
restart() {
    echo "========================================"
    echo "  Restarting DeerFlow Docker Services"
    echo "========================================"
    echo ""
    start_model_proxy_bridge
    echo -e "${BLUE}Restarting containers...${NC}"
    cd "$DOCKER_DIR" && $COMPOSE_CMD restart
    echo ""
    echo -e "${GREEN}✓ Docker services restarted${NC}"
    echo ""
    echo "  🌐 Application: http://localhost:8000"
    echo "  📋 View logs: make docker-logs"
    echo ""
}

model_preflight() {
    local provider="${1:-richlab}"
    local runtime_container="deer-flow-langgraph"
    local proxy_args=()
    if ! docker inspect "$runtime_container" >/dev/null 2>&1; then
        runtime_container="deer-flow-gateway"
    fi
    if ! docker inspect "$runtime_container" >/dev/null 2>&1; then
        echo -e "${YELLOW}No Forge runtime container is available. Run make docker-start first.${NC}"
        exit 1
    fi
    start_model_proxy_bridge
    if [ -n "${MODEL_RUNTIME_HTTP_PROXY:-}" ]; then
        proxy_args+=("-e" "HTTP_PROXY=$MODEL_RUNTIME_HTTP_PROXY")
        proxy_args+=("-e" "HTTPS_PROXY=$MODEL_RUNTIME_HTTPS_PROXY")
        proxy_args+=("-e" "NO_PROXY=$MODEL_RUNTIME_NO_PROXY")
    fi
    docker exec "${proxy_args[@]}" "$runtime_container" \
        /app/backend/.venv/bin/python /app/scripts/model_provider_preflight.py \
        --provider "$provider"
}

# Show help
help() {
    echo "DeerFlow Docker Management Script"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  init              - Pull the sandbox image (speeds up first Pod startup)"
    echo "  start             - Start Docker services (auto-detects sandbox mode from config.yaml)"
    echo "  start --gateway   - Start without LangGraph container (Gateway mode, experimental)"
    echo "  restart           - Restart all running Docker services"
    echo "  model-preflight [richlab|deepseek] - Run bounded provider connectivity checks"
    echo "  logs [option] - View Docker development logs"
    echo "                  --frontend   View frontend logs only"
    echo "                  --gateway    View gateway logs only"
    echo "                  --nginx      View nginx logs only"
    echo "                  --provisioner View provisioner logs only"
    echo "  stop          - Stop Docker development services"
    echo "  help          - Show this help message"
    echo ""
}

main() {
    case "${1:-}" in
        init|start|restart|model-preflight|logs|stop)
            require_ubuntu_native_docker
            ;;
    esac

    # Main command dispatcher
    case "$1" in
        init)
            init
            ;;
        start)
            shift
            start "$@"
            ;;
        restart)
            restart
            ;;
        model-preflight)
            model_preflight "$2"
            ;;
        logs)
            logs "$2"
            ;;
        stop)
            stop
            ;;
        help|--help|-h|"")
            help
            ;;
        *)
            echo -e "${YELLOW}Unknown command: $1${NC}"
            echo ""
            help
            exit 1
            ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
