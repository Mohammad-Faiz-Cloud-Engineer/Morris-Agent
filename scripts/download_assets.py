#!/usr/bin/env python3
"""Download the Piper voice required by the portable default configuration."""

from argparse import ArgumentParser
from pathlib import Path
from urllib.request import urlretrieve


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
    print("Piper voice is ready. Add models/wake_word/Hey_Jansky.onnx for the custom wake word.")


if __name__ == "__main__":
    main()
