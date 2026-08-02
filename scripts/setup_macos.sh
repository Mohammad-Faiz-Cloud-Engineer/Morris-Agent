#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v brew >/dev/null; then
  echo "Homebrew is required. Install it from https://brew.sh and re-run this script." >&2
  exit 1
fi
brew install python portaudio sdl2 ffmpeg
python3 -m venv "$PROJECT_ROOT/.venv"
"$PROJECT_ROOT/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_ROOT/.venv/bin/python" -m pip install -r "$PROJECT_ROOT/requirements.txt"
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/download_assets.py" --project-root "$PROJECT_ROOT"
echo "Install Ollama from https://ollama.com/download/mac, then run: ollama pull qwen2.5:1.5b"
echo "Start Jansky with: $PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/orchestrator.py"
