#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

sudo apt update
sudo apt install -y python3 python3-venv python3-pip portaudio19-dev libportaudio2 libsdl2-2.0-0 ffmpeg

# Reject Python versions without prebuilt wheels (pygame, faster-whisper,
# scipy have none for 3.14+), so users get a clear message instead of a
# silent mid-install compile failure.  Runs after `apt install python3` so a
# fresh machine without Python still gets it installed first.
PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo unknown)"
case "$PY_VERSION" in
  3.9|3.10|3.11|3.12|3.13) ;;
  *)
    echo "Morris Agent needs Python 3.9 - 3.13 (found $PY_VERSION)." >&2
    echo "Install a supported Python 3 and re-run this script." >&2
    exit 1
    ;;
esac

python3 -m venv "$PROJECT_ROOT/.venv"
"$PROJECT_ROOT/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_ROOT/.venv/bin/python" -m pip install -r "$PROJECT_ROOT/requirements.txt"
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/download_assets.py" --project-root "$PROJECT_ROOT"
echo "Install Ollama from https://ollama.com, then run: ollama pull qwen2.5:1.5b"
echo "Start Morris Agent with: $PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/orchestrator.py"
