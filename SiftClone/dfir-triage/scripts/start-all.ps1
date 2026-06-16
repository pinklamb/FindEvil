param(
    [string]$CaseId = "CASE-FRONTEND-001",
    [switch]$SkipWorkerBuild,
    [switch]$SkipNpmInstall,
    [switch]$KeepGeneratedData
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== Traceable DFIR startup =="
Write-Host "Project: $Root"
Write-Host "Default case ID: $CaseId"
Write-Host ""

if (-not $KeepGeneratedData) {
    Write-Host "Resetting generated demo data..."
    & "$PSScriptRoot\clean-generated.ps1"
}

if (-not $SkipWorkerBuild) {
    Write-Host "Building custom SIFT worker image..."
    docker compose build sift-worker-image
}

Write-Host "Starting backend services..."
docker compose up -d --build ollama mcp

Write-Host "Waiting for backend API..."
$Health = $null
for ($i = 0; $i -lt 60; $i++) {
    try {
        $Health = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/health" -TimeoutSec 5
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}

if ($null -eq $Health) {
    throw "Backend API did not become ready at http://localhost:8000/api/health"
}

Write-Host "Backend ready."
Write-Host "Evidence files will be listed from the evidence folder in the UI."

if (-not $SkipNpmInstall) {
    Push-Location frontend
    $NeedsNpmInstall = -not (Test-Path "node_modules")
    if (-not $NeedsNpmInstall) {
        npm exec vite -- --version | Out-Null
        $NeedsNpmInstall = $LASTEXITCODE -ne 0
    }
    if ($NeedsNpmInstall) {
        Write-Host "Installing frontend dependencies with npm install..."
        npm install
    }
    Pop-Location
}

Write-Host ""
Write-Host "Ready."
Write-Host "API:       http://localhost:8000/api/health"
Write-Host "Frontend: http://localhost:5174"
Write-Host ""
Write-Host "Starting Vite. Press Ctrl+C to stop the frontend dev server."
Write-Host ""

Push-Location frontend
npm run dev
Pop-Location
