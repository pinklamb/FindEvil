#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "This removes generated case stores, traces, timelines, and extractions."
echo "It preserves manually added evidence files under evidence/."

printf '{}\n' > storage/case_store.json
find evidence -maxdepth 1 -type d -name 'CASE-*' -exec rm -rf {} +
find evidence -maxdepth 1 -type d ! -name evidence ! -name case-001 ! -name shared-rules -exec rm -rf {} +

echo "Generated data cleaned."
