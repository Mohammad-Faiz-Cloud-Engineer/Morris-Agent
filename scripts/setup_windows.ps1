[CmdletBinding()]
param(
    [switch]$InstallOllama
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# PowerShell 5.1 has a notorious gotcha: with $ErrorActionPreference = "Stop",
# stderr from a native command becomes a terminating error EVEN when the
# command succeeds.  All external calls are therefore made with the
# preference temporarily relaxed and the real exit code checked via
# $LASTEXITCODE, which is the only reliable signal.
function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$File,
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$ErrorMessage = "Command failed: $File $($Arguments -join ' ')"
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $File @Arguments
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($LASTEXITCODE -ne 0) {
        throw "$ErrorMessage (exit code $LASTEXITCODE)"
    }
}

function Get-PythonVersion {
    param([Parameter(Mandatory)][string]$Exe)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $Exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        $code = $LASTEXITCODE
    } catch {
        $output = $null
        $code = 999
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0 -or -not $output) {
        return $null
    }
    return ([string]$output).Trim()
}

# ---------------------------------------------------------------------------
# 1. Find a Python version with prebuilt wheels for every dependency.
#
# pygame, faster-whisper (ctranslate2), and scipy have no Windows wheels for
# Python 3.14+ yet; pip would try to compile them from source and fail.  Only
# 3.9 - 3.13 are used, in order of preference.
# ---------------------------------------------------------------------------
$PreferredPythons = @(
    @{ Exe = "py"; Args = @("-3.13") },
    @{ Exe = "py"; Args = @("-3.12") },
    @{ Exe = "py"; Args = @("-3.11") },
    @{ Exe = "py"; Args = @("-3.10") },
    @{ Exe = "py"; Args = @("-3.9") },
    @{ Exe = "python"; Args = @() }
)

$SelectedExe = $null
$SelectedVersion = $null

# Probe helper: returns version string, or $null if the interpreter is unusable.
# Must tolerate: uninstalled py tags (stderr + non-zero exit) and commands that
# are entirely missing (PowerShell throws NativeCommandError under EAP=Stop).
function Get-ProbeResult {
    param([string]$Exe, [string[]]$ArgsList)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $probe = & $Exe @($ArgsList + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")) 2>$null
        $code = $LASTEXITCODE
    } catch {
        $probe = $null
        $code = 999
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0 -or -not $probe) {
        return $null
    }
    return ([string]$probe).Trim()
}

foreach ($candidate in $PreferredPythons) {
    # Probe the candidate; ignore failures (e.g. uninstalled version tags).
    $probe = Get-ProbeResult $candidate.Exe $candidate.Args
    if (-not $probe) {
        continue
    }
    if ($probe -match "^3\.(9|10|11|12|13)$") {
        $SelectedExe = $candidate.Exe
        $SelectedArgs = $candidate.Args
        $SelectedVersion = $probe
        break
    }
}

if (-not $SelectedExe) {
    # Print a clear message and exit with a deterministic code.  Write-Error
    # would itself throw under $ErrorActionPreference = "Stop", so keep the
    # message on the host and call exit explicitly.
    Write-Host @"

No compatible Python found.

Morris Agent needs Python 3.9 - 3.13.  Python 3.14+ has no prebuilt Windows
wheels for pygame / faster-whisper / scipy, so the installation would fail.

Install Python 3.12 from https://www.python.org/downloads/windows/
(tick "Add python.exe to PATH" during installation), then re-run:

    powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1

"@
    exit 1
}

Write-Host "Using Python $SelectedVersion (compatible with all dependencies)."

# ---------------------------------------------------------------------------
# 2. Create (or refresh) the virtual environment.
# ---------------------------------------------------------------------------
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $VenvPython) {
    $existing = Get-PythonVersion $VenvPython
    if ($existing -eq $SelectedVersion) {
        Write-Host "Existing .venv already uses Python $existing; keeping it."
    } else {
        Write-Host "Refreshing .venv (Python $existing -> Python $SelectedVersion)."
        Remove-Item -Recurse -Force -LiteralPath (Join-Path $ProjectRoot ".venv")
        Invoke-Checked -File $SelectedExe -Arguments ($SelectedArgs + @("-m", "venv", (Join-Path $ProjectRoot ".venv"))) -ErrorMessage "Failed to create the virtual environment."
    }
} else {
    Invoke-Checked -File $SelectedExe -Arguments ($SelectedArgs + @("-m", "venv", (Join-Path $ProjectRoot ".venv"))) -ErrorMessage "Failed to create the virtual environment."
}

# ---------------------------------------------------------------------------
# 3. Install dependencies (fail loudly if anything goes wrong).
# ---------------------------------------------------------------------------
Write-Host "Installing Python packages (this can take a few minutes)..."
Invoke-Checked -File $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip") -ErrorMessage "Failed to upgrade pip."
Invoke-Checked -File $VenvPython -Arguments @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements.txt")) -ErrorMessage "Failed to install Python dependencies. See the pip error above."

# ---------------------------------------------------------------------------
# 4. Sanity-check that the key imports work inside the venv.
# ---------------------------------------------------------------------------
Invoke-Checked -File $VenvPython -Arguments @("-c", "import numpy, pygame, sounddevice, faster_whisper, openwakeword, piper; print('Dependency import check passed.')") -ErrorMessage "Installed packages failed to import."

# ---------------------------------------------------------------------------
# 5. Download the Piper voice and openwakeword fallback models.
# ---------------------------------------------------------------------------
Invoke-Checked -File $VenvPython -Arguments @((Join-Path $ProjectRoot "scripts\download_assets.py"), "--project-root", $ProjectRoot) -ErrorMessage "Failed to download runtime assets (Piper voice / openwakeword models)."

# ---------------------------------------------------------------------------
# 6. Optional: install Ollama via winget.
# ---------------------------------------------------------------------------
if ($InstallOllama) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Invoke-Checked -File "winget" -Arguments @("install", "--id", "Ollama.Ollama", "--exact", "--accept-package-agreements", "--accept-source-agreements") -ErrorMessage "winget failed to install Ollama."
    } else {
        Write-Warning "winget is unavailable. Install Ollama from https://ollama.com/download/windows"
    }
}

# ---------------------------------------------------------------------------
# 7. Done.
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Setup complete!"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Install/start Ollama, then run:  ollama pull qwen2.5:1.5b"
Write-Host "  2. (Optional) Add API keys:  copy .env.example to .env and edit"
Write-Host "  3. Start Morris Agent:"
Write-Host "     .\.venv\Scripts\python.exe orchestrator.py"
Write-Host ""
Write-Host "  Note: without models/wake_word/Morris.onnx, the fallback wake phrase is 'Hey Jarvis'."
