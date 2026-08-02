"""Cross-platform openWakeWord detection."""

from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from audio.audio_manager import DeviceSelector, input_sample_rate, resolve_audio_device, resample_int16

try:
    import openwakeword
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False


class WakeWordDetector:
    """Detect a custom openWakeWord ONNX model from any system microphone."""

    def __init__(
        self,
        model_path: str = "",
        threshold: float = 0.5,
        sample_rate: int = 16000,
        mic_sample_rate: int = 0,
        microphone_device: DeviceSelector = None,
        allow_builtin_fallback: bool = True,
    ):
        if not OPENWAKEWORD_AVAILABLE:
            raise RuntimeError("openwakeword is not installed. Run the platform setup script first.")

        self.threshold = threshold
        self.sample_rate = sample_rate
        self.mic_device = resolve_audio_device(microphone_device, "input")
        self.mic_sample_rate = input_sample_rate(self.mic_device, mic_sample_rate)
        # openWakeWord consumes 80 ms / 1280 samples at 16 kHz.
        self.mic_chunk_size = max(1, round(1280 * self.mic_sample_rate / self.sample_rate))
        self._audio_queue: Queue[bytes] = Queue()
        self._running = False
        self._paused = False
        self._resume_event = Event()
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._callback: Optional[Callable[[], None]] = None

        custom_model = Path(model_path).expanduser() if model_path else None
        if custom_model and custom_model.exists():
            self.model = Model(wakeword_model_paths=[str(custom_model)])
            self.wake_phrase = "Hey Jansky"
            print(f"    Wake word model: {custom_model.name}")
        elif allow_builtin_fallback:
            # This makes a clean checkout usable immediately, while clearly
            # telling the user that its command changes to the fallback model.
            package_models = Path(openwakeword.__file__).parent / "resources" / "models"
            fallback = next(package_models.glob("hey_jarvis*.onnx"), None)
            if fallback is None:
                raise FileNotFoundError("No bundled openWakeWord fallback model was found.")
            self.model = Model(wakeword_model_paths=[str(fallback)])
            self.wake_phrase = "Hey Jarvis"
            print("    Warning: custom Hey Jansky model is missing; using built-in 'Hey Jarvis'.")
        else:
            raise FileNotFoundError(f"Wake word model not found: {model_path}")

    def start(self, callback: Callable[[], None]) -> None:
        self._callback = callback
        self._running = True
        self._paused = False
        self._stop_event.clear()
        self._resume_event.set()
        self._thread = Thread(target=self._listen_loop, name="jansky-wake-word", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        self._resume_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def pause(self) -> None:
        """Release the microphone before speech capture or playback."""
        self._paused = True
        self._resume_event.clear()

    def resume(self) -> None:
        self._paused = False
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except Empty:
                break
        self._resume_event.set()

    def _listen_loop(self) -> None:
        while self._running:
            self._resume_event.wait()
            if not self._running:
                break

            def audio_callback(indata, frames, time_info, status):
                if status:
                    print(f"Wake-word input status: {status}")
                self._audio_queue.put(bytes(indata))

            try:
                stream = sd.RawInputStream(
                    device=self.mic_device,
                    samplerate=self.mic_sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.mic_chunk_size,
                    callback=audio_callback,
                )
                stream.start()
            except Exception as error:
                print(f"Wake-word stream error: {error}")
                self._stop_event.wait(timeout=1.0)
                continue

            detected = False
            try:
                while self._running and not self._paused:
                    try:
                        raw = self._audio_queue.get(timeout=0.1)
                    except Empty:
                        continue
                    audio = np.frombuffer(raw, dtype=np.int16)
                    audio = resample_int16(audio, self.mic_sample_rate, self.sample_rate)
                    predictions = self.model.predict(audio)
                    if any(score >= self.threshold for score in predictions.values()):
                        detected = True
                        break
            finally:
                stream.stop()
                stream.close()

            if detected and self._callback:
                self.pause()
                self.model.reset()
                self._callback()
