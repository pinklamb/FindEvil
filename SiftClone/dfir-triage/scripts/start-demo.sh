#!/usr/bin/env bash
set -euo pipefail

CASE_ID="${1:-CASE-FRONTEND-001}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

docker compose build sift-worker-image
docker compose up -d --build ollama mcp

python - <<PY
import sys
sys.path.insert(0, "dfir_backend")
from server import create_suspicious_test_case, check_llm_status
print(create_suspicious_test_case("${CASE_ID}"))
print(check_llm_status())
PY

echo
echo "Demo backend is ready."
echo "MCP server container: dfir-mcp"
echo "Ollama: http://localhost:11434"
echo "API: http://localhost:8000/api/health"
echo "Demo case: ${CASE_ID}"
echo
echo "Frontend:"
echo "  cd frontend"
echo "  npm install"
echo "  npm run dev"
