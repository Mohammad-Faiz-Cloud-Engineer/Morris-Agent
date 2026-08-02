[CmdletBinding()]
param(
    [switch]$InstallOllama
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Get-Command py -ErrorAction SilentlyContinue
if (-not $Python) {
    throw "Python 3.9 or later is required. Install it from https://www.python.org/downloads/windows/ and re-run."
}

& py -3 -m venv "$ProjectRoot\.venv"
& "$ProjectRoot\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$ProjectRoot\.venv\Scripts\python.exe" -m pip install -r "$ProjectRoot\requirements.txt"
& "$ProjectRoot\.venv\Scripts\python.exe" "$ProjectRoot\scripts\download_assets.py" --project-root "$ProjectRoot"

if ($InstallOllama) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Ollama.Ollama --exact --accept-package-agreements --accept-source-agreements
    } else {
        Write-Warning "winget is unavailable. Install Ollama from https://ollama.com/download/windows"
    }
}

Write-Host "Setup complete. Install/start Ollama, run 'ollama pull qwen2.5:1.5b', then run .\.venv\Scripts\python orchestrator.py"
