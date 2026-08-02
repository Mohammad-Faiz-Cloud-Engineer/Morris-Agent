"""Portable runtime configuration for Morris Agent.

All paths are rooted at this checkout by default.  They can be overridden in
``config/config.json`` or with environment variables, so the same checkout
works on Windows, macOS, and Linux (Debian/Ubuntu and Arch).
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


REPOSITORY_ROOT = Path(__file__).resolve().parent


def _default_path(*parts: str) -> str:
    return str(REPOSITORY_ROOT.joinpath(*parts))


@dataclass
class Config:
    """Application configuration with portable, checkout-relative defaults."""

    project_root: str = str(REPOSITORY_ROOT)
    assets_path: str = _default_path("assets", "face")

    # Models and executables.  ``whisper_path`` may be an executable name on
    # PATH (for example ``whisper-cli`` or ``whisper-cli.exe``).
    piper_voice: str = _default_path("piper", "voices", "en_GB-semaine-medium.onnx")
    whisper_path: str = "whisper-cli"
    whisper_model: str = _default_path("whisper.cpp", "models", "ggml-base.en-q5_0.bin")
    stt_backend: str = "auto"  # auto, whisper_cpp, or faster_whisper
    stt_model_name: str = "base.en"  # Used by faster-whisper.
    chat_model: str = "qwen2.5:1.5b"
    wake_word_model: str = _default_path("models", "wake_word", "Morris.onnx")
    wake_word_threshold: float = 0.5

    # An empty device value uses the operating system's default device.  A
    # number is a sounddevice index; text is matched against the device name.
    microphone_device: str = ""
    speaker_device: str = ""
    mic_sample_rate: int = 0  # 0 = use the selected input device's native rate
    target_sample_rate: int = 16000

    local_location: str = "Kingston, CA"
    openweather_api_key: str = ""
    moonshot_api_key: str = ""
    newsapi_key: str = ""
    local_soul_path: str = _default_path("config", "local_soul.md")
    cloud_soul_path: str = _default_path("config", "cloud_soul.md")

    display_width: int = 800
    display_height: int = 480
    use_framebuffer: bool = False  # Set true only for a Linux Pi framebuffer.
    enable_streaming_tts: bool = False
    enable_ui: bool = True

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """Load JSON and .env values, resolving relative paths safely."""
        config = cls()
        root_override = os.getenv("MORRIS_PROJECT_ROOT")
        if root_override:
            config.project_root = str(Path(root_override).expanduser().resolve())

        if config_path is None:
            config_path = os.getenv(
                "MORRIS_CONFIG",
                str(Path(config.project_root) / "config" / "config.json"),
            )

        config_file = Path(config_path).expanduser()
        if config_file.exists():
            with config_file.open(encoding="utf-8") as handle:
                data = json.load(handle)
            for key, value in data.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        config.project_root = str(Path(config.project_root).expanduser().resolve())
        config._resolve_paths()
        config._load_env_file(Path(config.project_root) / ".env")

        for attribute, variable in (
            ("openweather_api_key", "OPENWEATHER_API_KEY"),
            ("moonshot_api_key", "MOONSHOT_API_KEY"),
            ("newsapi_key", "NEWSAPI_KEY"),
        ):
            setattr(config, attribute, os.getenv(variable, getattr(config, attribute)))
        return config

    def _resolve_paths(self) -> None:
        """Resolve supported path fields relative to ``project_root``."""
        root = Path(self.project_root)
        for field_name in (
            "assets_path", "piper_voice", "whisper_model", "wake_word_model",
            "local_soul_path", "cloud_soul_path",
        ):
            value = Path(getattr(self, field_name)).expanduser()
            if not value.is_absolute():
                value = root / value
            setattr(self, field_name, str(value))

    @staticmethod
    def _load_env_file(path: Path) -> None:
        """Load a simple .env file without requiring an extra dependency."""
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

    def save(self, config_path: Optional[str] = None) -> None:
        """Save non-secret configuration to a JSON file."""
        target = Path(config_path or Path(self.project_root) / "config" / "config.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            key: value for key, value in self.__dict__.items()
            if not key.endswith("_api_key") and not key.endswith("_key")
        }
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
