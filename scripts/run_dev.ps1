# Family OS - Daily Development Run Script
# Automates USB port reversal, checks Ollama, and starts services.
$ErrorActionPreference = "Continue"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "         FAMILY OS - SYSTEM STARTUP         " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Locate ADB
$adb = "d:\FamilyOS\tools\platform-tools\adb.exe"
if (-not (Test-Path $adb)) {
    $adb = (Get-Command adb -ErrorAction SilentlyContinue).Source
}

if ($adb) {
    Write-Host "`n[1/3] Checking connected Android devices via ADB..." -ForegroundColor Yellow
    & $adb devices
    Write-Host "Setting up USB port reversal (8000 & 8081)..." -ForegroundColor Yellow
    & $adb reverse tcp:8000 tcp:8000
    & $adb reverse tcp:8081 tcp:8081
    Write-Host "✓ ADB ports reversed successfully." -ForegroundColor Green
} else {
    Write-Host "[!] ADB not found in tools\platform-tools or PATH. Phone USB automation may not work." -ForegroundColor Red
}

# 2. Check Ollama
Write-Host "`n[2/3] Checking Ollama local LLM service..." -ForegroundColor Yellow
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 2 -ErrorAction Stop
    Write-Host "✓ Ollama is running and responding." -ForegroundColor Green
} catch {
    Write-Host "[!] Ollama is not running on http://127.0.0.1:11434." -ForegroundColor Yellow
    Write-Host "    Attempting to start Ollama in the background..." -ForegroundColor Yellow
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Minimized -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# 3. Instructions for running servers
Write-Host "`n[3/3] Ready to run Family OS services!" -ForegroundColor Green
Write-Host "Run the following in separate terminal tabs:" -ForegroundColor Cyan
Write-Host "  Terminal A (Backend):" -ForegroundColor White
Write-Host "    cd d:\FamilyOS\backend; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" -ForegroundColor Gray
Write-Host "  Terminal B (Mobile Client):" -ForegroundColor White
Write-Host "    cd d:\FamilyOS\apps\mobile; npx expo start" -ForegroundColor Gray
Write-Host "`nOn your phone: Open Expo Go, open Family OS, and enjoy!`n" -ForegroundColor Green
