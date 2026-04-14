#!/usr/bin/env bash
#
# cleanup-containers.sh - Clean up DeerFlow containers by name prefix
#
# This script cleans up both Docker and Apple Container runtime containers
# to ensure compatibility across different container runtimes.
#

set -e

PREFIX="${1:-deer-flow-sandbox}"
REMOVE_MODE="${2:-remove}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Cleaning up containers with prefix: ${PREFIX}"

cleanup_docker() {
    if command -v docker &> /dev/null; then
        echo -n "Checking Docker containers... "
        DOCKER_CONTAINERS=$(docker ps -aq --filter "name=${PREFIX}" 2>/dev/null || echo "")

        if [ -n "$DOCKER_CONTAINERS" ]; then
            echo ""
            echo "Found Docker containers to clean up:"
            docker ps -a --filter "name=${PREFIX}" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}"
            if [ "$REMOVE_MODE" = "remove" ]; then
                echo "Removing Docker containers..."
                echo "$DOCKER_CONTAINERS" | xargs docker rm -f 2>/dev/null || true
                echo -e "${GREEN}✓ Docker containers removed${NC}"
            else
                echo "Stopping Docker containers..."
                echo "$DOCKER_CONTAINERS" | xargs docker stop 2>/dev/null || true
                echo -e "${GREEN}✓ Docker containers stopped${NC}"
            fi
        else
            echo -e "${GREEN}none found${NC}"
        fi
    else
        echo "Docker not found, skipping..."
    fi
}

cleanup_apple_container() {
    if command -v container &> /dev/null; then
        echo -n "Checking Apple Container containers... "
        CONTAINER_LIST=$(container list --format json 2>/dev/null || echo "[]")

        if [ "$CONTAINER_LIST" != "[]" ] && [ -n "$CONTAINER_LIST" ]; then
            CONTAINER_IDS=$(echo "$CONTAINER_LIST" | python3 -c "
import json
import sys
try:
    containers = json.load(sys.stdin)
    if isinstance(containers, list):
        for c in containers:
            if isinstance(c, dict):
                cid = c.get('configuration').get('id', '')
                if '${PREFIX}' in cid:
                    print(cid)
except:
    pass
" 2>/dev/null || echo "")

            if [ -n "$CONTAINER_IDS" ]; then
                echo ""
                echo "Found Apple Container containers to clean up:"
                echo "$CONTAINER_IDS" | while read -r cid; do
                    echo "  - $cid"
                done

                if [ "$REMOVE_MODE" = "remove" ]; then
                    echo "Removing Apple Container containers..."
                    echo "$CONTAINER_IDS" | while read -r cid; do
                        container rm -f "$cid" 2>/dev/null || container stop "$cid" 2>/dev/null || true
                    done
                    echo -e "${GREEN}✓ Apple Container containers removed${NC}"
                else
                    echo "Stopping Apple Container containers..."
                    echo "$CONTAINER_IDS" | while read -r cid; do
                        container stop "$cid" 2>/dev/null || true
                    done
                    echo -e "${GREEN}✓ Apple Container containers stopped${NC}"
                fi
            else
                echo -e "${GREEN}none found${NC}"
            fi
        else
            echo -e "${GREEN}none found${NC}"
        fi
    else
        echo "Apple Container not found, skipping..."
    fi
}

cleanup_docker
cleanup_apple_container

echo -e "${GREEN}✓ Container cleanup complete${NC}"
