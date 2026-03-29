"""
OpenWakeWord Listener - Replaces ESP32 wake word detection with on-device ML

Uses the openWakeWord library with a custom trained ONNX model to detect
the wake phrase entirely on the Raspberry Pi 5. Drop-in replacement for
ESP32WakeListener with the same public interface.
"""

import threading
import time
import numpy as np
import pyaudio
from typing import Optional, Callable


class OpenWakeWordListener:
    """
    Listens for wake word using openWakeWord ONNX model on-device.

    Same public interface as ESP32WakeListener:
      register_wake_callback, start, stop, send_sleep_signal, is_running, get_stats

    Extra methods for mic sharing with whisper_stt:
      pause()   -- release the mic (blocks until stream is actually closed)
      resume()  -- reopen mic and restart detection
    """

    CHUNK = 1280        # 80 ms at 16 kHz (required by openWakeWord)
    RATE = 16000
    FORMAT = pyaudio.paInt16
    CHANNELS = 1

    def __init__(
        self,
        model_path: str,
        threshold: float = 0.5,
        cooldown: float = 1.5,
        input_device_index: Optional[int] = None,
    ):
        """
        Args:
            model_path: Path to hey_buddy.onnx (or any openWakeWord ONNX model)
            threshold: Detection score threshold (0.0-1.0). Lower = more sensitive.
            cooldown: Seconds to ignore detections after one fires (prevents double-trigger).
            input_device_index: PyAudio device index. None = system default.
        """
        self.model_path = model_path
        self.threshold = threshold
        self.cooldown = cooldown
        self.input_device_index = input_device_index

        self._wake_callback: Optional[Callable] = None
        self._is_running = False
        self._is_paused = False
        self._thread: Optional[threading.Thread] = None
        self._oww = None

        # Used to block pause() until the PyAudio stream is actually closed,
        # so whisper_stt can safely open the mic right after pause() returns.
        self._stream_released = threading.Event()
        self._stream_released.set()  # starts "released" (not yet running)

        self.wake_count = 0
        self.last_wake_time: Optional[float] = None

    # -------------------------------------------------------------------------
    # Public interface (same as ESP32WakeListener)
    # -------------------------------------------------------------------------

    def register_wake_callback(self, callback: Callable):
        self._wake_callback = callback

    def start(self) -> bool:
        if self._is_running:
            return True

        try:
            from openwakeword.model import Model
            import os as _os
            _model_dir = _os.path.dirname(_os.path.abspath(self.model_path))
            self._oww = Model(
                wakeword_models=[self.model_path],
                inference_framework="onnx",
                melspec_model_path=_os.path.join(_model_dir, "melspectrogram.onnx"),
                embedding_model_path=_os.path.join(_model_dir, "embedding_model.onnx"),
            )
        except Exception as e:
            print(f"Failed to load openWakeWord model from {self.model_path}: {e}")
            return False

        self._is_running = True
        self._is_paused = False
        self._stream_released.clear()  # stream will be opened by thread

        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="OpenWakeWordListener"
        )
        self._thread.start()
        print(f"OpenWakeWord listener started — model: {self.model_path}")
        return True

    def stop(self):
        if not self._is_running:
            return
        self._is_running = False
        self._is_paused = False  # unblock thread if it's sleeping in pause
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        print("OpenWakeWord listener stopped")

    def send_sleep_signal(self):
        """No-op: nothing to notify (no ESP32)."""
        pass

    def is_running(self) -> bool:
        return self._is_running

    def get_stats(self) -> dict:
        return {
            "mode": "openwakeword",
            "is_running": self._is_running,
            "is_paused": self._is_paused,
            "wake_count": self.wake_count,
            "last_wake_time": self.last_wake_time,
            "model_path": self.model_path,
        }

    # -------------------------------------------------------------------------
    # Mic-sharing helpers (call from voice_chatbot.py around whisper start/stop)
    # -------------------------------------------------------------------------

    def pause(self):
        """
        Stop reading audio and release the mic.

        Blocks until the PyAudio stream is actually closed so the caller can
        immediately open the same device (e.g. whisper_stt.start()).
        """
        if not self._is_running or self._is_paused:
            return
        self._is_paused = True
        # Wait up to 1 s for the thread to close the stream
        self._stream_released.wait(timeout=1.0)

    def resume(self):
        """
        Reopen mic and resume wake word detection.
        Call this after whisper_stt.stop() has released the mic.
        """
        if not self._is_running:
            return
        self._stream_released.clear()
        self._is_paused = False

    # -------------------------------------------------------------------------
    # Internal audio / inference loop
    # -------------------------------------------------------------------------

    def _listen_loop(self):
        p = pyaudio.PyAudio()
        stream = None

        def find_input_device():
            if self.input_device_index is not None:
                return self.input_device_index, int(p.get_device_info_by_index(
                    self.input_device_index)["defaultSampleRate"])
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info["maxInputChannels"] > 0:
                    return i, int(info["defaultSampleRate"])
            return None, self.RATE

        def open_stream(device_idx, device_rate, native_chunk):
            if device_idx is None:
                raise RuntimeError("No input device found")
            return p.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=device_rate,
                input=True,
                frames_per_buffer=native_chunk,
                input_device_index=device_idx,
            )

        def close_stream(s):
            try:
                s.stop_stream()
                s.close()
            except Exception:
                pass

        try:
            device_idx, device_rate = find_input_device()
            native_chunk = int(self.CHUNK * device_rate / self.RATE)
            needs_resample = device_rate != self.RATE
            stream = open_stream(device_idx, device_rate, native_chunk)
            print(f"OpenWakeWord: listening for wake word... (mic @ {device_rate} Hz"
                  + (f", resampling to {self.RATE} Hz)" if needs_resample else ")"))

            while self._is_running:
                # --- Pause handling: release mic so whisper can use it ---
                if self._is_paused:
                    if stream is not None:
                        close_stream(stream)
                        stream = None
                    self._stream_released.set()
                    # Spin-wait until unpaused or stopped
                    while self._is_paused and self._is_running:
                        time.sleep(0.05)
                    if not self._is_running:
                        break
                    # Reopen the stream after whisper releases the mic
                    self._stream_released.clear()
                    try:
                        stream = open_stream(device_idx, device_rate, native_chunk)
                        if self._oww:
                            self._oww.reset()  # clear stale audio state
                    except Exception as e:
                        print(f"OpenWakeWord: failed to reopen mic: {e}")
                        time.sleep(0.5)
                    continue

                # --- Normal inference path ---
                try:
                    audio_data = stream.read(native_chunk, exception_on_overflow=False)
                except OSError as e:
                    print(f"OpenWakeWord: mic read error: {e}")
                    time.sleep(0.01)
                    continue

                raw = np.frombuffer(audio_data, dtype=np.int16)
                if needs_resample:
                    audio_np = np.interp(
                        np.linspace(0, len(raw) - 1, self.CHUNK),
                        np.arange(len(raw)),
                        raw
                    ).astype(np.int16)
                else:
                    audio_np = raw

                try:
                    prediction = self._oww.predict(audio_np)
                except Exception:
                    continue

                score = prediction.get("hey_buddy", 0)
                if score >= self.threshold:
                    now = time.time()
                    if self.last_wake_time is None or (now - self.last_wake_time) > self.cooldown:
                        self.wake_count += 1
                        self.last_wake_time = now
                        print(f"Wake word detected! (score: {score:.3f})")
                        if self._wake_callback:
                            try:
                                self._wake_callback()
                            except Exception as e:
                                print(f"Error in wake callback: {e}")

        finally:
            if stream is not None:
                close_stream(stream)
            self._stream_released.set()
            p.terminate()
