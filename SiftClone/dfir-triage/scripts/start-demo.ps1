param(
    [string]$CaseId = "CASE-FRONTEND-001"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

docker compose build sift-worker-image
docker compose up -d --build ollama mcp

$code = @"
import sys
sys.path.insert(0, r'dfir_backend')
from server import create_suspicious_test_case, check_llm_status
print(create_suspicious_test_case('$CaseId'))
print(check_llm_status())
"@

python -c $code

Write-Host ""
Write-Host "Demo backend is ready."
Write-Host "MCP server container: dfir-mcp"
Write-Host "Ollama: http://localhost:11434"
Write-Host "API: http://localhost:8000/api/health"
Write-Host "Demo case: $CaseId"
Write-Host ""
Write-Host "Frontend:"
Write-Host "  cd frontend"
Write-Host "  npm install"
Write-Host "  npm run dev"
