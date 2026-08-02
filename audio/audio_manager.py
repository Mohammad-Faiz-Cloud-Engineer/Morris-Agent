"""Cross-platform microphone recording and WAV playback.

sounddevice uses PortAudio, so it provides native device access on Windows,
macOS, and Linux.  No ALSA executable or hardware-specific device name is
required.
"""

import time
import wave
from threading import Lock
from typing import Optional, Union

import numpy as np
import sounddevice as sd


DeviceSelector = Optional[Union[int, str]]


def list_audio_devices() -> list[dict]:
    """Return portable audio-device metadata for setup and diagnostics."""
    return [dict(index=index, **dict(device)) for index, device in enumerate(sd.query_devices())]


def resolve_audio_device(selector: DeviceSelector, kind: str) -> Optional[int]:
    """Resolve an optional device index/name to a sounddevice device index.

    Passing ``None`` or an empty string deliberately preserves the operating
    system default.  Text matches are case-insensitive substrings, which makes
    it convenient to configure friendly device names across platforms.
    """
    if selector is None or selector == "":
        return None
    if isinstance(selector, int) or (isinstance(selector, str) and selector.isdigit()):
        index = int(selector)
        device = sd.query_devices(index)
        channels = device["max_input_channels"] if kind == "input" else device["max_output_channels"]
        if channels <= 0:
            raise ValueError(f"Audio device {index} does not support {kind}.")
        return index

    channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
    matches = [
        index for index, device in enumerate(sd.query_devices())
        if str(selector).lower() in device["name"].lower() and device[channel_key] > 0
    ]
    if not matches:
        available = [
            f"{index}: {device['name']}" for index, device in enumerate(sd.query_devices())
            if device[channel_key] > 0
        ]
        raise RuntimeError(f"No {kind} device matching {selector!r}. Available: {available}")
    return matches[0]


def input_sample_rate(device: Optional[int], configured_rate: int) -> int:
    """Use an explicit rate, otherwise select the input device's native rate."""
    if configured_rate and configured_rate > 0:
        return configured_rate
    info = sd.query_devices(device, "input")
    return max(8000, int(round(info["default_samplerate"])))


def resample_int16(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Resample mono int16 audio without a SciPy-only dependency."""
    if source_rate == target_rate or len(audio) == 0:
        return audio.astype(np.int16, copy=False)
    destination_length = max(1, round(len(audio) * target_rate / source_rate))
    source_positions = np.arange(len(audio), dtype=np.float64)
    destination_positions = np.linspace(0, len(audio) - 1, destination_length)
    return np.interp(destination_positions, source_positions, audio).clip(-32768, 32767).astype(np.int16)


class AudioManager:
    """Manage mono speech capture and speaker output on every target OS."""

    def __init__(
        self,
        sample_rate: int = 16000,
        mic_sample_rate: int = 0,
        microphone_device: DeviceSelector = None,
        speaker_device: DeviceSelector = None,
        channels: int = 1,
        dtype: str = "int16",
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.mic_device = resolve_audio_device(microphone_device, "input")
        self.speaker_device = resolve_audio_device(speaker_device, "output")
        self.mic_sample_rate = input_sample_rate(self.mic_device, mic_sample_rate)
        self.is_muted = False
        self._mute_lock = Lock()
        self._recording = False
        self._audio_buffer: list[np.ndarray] = []

        mic_label = microphone_device or "system default"
        speaker_label = speaker_device or "system default"
        print(f"    Microphone: {mic_label} at {self.mic_sample_rate} Hz")
        print(f"    Speaker: {speaker_label}")

    def mute(self) -> None:
        with self._mute_lock:
            self.is_muted = True

    def unmute(self) -> None:
        with self._mute_lock:
            self.is_muted = False

    @staticmethod
    def _normalize(audio: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
        peak = np.max(np.abs(audio.astype(np.float64))) if len(audio) else 0
        if peak < 50:
            return audio.astype(np.int16, copy=False)
        gain = (target_peak * 32767) / peak
        return np.clip(audio.astype(np.float64) * gain, -32768, 32767).astype(np.int16)

    def record_until_silence(
        self,
        silence_threshold: float = 0.01,
        silence_duration: float = 1.5,
        max_duration: float = 30.0,
    ) -> Optional[np.ndarray]:
        """Record until silence, then return normalized audio at ``sample_rate``."""
        if self.is_muted:
            return None

        self._audio_buffer = []
        self._recording = True
        silence_elapsed = 0.0
        started_at = time.monotonic()

        def callback(indata, frames, time_info, status):
            if status:
                print(f"Audio input status: {status}")
            if not self.is_muted and self._recording:
                self._audio_buffer.append(indata.copy())

        try:
            with sd.InputStream(
                device=self.mic_device,
                samplerate=self.mic_sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                blocksize=0,
                callback=callback,
            ):
                while self._recording and time.monotonic() - started_at < max_duration:
                    sd.sleep(50)
                    if not self._audio_buffer:
                        continue
                    recent = self._audio_buffer[-1].flatten()
                    rms = np.sqrt(np.mean(recent.astype(np.float32) ** 2)) / 32768
                    chunk_seconds = len(recent) / self.mic_sample_rate
                    silence_elapsed = silence_elapsed + chunk_seconds if rms < silence_threshold else 0.0
                    if silence_elapsed >= silence_duration:
                        break
        finally:
            self._recording = False

        if not self._audio_buffer:
            return None
        raw_audio = np.concatenate(self._audio_buffer).flatten()
        normalized = self._normalize(raw_audio)
        return resample_int16(normalized, self.mic_sample_rate, self.sample_rate)

    def save_to_wav(self, audio: np.ndarray, filepath: str) -> None:
        with wave.open(filepath, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio.astype(np.int16, copy=False).tobytes())

    def play_wav(self, filepath: str) -> None:
        """Play a PCM WAV through the configured/default system speaker."""
        self.mute()
        try:
            with wave.open(filepath, "rb") as wav_file:
                if wav_file.getsampwidth() != 2:
                    raise ValueError("Only 16-bit PCM WAV playback is supported.")
                frames = np.frombuffer(wav_file.readframes(wav_file.getnframes()), dtype=np.int16)
                channels = wav_file.getnchannels()
                if channels > 1:
                    frames = frames.reshape(-1, channels)
                sd.play(frames, wav_file.getframerate(), device=self.speaker_device, blocking=True)
        finally:
            self.unmute()

    def play_audio(self, audio: np.ndarray, sample_rate: Optional[int] = None) -> None:
        self.mute()
        try:
            sd.play(audio, sample_rate or self.sample_rate, device=self.speaker_device, blocking=True)
        finally:
            self.unmute()
