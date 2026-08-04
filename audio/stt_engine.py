"""Portable speech-to-text with whisper.cpp or faster-whisper backends."""

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False


class WhisperSTT:
    """Transcribe WAV audio on Windows, macOS, and Linux.

    ``auto`` prefers a locally installed whisper.cpp CLI and transparently
    falls back to faster-whisper, whose pre-built Python packages work on all
    supported desktop platforms.
    """

    def __init__(
        self,
        whisper_path: str = "whisper-cli",
        model_path: str = "",
        language: str = "en",
        threads: int = 4,
        backend: str = "auto",
        model_name: str = "small.en",
    ):
        self.model_path = model_path
        self.language = language
        self.threads = threads
        self.backend = backend.lower()
        self.whisper_path = self._find_whisper_cli(whisper_path)
        self._faster_model = None

        if self.backend not in {"auto", "whisper_cpp", "faster_whisper"}:
            raise ValueError("stt_backend must be auto, whisper_cpp, or faster_whisper")

        use_cpp = (
            self.backend != "faster_whisper"
            and self.whisper_path
            and model_path
            and Path(model_path).exists()
            and Path(model_path).is_file()
        )
        if use_cpp:
            self.backend = "whisper_cpp"
            print(f"    STT backend: whisper.cpp ({self.whisper_path})")
            return
        if self.backend == "whisper_cpp":
            raise FileNotFoundError(
                "whisper.cpp requires both a CLI executable and a ggml model. "
                "Install whisper-cli or use stt_backend='faster_whisper'."
            )
        if not FASTER_WHISPER_AVAILABLE:
            raise RuntimeError(
                "No usable STT backend. Install faster-whisper or configure whisper.cpp."
            )
        self.backend = "faster_whisper"
        # int8 gives consistent CPU operation without CUDA/CoreML requirements.
        self._faster_model = WhisperModel(model_name, device="cpu", compute_type="int8")
        print(f"    STT backend: faster-whisper ({model_name})")

    @staticmethod
    def _find_whisper_cli(candidate: str) -> Optional[str]:
        if not candidate:
            return None
        expanded = Path(candidate).expanduser()
        if expanded.exists():
            return str(expanded)
        found = shutil.which(candidate)
        if found:
            return found
        # Common names exposed by current and older whisper.cpp releases.
        for name in ("whisper-cli", "whisper-cli.exe", "whisper-cpp", "main"):
            found = shutil.which(name)
            if found:
                return found
        return None

    def transcribe(self, audio_path: str) -> str:
        """Transcribe a 16 kHz mono WAV file."""
        if self.backend == "faster_whisper":
            segments, _ = self._faster_model.transcribe(
                audio_path, language=self.language, vad_filter=True
            )
            return " ".join(segment.text.strip() for segment in segments).strip()

        process = subprocess.run(
            [
                self.whisper_path,
                "-m", self.model_path,
                "-f", audio_path,
                "-l", self.language,
                "-t", str(self.threads),
                "--no-timestamps",
                "-np",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(f"whisper.cpp failed: {process.stderr.strip()}")
        return process.stdout.replace("[BLANK_AUDIO]", "").strip()

    def transcribe_audio_array(self, audio, sample_rate: int = 16000) -> str:
        """Write an audio array to a safe temporary WAV and transcribe it."""
        descriptor, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(descriptor)
        try:
            with wave.open(temp_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio.astype("int16", copy=False).tobytes())
            return self.transcribe(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)
