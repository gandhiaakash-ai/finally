#!/usr/bin/env bash
# Stop and remove the FinAlly container.
# The Docker volume (finally-data) is preserved so portfolio data persists.
# Idempotent: safe to run when the container is already stopped or absent.

set -euo pipefail

CONTAINER_NAME="finally"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed or not on PATH." >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
  echo "Stopping container: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
  echo "Stopped. Volume 'finally-data' is preserved."
else
  echo "Container '$CONTAINER_NAME' is not running."
fi
