#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sudo apt update
sudo apt install -y python3 python3-venv python3-pip portaudio19-dev libportaudio2 libsdl2-2.0-0 ffmpeg
python3 -m venv "$PROJECT_ROOT/.venv"
"$PROJECT_ROOT/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_ROOT/.venv/bin/python" -m pip install -r "$PROJECT_ROOT/requirements.txt"
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/download_assets.py" --project-root "$PROJECT_ROOT"
echo "Install Ollama from https://ollama.com, then run: ollama pull qwen2.5:1.5b"
echo "Start Morris Agent with: $PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/orchestrator.py"
