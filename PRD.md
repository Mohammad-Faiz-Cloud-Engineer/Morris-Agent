# Product Requirements Document: Morris Agent

**Version:** 3.0 (Codebase-Aligned)
**Last Updated:** August 2026
**Supported Platforms:** Fully cross-platform — Windows (ARM + x86/x64), Linux (Debian/Ubuntu and Arch), and macOS on desktops and laptops
**Document Purpose:** Complete, accurate guide reflecting the current implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Hardware Specifications](#2-hardware-specifications)
3. [System Architecture](#3-system-architecture)
4. [Technical Stack (Actual)](#4-technical-stack-actual)
5. [Memory Budget](#5-memory-budget)
6. [Implementation Phases](#6-implementation-phases)
7. [File Structure](#7-file-structure)
8. [Configuration Files](#8-configuration-files)
9. [API Contracts](#9-api-contracts)
10. [Testing Criteria](#10-testing-criteria)
11. [Known Risks & Mitigations](#11-known-risks--mitigations)

---

## 1. Executive Summary

### 1.1 Goal

Create a modular, local-first voice AI assistant that runs on any desktop or laptop with Windows, macOS, or Linux (Debian/Ubuntu and Arch). No platform is special: the same checkout runs everywhere. Voice interaction is handled locally with an optional cloud fallback for complex queries. The assistant's name is **Morris Agent**. The wake word is **"Morris"**.

### 1.2 Core Philosophy

**"Local Speed, Cloud Power"** — The system defaults to fast local processing. It seamlessly hands off to a cloud API for complex reasoning, injecting personality context only when necessary. All knowledge, weather, news, jokes, and system-status features are reachable through six function tools, with a plain-language fallback so even small models can route correctly.

### 1.3 User Experience

- Animated "Face" on an 800x480 display reacting to system states
- Wake word activation: custom **"Morris"** or the bundled **"Hey Jarvis"** fallback
- Talking filler phrases ("On it!", "Let me check.") while the brain is thinking
- Natural voice interaction with conversational responses

### 1.4 Key Design Decisions (Code-Aligned)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Local LLM | Single Qwen2.5:1.5b for routing AND chat | Native tool-calling, ~3GB RAM |
| STT | `auto` backend: whisper.cpp `base.en-q5_0` when provisioned, else faster-whisper | Balance of speed and accuracy; portable fallback for desktops |
| TTS | Piper Python package (`piper-tts`) with `en_GB-semaine-medium` | In-process synthesis, ~50MB RAM, no external binary needed |
| Wake Word | Custom openWakeWord `Morris.onnx`; bundled `Hey Jarvis` fallback | Trainable; a clean checkout works immediately |
| Tools | time, weather, news, system status, joke, cloud handoff | Six schemas covering the assistant's capabilities |
| Cloud API | Kimi K2 preview via `api.moonshot.ai` | High-quality complex question answering |
| UI | PyGame; native SDL desktop driver, optional `fbcon` on headless Linux | Works on normal desktops and headless Linux |

---

## 2. Hardware Specifications

### 2.1 Minimum Hardware

```yaml
compute:
  ram: "2GB+ (8GB recommended for Ollama + Whisper headroom)"
  storage: "10GB+ free (or NVMe SSD recommended)"
  cooling: "Active cooling recommended during sustained inference"

display:
  type: "Any SDL-compatible display (desktop, laptop, or external)"
  resolution: "800x480"
  interface: "Auto-detected by SDL"

audio_input:
  type: "USB Microphone"
  recommended: "ReSpeaker USB Mic Array or similar"
  sample_rate: "Takes native input rate (resampled to 16000 Hz)"
  channels: "1 (mono)"

audio_output:
  type: "USB Speaker out or 3.5mm jack"
  recommended: "USB speaker for better quality"

connectivity:
  wifi: "Required for Cloud API, Weather, News, and Jokes"
  ethernet: "Optional (recommended for stability)"
```

### 2.2 Desktop Platforms

The same checkout runs on Windows, macOS, Debian/Ubuntu, and Arch without source changes. `config.py` roots all paths to the checkout, device selection is portable (empty = OS default, otherwise a sound device index or case-insensitive name substring), and the UI uses the native SDL driver unless `use_framebuffer` is set on headless Linux.

### 2.3 Audio Device Diagnostics

```bash
# List recording/playback devices (Linux)
arecord -l  # recording
aplay -l    # playback

# Portable: print device indices and names from Python
.venv/bin/python -c "from audio.audio_manager import list_audio_devices; print(list_audio_devices())"
```

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERACTION                          │
│  [Microphone] ──► [Wake Word] ──► [STT] ──► [Orchestrator]      │
│                                                     │              │
│  [Speaker] ◄── [TTS] ◄── [Filler/Response] ◄────────┘              │
│                                                                   │
│  [Display/Face] ◄── [UI Manager] ◄───── [State Updates]              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR (Python)                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Tool Router                            │   │
│  │  Input: User text + Tool definitions                      │   │
│  │  Output: Tool call JSON OR direct chat response           │   │
│  └──────────────────────────────────────────────────────────┘   │
│       Tools: time · weather · news · system · joke · cloud      │
│           │             │            │          │              │
│           ▼             ▼            ▼          ▼              │
│      datetime      OpenWeather    NewsAPI     Kimi K2           │
│       stdlib          API           API         API             │
│       psutil       (optional)    (optional)   (optional)        │
│                                                                  │
│  [LOCAL_CHAT] ◄── No tool call — simple chat / greetings        │
│  [FILLERS]    ◄── Pre-recorded WAVs played before processing    │
│  [CUSTOM ACTIONS] ◄── e.g. "on camera" introduction script      │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow (Detailed)

```
1. IDLE STATE
   └── openWakeWord listening continuously (CPU: ~5%)
   └── UI showing "Idle" animation

2. WAKE WORD DETECTED ("Morris" / "Hey Jarvis")
   └── Router conversation history is cleared (fresh interaction)
   └── State → LISTENING; UI shows "Listening"
   └── Audio capture records until 1.5 s of silence or 15 s max

3. SPEECH CAPTURED
   └── State → THINKING; UI shows "Thinking" + spinning dots
   └── STT encodes → text (whisper.cpp CLI or faster-whisper)

4. FILLER + ROUTING
   └── A random pre-recorded filler ("On it!") plays to fill latency
   └── (skipped for the custom "on camera" introduction)
   └── Router decides using Ollama tool calls, or a keyword fallback

   CASE TIME: tool `get_current_time` → Python datetime → speech
   CASE WEATHER: `get_weather` (location or config default) → speech
   CASE NEWS: `get_news` (category or general) → speech
   CASE SYSTEM_STATUS: `get_system_status` (CPU temp, RAM, uptime) → speech
   CASE JOKE: `get_joke` (Official Joke API) → speech
   CASE CLOUD_HANDOFF: load cloud_soul.md → Kimi K2 → speech
   CASE direct chat (greetings/simple) → local Qwen reply → speech
   CASE "on camera": fixed introduction sentence → speech

5. RESPONSE DELIVERY
   └── State → SPEAKING; UI switches to speaking face
   └── Piper `synthesize()` → temp WAV → plays on the OS speaker
   └── Microphone MUTED during playback to prevent echo

6. RETURN TO IDLE
   └── State → IDLE; wake word detection resumes
```

### 3.3 State Machine

```python
# Valid states (ui/ui_manager.py + orchestrator UI usage)
class UIState(Enum):
    IDLE = "idle"           # Listening for wake word
    LISTENING = "listening" # Recording user speech
    THINKING = "thinking"   # Processing/routing
    SPEAKING = "speaking"   # Playing TTS output
    ERROR = "error"         # Error state (auto-recovers)

# Valid transitions observed in orchestrator
IDLE → LISTENING → THINKING → SPEAKING → IDLE
IDLE → LISTENING → IDLE            (no speech / STT error)
THINKING → ERROR → IDLE            (processing exception)
```

---

## 4. Technical Stack (Actual)

### 4.1 Core Components

| Component | Technology | Version/Model | Installation |
|-----------|------------|---------------|--------------|
| Runtime | Python | 3.9 – 3.13 (3.14+ has no prebuilt wheels for pygame/faster-whisper/scipy; scripts reject it) | `scripts/setup_raspi.sh` / desktop scripts |
| Orchestrator | Custom Python | - | `orchestrator.py` |
| Model Runtime | Ollama | Latest | `curl -fsSL https://ollama.com/install.sh \| sh` |
| Local LLM | Qwen2.5:1.5b | `qwen2.5:1.5b` | `ollama pull qwen2.5:1.5b` |
| Wake Word | openWakeWord + onnxruntime | 0.6+ / 1.18+ | `pip install openwakeword onnxruntime` |
| STT | whisper.cpp `whisper-cli` OR faster-whisper | `base.en-q5_0` / `base.en` | built by `scripts/setup_raspi.sh` or `pip install faster-whisper` |
| TTS | Piper Python package | `piper-tts>=1.3` | `pip install piper-tts` |
| Voice | `en_GB-semaine-medium` | ONNX + `.onnx.json` | downloaded by setup scripts |
| UI | PyGame | 2.5+ | `pip install pygame` |
| HTTP Client | httpx | 0.27+ | `pip install httpx` |
| Audio | sounddevice | 0.5+ | `pip install sounddevice` |
| System status | psutil | 6.0+ | part of `requirements.txt`; optional at runtime — `system_tool.py` degrades gracefully without it |

### 4.2 Installation

#### 4.2.1 Debian-based Linux (one-command `scripts/setup_raspi.sh`)

```bash
git clone <repo-url>
cd <repo>
chmod +x scripts/setup_raspi.sh
./scripts/setup_raspi.sh
```

What `scripts/setup_raspi.sh` does in order:

1. `apt` installs: Python tooling, build tools, SDL2, PortAudio, ALSA utilities
2. Creates `venv313` and installs Python deps (`httpx sounddevice numpy piper-tts openwakeword onnxruntime pygame`)
3. Installs Ollama and pulls `qwen2.5:1.5b`
4. Clones + builds whisper.cpp, installs the `whisper-cli` binary as `whisper-cpp` in `/usr/local/bin`, downloads `base.en`, quantizes to `q5_0`
5. Downloads `en_GB-semaine-medium.onnx` + `.onnx.json` into `piper/voices/`
6. Copies `.env.example` → `.env`

Then run:

```bash
source venv313/bin/activate
python orchestrator.py
```

If no custom `models/wake_word/Morris.onnx` exists, startup announces and uses the bundled fallback phrase **"Hey Jarvis"**.

#### 4.2.2 Desktop Scripts

Run from a native terminal (not WSL). All scripts create `.venv`, install `requirements.txt` (which pulls the Piper package, faster-whisper, psutil, etc.), and run `scripts/download_assets.py`, which fetches the `en_GB-semaine-medium` Piper voice into `piper/voices/`. The scripts do not install Ollama and do not create or fill in `.env`; they print the remaining steps (install/start Ollama and `ollama pull qwen2.5:1.5b`), leaving `.env` configuration to the user.

| Platform | Command |
|---|---|
| Windows PowerShell | `powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1` |
| Windows + Ollama via winget | `powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1 -InstallOllama` |
| Debian / Ubuntu | `bash scripts/setup_debian.sh` |
| Arch Linux | `bash scripts/setup_arch.sh` |
| macOS (Homebrew) | `bash scripts/setup_macos.sh` |

`scripts/download_assets.py` downloads the Piper voice (`.onnx` + `.onnx.json`). Face PNGs and filler WAVs are already committed under `assets/face/` and `assets/fillers/`; if they are removed, the UI falls back to a procedural face and no fillers are played. Custom `models/wake_word/Morris.onnx` is never downloaded — it must be added manually (see 4.3).

### 4.3 openWakeWord Custom Model Training

Training happens on a separate machine (Colab/laptop). The custom model is NOT tracked in the repository.

#### 4.3.1 Training

```python
# Use the official openWakeWord training notebook (Colab)
WAKE_WORD = "morris"               # intended word
TARGET_FALSE_ACCEPTS_PER_HOUR = 0.5
NUM_SYNTHETIC_SAMPLES = 10000     # more is better but slower
```

Export the trained model as an **ONNX** file and name it `Morris.onnx` to match the code default.

#### 4.3.2 Transfer to the checkout

```bash
scp Morris.onnx <host>:<repo>/models/wake_word/Morris.onnx
```

Place `Morris.onnx` under `models/wake_word/`. When that file is not present, startup logs a warning and loads the **bundled `hey_jarvis*.onnx`** supplied with the `openwakeword` package.

---

## 5. Memory Budget

### 5.1 RAM Allocation

```
Total Available: 8192 MB
Reserved for OS:  ~500 MB
━━━━━━━━━━━━━━━━━━━━━━━━
Available:       ~7692 MB

NORMAL OPERATION:
├── Ollama + Qwen2.5:1.5b     ~3200 MB
├── Python orchestrator        ~200 MB
├── openWakeWord                 ~150 MB (non-blocking)
├── Whisper engine               ~500 MB (loaded only during STT)
├── Piper TTS                    ~80 MB
├── PyGame UI                    ~50 MB
├── Audio buffers                ~50 MB
└── Headroom                     ~462 MB
━━━━━━━━━━━━━━━━━━━━━━━━
Total:  ~4692 MB (~61% of the available pool)
```

### 5.2 Model Management

`OllamaClient` exposes `ensure_model_loaded()` (issues a `keep_alive: 10m` "hello" prompt), but `orchestrator.py` does not currently call it — the model is loaded by Ollama on first use. Whisper models are provisioned system-wide (`whisper-cli` / `whisper-cpp` on PATH plus a GGML model) or via faster-whisper's first-use model download; for offline repeatable deployments the STT backend should be pinned and a model pre-provisioned rather than relying on an implicit download.

---

## 6. Implementation Phases

Each phase maps to a directory in the checkout. The reference code in this PRD reflects the actual running code.

### Phase 1: Foundation (Audio Pipeline) — `audio/`

**Deliverable:** terminal app that records, transcribes, and speaks text.

`audio/audio_manager.py` — cross-platform capture/playback with device selection, WAV normalization, and resampling to 16 kHz. Uses sounddevice/PortAudio (no ALSA binaries). Muting, silence-bounded recording, and WAV playback all live here.

Key method: `record_until_silence(silence_threshold, silence_duration, max_duration) → Optional[np.ndarray]` (returns None if muted; otherwise normalized 16 kHz mono).

`audio/tts_engine.py` — wraps the `piper-tts` Python package with `en_GB-semaine-medium`. `synthesize()` writes a WAV; `synthesize_to_audio()` returns raw PCM.

`audio/stt_engine.py` — backend auto-selects:
- `auto`: whisper.cpp CLI when both `whisper-cli` and the configured GGML model exist; otherwise faster-whisper.
- `whisper_cpp`: requires executable + model.
- `faster_whisper`: requires package + model name, CPU int8.

### Phase 2: Brain (LLM Router) — `brain/`

`brain/tool_definitions.py` — six tool schemas: `get_current_time`, `get_weather`, `get_news`, `get_system_status`, `get_joke`, `cloud_handoff`, plus the router `SYSTEM_PROMPT`.

`brain/ollama_client.py` — Ollama `/api/chat` wrapper with tool-call parsing (handles raw-argument strings) and `/api/tags` availability probe.

`brain/router.py` — sends the system prompt plus conversation history and the six tool schemas to Ollama; if the model emits a JSON tool call it uses that, otherwise it falls back to keyword phrase matching (`TIME_PHRASES`, `WEATHER_PHRASES`, `NEWS_PHRASES`, `SYSTEM_PHRASES`, `JOKE_PHRASES`) and a "simple chat" shortlist, then a default cloud handoff. This text fallback is what lets the 1.5B model route reliably.

`brain/tools/` — `time_tool.py` (stdlib), `weather_tool.py` (OpenWeatherMap), `news_tool.py` (NewsAPI), `system_tool.py` (psutil), `joke_tool.py` (Official Joke API). Cloud calls go through `brain/cloud_client.py` (`api.moonshot.ai/v1`).

### Phase 3: Senses (Wake Word) — `senses/wake_word_detector.py`

Detects a custom `Morris.onnx` model from any system mic; falls back to the bundled "Hey Jarvis" model. Runs in a daemon thread over a `RawInputStream` with 80 ms/1280-sample chunks at 16 kHz (chunk size scaled to the actual mic rate).

### Phase 4: Interface (UI Face) — `ui/ui_manager.py`

PyGame faces load every `*.png` in `assets/face/` (e.g. `happy`, `winking`, `thinking`, `happy_eye_glistening`, `irritated`), scaled and centered. When none are present a procedural face is drawn. On a Linux Pi with `use_framebuffer` true it uses `fbcon`/`/dev/fb0`; otherwise the native desktop driver (Windows/macOS/Wayland) is used. `enable_ui:false` disables the UI entirely.

### Phase 5: Integration (Full System) — `orchestrator.py` + `config.py`

`config.py` resolves all paths relative to the checkout, loads `config/config.json`, then `.env`, then OS env vars (`OPENWEATHER_API_KEY`, `NEWSAPI_KEY`, `MOONSHOT_API_KEY`; overridable `MORRIS_PROJECT_ROOT` / `MORRIS_CONFIG`).

`orchestrator.py`:
- Initializes components, catching failures per optional tool and the UI
- Loads pre-generated filler WAVs from `assets/fillers/`
- Speaks the startup greeting **before** starting the wake-word detector (so its own voice doesn't trigger "Hey")
- Resets conversation history on every wake word (transient context per interaction)
- Handles the custom "on camera" introduction phrase
- Speaks a random filler before routing (except "on camera")
- Forces `os._exit(0)` on shutdown to kill daemon sounddevice threads

#### 5.5 Systemd Service (Linux)

Reference example deployment unit (not versioned in the repository):

```ini
# /etc/systemd/system/morris-agent.service
[Unit]
Description=Morris Agent AI Assistant
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=<user>
WorkingDirectory=/home/<user>/Morris-Agent
EnvironmentFile=/home/<user>/Morris-Agent/.env
ExecStart=/home/<user>/Morris-Agent/venv313/bin/python orchestrator.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable morris-agent.service
sudo systemctl start morris-agent.service
sudo journalctl -u morris-agent.service -f
```

---

## 7. File Structure (current)

```text
.
├── README.md                     Project overview + setup
├── PRD.md                        This document
├── LICENSE                       BSD-2-Clause
├── config.py                     Portable runtime config loader
├── orchestrator.py                Main entry point
├── requirements.txt               Python dependencies
├── .env.example                  API-key template
├── scripts/                      Bootstrap scripts
│   ├── setup_raspi.sh            One-command Debian/Raspberry Pi OS installer
│   ├── setup_windows.ps1
│   ├── setup_macos.sh
│   ├── setup_debian.sh
│   ├── setup_arch.sh
│   └── download_assets.py
├── config/
│   ├── config.json               Runtime settings & paths
│   └── cloud_soul.md             Cloud LLM personality
├── audio/
│   ├── __init__.py
│   ├── audio_manager.py         Mic capture / WAV playback / muting
│   ├── tts_engine.py            Piper (piper-tts) wrapper
│   └── stt_engine.py            whisper.cpp / faster-whisper backends
├── brain/
│   ├── __init__.py
│   ├── ollama_client.py         Ollama chat + tool calls
│   ├── router.py                Routing (tool calls + keyword fallback)
│   ├── tool_definitions.py       Six tool schemas + system prompt
│   ├── cloud_client.py          Kimi K2 (api.moonshot.ai)
│   └── tools/
│       ├── __init__.py
│       ├── time_tool.py
│       ├── weather_tool.py
│       ├── news_tool.py
│       ├── system_tool.py
│       └── joke_tool.py
├── senses/
│   ├── __init__.py
│   └── wake_word_detector.py    openWakeWord listener
├── ui/
│   ├── __init__.py
│   └── ui_manager.py            PyGame face + state animation
├── assets/
│   ├── face/                    PNG face states (optional)
│   └── fillers/                 Pre-generated filler WAVs (optional)
├── models/                      Untracked custom wake-word model
│   └── wake_word/Morris.onnx
├── piper/voices/                en_GB-semaine-medium.onnx (+.onnx.json)
├── whisper.cpp/                 Clone + downloaded models (built by setup)
└── tests/
    ├── test_audio_pipeline.py
    ├── test_wake_word.py
    └── test_router.py
```

---

## 8. Configuration Files

### 8.1 Environment (.env)

```dotenv
OPENWEATHER_API_KEY=
NEWSAPI_KEY=
MOONSHOT_API_KEY=
```

Keys are optional; missing-key tools reply with a configuration message.

### 8.2 Main Config (`config/config.json`)

```json
{
  "assets_path": "assets/face",
  "piper_voice": "piper/voices/en_GB-semaine-medium.onnx",
  "whisper_path": "whisper-cli",
  "whisper_model": "whisper.cpp/models/ggml-base.en-q5_0.bin",
  "stt_backend": "auto",
  "stt_model_name": "base.en",
  "chat_model": "qwen2.5:1.5b",
  "wake_word_model": "models/wake_word/Morris.onnx",
  "wake_word_threshold": 0.5,
  "microphone_device": "",
  "speaker_device": "",
  "mic_sample_rate": 0,
  "target_sample_rate": 16000,
  "cloud_soul_path": "config/cloud_soul.md",
  "display_width": 800,
  "display_height": 480,
  "use_framebuffer": false,
  "enable_ui": true,
  "local_location": "Kingston, CA"
}
```

Path resolution:
- Relative paths are rooted at `project_root` (the checkout, or `MORRIS_PROJECT_ROOT`).
- `MORRIS_CONFIG` and OS environment variables can override the default config file location.
- API keys are loaded from the checkout `.env` and may be overridden by OS environment variables.
- Secrets (`*_api_key` / `*_key`) are never written by `Config.save()`.

### 8.3 Audio Devices

Empty `microphone_device`/`speaker_device` → OS defaults. Set an index or a case-insensitive name substring (e.g. `"respeaker"`).

---

## 9. API Contracts

### 9.1 Ollama Chat API

```http
POST http://localhost:11434/api/chat
{
  "model": "qwen2.5:1.5b",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "What's the news?"}
  ],
  "tools": [...six schemas...],
  "stream": false,
  "options": {"temperature": 0.7, "num_predict": 512}
}

// Response (tool call)
{
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {"function": {"name": "get_news", "arguments": {"category": ""}}}
    ]
  }
}
```

`brain/ollama_client.py` tolerates `arguments` arriving as a parsed dict or a JSON string.

### 9.2 OpenWeatherMap API

```
GET https://api.openweathermap.org/data/2.5/weather?q=London&appid=KEY&units=metric
```

Returns `name`, `main.temp`, `main.feels_like`, `main.humidity`, `weather[0].description`. Non-200 / 404 produces spoken fallback text.

### 9.3 NewsAPI

```
GET https://newsapi.org/v2/top-headlines?apiKey=KEY&country=us&pageSize=5&category=technology
```

Reads the first 5 titles into a spoken, unpiped one-liner. The `category` parameter is optional.

### 9.4 Official Joke API

```
GET https://official-joke-api.appspot.com/random_joke
```

Uses `setup` + `punchline` for a spoken joke; network failure yields a canned joke fallback.

### 9.5 Kimi K2 (Moonshot)

```
POST https://api.moonshot.ai/v1/chat/completions
Authorization: Bearer <API_KEY>
{
  "model": "kimi-k2-0905-preview",
  "messages": [
    {"role": "system", "content": "<cloud_soul.md>"},
    {"role": "user", "content": "Write a poem about stars"}
  ],
  "temperature": 0.7,
  "stream": false
}
```

Streaming response format:
```
data: {"choices": [{"delta": {"content": "The "}}]}
data: [DONE]
```

---

## 10. Testing Criteria

The current `tests/` are interactive component checks — not an automated cross-platform suite.

```bash
python tests/test_router.py
python tests/test_wake_word.py
python tests/test_audio_pipeline.py
```

### 10.1 Audio
- TTS synthesizes and plays clearly through the default/configured speaker.
- STT transcribes clear speech with <15% WER on the chosen backend.
- Microphone is muted during TTS playback.
- Silence detection stops recording after ~1.5s of quiet.

### 10.2 Brain
- Ollama responds within ~5 seconds for simple queries.
- Tool routing works: time, weather, news, system, joke, cloud.
- Keyword-text fallback produces the same routing as structured tool calls.
- Simple greetings stay local; conversation history resets per wake word.

> Routing note: jokes route to `get_joke` (`ToolType.JOKE`). test_router.py asserts `("Tell me a joke", ToolType.JOKE)` — the original `NONE` expectation was stale after `get_joke` and its keyword fallback were added.

### 10.3 Senses
- Custom "Morris" detects when `models/` is present; otherwise "Hey Jarvis" fallback active and announced.
- False-positive rate kept low via model + threshold tuning.

### 10.4 UI
- Renders on the target machine (Wayland/desktop/native framebuffer only on Linux when configured).
- State transitions (IDLE/LISTENING/THINKING/SPEAKING/ERROR) are smooth.
- Procedural face appears when PNG assets are absent.
- `enable_ui:false` and setup failure disable the UI without crashing the assistant.

### 10.5 Integration
- Full loop: wake word → listen → filler → router → response.
- Error paths recover gracefully without leaving the wake detector paused.
- Stable under continuous use; memory stays under 7 GB.
- Portable: same checkout runs on Windows, macOS, and Linux.

---

## 11. Known Risks & Mitigations

### 11.1 Audio Feedback Loop
**Risk:** Microphone picks up the speaker.
**Mitigations (implemented):** `AudioManager.mute()` during `blocking=True` playback for a `.wav`; the startup greeting is spoken before wake detection starts so the assistant does not trigger itself.

### 11.2 RAM Exhaustion
**Risk:** >8GB under heavy load.
**Mitigations:** single Ollama model at a time, whisper.cpp stays a subprocess loaded only during STT, faster-whisper is loaded at startup by `WhisperSTT` (CPU int8), `psutil` monitoring recommended.

### 11.3 Router Hallucination / Bad Tool Call
**Risk:** the 1.5B model emits an invalid JSON tool call or no call at all.
**Mitigations:** `arguments` strings are JSON-parsed defensively; a keyword- phrase fallback routes by text; unknown tool names become `NONE` rather than crashing.

### 11.4 Wake-Word False Positives
**Risk:** ambient speech triggers the assistant.
**Mitigations:** tune `wake_word_threshold` (default 0.5); test with the actual model (custom `Morris.onnx` or bundled fallback) and ambient recordings per deployment environment.

### 11.5 Network Failures
**Risk:** Weather/News/Joke/Kimi unreachable.
**Mitigations:** short timeouts per call (10s weather/news, 60s cloud, 5s joke), graceful spoken error messages, and optional tool init failures that skip the tool rather than crashing startup.

### 11.6 Thermal Throttling
**Risk:** sustained inference overheats a device.
**Mitigations:** active cooling; monitor temperature in `get_system_status` (`psutil.sensors_temperatures`); keep inference burst-limited.

---

## Appendix A: Quick Start Commands

```bash
# Debian-based Linux (one-command)
git clone <repo-url>
cd <repo>
chmod +x scripts/setup_raspi.sh && ./scripts/setup_raspi.sh
source venv313/bin/activate
python orchestrator.py

# Desktop (native terminal, not WSL)
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1            # Windows
bash scripts/setup_macos.sh    # macOS
bash scripts/setup_debian.sh   # Debian / Ubuntu
bash scripts/setup_arch.sh     # Arch

# Always ensure the local model is present
ollama pull qwen2.5:1.5b

# Fetch the Piper voice (required for TTS)
python scripts/download_assets.py
```

## Appendix B: Troubleshooting

| Symptom | Check |
|---|---|
| Voice model not found | Run setup script or place `en_GB-semaine-medium.onnx` + `.json` under `piper/voices/` |
| No usable STT backend | Provision `whisper-cli` + its `.bin`, or `pip install faster-whisper` |
| No mic / speaker | Leave device fields empty (OS default) or set an index/name in `config/config.json` |
| Wake word doesn't work | Verify the startup message; even without the custom model the fallback "Hey Jarvis" is used |
| Ollama unavailable | `ollama serve`, then `ollama pull qwen2.5:1.5b` |
| UI fails | Set `"enable_ui": false`, or check SDL driver support on the target machine |
| Weather/news/cloud unavailable | Add the key to `.env`; network access required |

---

**END OF PRD**

*This document mirrors the implemented code. Run the interactive checks in `tests/` after each phase on a new target machine before marking that platform as production-ready.*