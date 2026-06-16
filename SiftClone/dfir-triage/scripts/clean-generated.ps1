param(
    [switch]$IncludeDemoEvidence
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "This removes generated case stores, traces, timelines, and extractions."
Write-Host "It preserves manually added evidence files under evidence\."

if (Test-Path storage\case_store.json) {
    Set-Content -Path storage\case_store.json -Value "{}"
}

Get-ChildItem evidence -Directory -Filter "CASE-*" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

Get-ChildItem evidence -Directory -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -ne "case-001" -and $_.Name -ne "shared-rules"
} | Remove-Item -Recurse -Force

if ($IncludeDemoEvidence) {
    Get-ChildItem evidence\case-001 -File -Include *.jsonl,*.plaso -ErrorAction SilentlyContinue |
        Remove-Item -Force
    Remove-Item evidence\case-001\extractions -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item evidence\case-001\timelines -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Generated data cleaned."
