#!/usr/bin/env bash
# Build (if needed) and run the FinAlly Docker container.
# Idempotent: safe to run multiple times.
#
# Usage:
#   ./scripts/start_mac.sh           # run with existing image
#   ./scripts/start_mac.sh --build   # force rebuild before running
#   ./scripts/start_mac.sh --open    # open http://localhost:8000 after start

set -euo pipefail

IMAGE_NAME="finally"
CONTAINER_NAME="finally"
VOLUME_NAME="finally-data"
PORT=8000

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FORCE_BUILD=0
OPEN_BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --build) FORCE_BUILD=1 ;;
    --open)  OPEN_BROWSER=1 ;;
    -h|--help)
      sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed or not on PATH." >&2
  exit 1
fi

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    echo "No .env found. Copy .env.example to .env and fill in your keys:"
    echo "  cp .env.example .env"
  else
    echo "ERROR: .env not found and no .env.example to copy." >&2
  fi
  exit 1
fi

if [ "$FORCE_BUILD" -eq 1 ] || ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  echo "Building Docker image: $IMAGE_NAME"
  docker build -t "$IMAGE_NAME" .
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
  echo "Removing existing container: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

echo "Starting container: $CONTAINER_NAME"
docker run -d \
  --name "$CONTAINER_NAME" \
  -p "${PORT}:8000" \
  -v "${VOLUME_NAME}:/app/db" \
  --env-file .env \
  "$IMAGE_NAME" >/dev/null

URL="http://localhost:${PORT}"
echo "FinAlly is starting at ${URL}"

if [ "$OPEN_BROWSER" -eq 1 ]; then
  if command -v open >/dev/null 2>&1; then
    open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL"
  fi
fi
