#!/bin/bash
# Start the Agent Hypervisor Playground
# Usage: bash playground/run.sh [port]

PORT=${1:-8000}
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export PYTHONPATH="$REPO_ROOT/src"

echo "Agent Hypervisor Playground"
echo "  http://localhost:$PORT"
echo ""

uvicorn playground.api.server:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --reload
