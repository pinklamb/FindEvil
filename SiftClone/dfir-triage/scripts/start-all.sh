#!/usr/bin/env bash
set -euo pipefail

CASE_ID="${1:-CASE-FRONTEND-001}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
KEEP_GENERATED_DATA="${KEEP_GENERATED_DATA:-0}"

echo "== Traceable DFIR startup =="
echo "Project: $ROOT"
echo "Default case ID: $CASE_ID"
echo

if [[ "$KEEP_GENERATED_DATA" != "1" ]]; then
  echo "Resetting generated demo data..."
  ./scripts/clean-generated.sh
fi

echo "Building custom SIFT worker image..."
docker compose build sift-worker-image

echo "Starting backend services..."
docker compose up -d --build ollama mcp

echo "Waiting for backend API..."
ready=0
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:8000/api/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" != "1" ]]; then
  echo "Backend API did not become ready at http://localhost:8000/api/health" >&2
  exit 1
fi

echo "Backend ready."
echo "Evidence files will be listed from the evidence folder in the UI."

if [[ ! -d frontend/node_modules ]] || ! (cd frontend && npm exec vite -- --version >/dev/null 2>&1); then
  echo "Installing frontend dependencies with npm install..."
  (cd frontend && npm install)
fi

echo
echo "Ready."
echo "API:       http://localhost:8000/api/health"
echo "Frontend: http://localhost:5174"
echo
echo "Starting Vite. Press Ctrl+C to stop the frontend dev server."
echo

cd frontend
npm run dev
