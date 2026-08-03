#!/usr/bin/env python3
"""Download runtime assets (Piper voice, openWakeWord fallback models)."""

from argparse import ArgumentParser
from pathlib import Path
from urllib.request import urlretrieve

import openwakeword
from openwakeword.utils import download_models

VOICE_BASE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "en/en_GB/semaine/medium/en_GB-semaine-medium.onnx"
)


def download(url: str, destination: Path) -> None:
    if destination.exists():
        print(f"Already present: {destination}")
        return
    print(f"Downloading {destination.name}...")
    urlretrieve(url, destination)


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    voice_directory = arguments.project_root / "piper" / "voices"
    voice_directory.mkdir(parents=True, exist_ok=True)
    download(VOICE_BASE_URL, voice_directory / "en_GB-semaine-medium.onnx")
    download(f"{VOICE_BASE_URL}.json", voice_directory / "en_GB-semaine-medium.onnx.json")
    print("Piper voice is ready. Add models/wake_word/Morris.onnx for the custom wake word.")

    # The openwakeword wheel ships with an empty resources/models directory;
    # the fallback 'Hey Jarvis' model has to be fetched from GitHub releases.
    models_directory = Path(openwakeword.__file__).parent / "resources" / "models"
    models_directory.mkdir(parents=True, exist_ok=True)
    if (models_directory / "hey_jarvis_v0.1.onnx").exists():
        print("Already present: openwakeword fallback models")
    else:
        print("Downloading openwakeword fallback wake-word model...")
        download_models(["hey_jarvis_v0.1"], target_directory=str(models_directory))
        print("openwakeword fallback wake-word model ready.")


if __name__ == "__main__":
    main()
