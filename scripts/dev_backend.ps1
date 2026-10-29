# PowerShell script to start Family OS backend on 0.0.0.0:8000
$ErrorActionPreference = "Stop"

Set-Location -Path "$PSScriptRoot\..\backend"

if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "Please edit backend\.env and configure secrets if needed." -ForegroundColor Yellow
}

Write-Host "Applying database migrations..." -ForegroundColor Cyan
python -m alembic upgrade head

Write-Host "Starting Family OS backend on http://0.0.0.0:8000..." -ForegroundColor Green
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
