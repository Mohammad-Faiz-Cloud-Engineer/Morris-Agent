#!/usr/bin/env bash
# ==============================================================
#  Morris Agent — One-Command Installer for Raspberry Pi OS / Debian
# ==============================================================
#  Usage:  chmod +x scripts/setup_raspi.sh && ./scripts/setup_raspi.sh
#
#  What this script does (in order):
#   1. Installs system packages (apt)
#   2. Creates a Python virtual environment with the system Python 3
#   3. Installs Python dependencies (pip)
#   4. Installs Ollama and pulls Qwen 2.5:1.5b
#   5. Builds Whisper.cpp from source and downloads the model
#   6. Downloads the Piper TTS voice
#   7. Reminds you to add API keys
# ==============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ── colours ───────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${YELLOW}[→]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── 1. System packages ───────────────────────────────────────
info "Installing system packages …"
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-dev \
  build-essential cmake git curl wget \
  libsdl2-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  portaudio19-dev libasound2-dev \
  alsa-utils
ok "System packages installed"

# ── Python version guard ─────────────────────────────────────
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

# ── 2. Python virtual environment ────────────────────────────
VENV_DIR="venv313"
if [ ! -d "$VENV_DIR" ]; then
  info "Creating Python virtual environment …"
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
ok "Virtual environment ready ($VENV_DIR)"

# ── 3. Python dependencies ───────────────────────────────────
info "Installing Python packages …"
pip install -q \
  httpx \
  sounddevice \
  numpy \
  piper-tts \
  openwakeword \
  onnxruntime \
  pygame
ok "Python packages installed"

# ── 4. Ollama + model ────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
  info "Installing Ollama …"
  curl -fsSL https://ollama.com/install.sh | sh
fi
ok "Ollama installed"

info "Pulling Qwen 2.5:1.5b (this may take a few minutes) …"
ollama pull qwen2.5:1.5b
ok "Qwen 2.5:1.5b ready"

# ── 5. Whisper.cpp ───────────────────────────────────────────
if [ ! -f "/usr/local/bin/whisper-cpp" ]; then
  if [ ! -d "whisper.cpp" ]; then
    info "Cloning Whisper.cpp …"
    git clone https://github.com/ggerganov/whisper.cpp.git
  fi
  info "Building Whisper.cpp …"
  cd whisper.cpp
  cmake -B build
  cmake --build build --config Release -j"$(nproc)"
  sudo cp build/bin/whisper-cli /usr/local/bin/whisper-cpp
  ok "Whisper.cpp built and installed to /usr/local/bin/whisper-cpp"

  info "Downloading Whisper base.en model …"
  bash models/download-ggml-model.sh base.en
  if [ -f build/bin/quantize ]; then
    ./build/bin/quantize models/ggml-base.en.bin models/ggml-base.en-q5_0.bin q5_0
    ok "Whisper model quantised (q5_0)"
  fi
  cd "$REPO_ROOT"
else
  ok "Whisper.cpp already installed"
fi

# ── 6. Piper TTS voice ──────────────────────────────────────
VOICE_DIR="piper/voices"
VOICE_FILE="$VOICE_DIR/en_GB-semaine-medium.onnx"
if [ ! -f "$VOICE_FILE" ]; then
  info "Downloading Piper TTS voice …"
  mkdir -p "$VOICE_DIR"
  wget -q -O "$VOICE_FILE" \
    https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx
  wget -q -O "${VOICE_FILE}.json" \
    https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json
  ok "Piper voice downloaded"
else
  ok "Piper voice already present"
fi

# ── 7. .env file ─────────────────────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  info "Created .env from template — edit it to add your API keys"
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Morris Agent is installed!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Next steps:"
echo "    1. (Optional) Add API keys:  nano .env"
echo "    2. Start Morris Agent:"
echo "         source venv313/bin/activate"
echo "         python orchestrator.py"
echo ""
echo "  Say \"Morris\" and start talking!"
echo ""
