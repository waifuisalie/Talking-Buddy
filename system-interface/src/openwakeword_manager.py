#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenWakeWord Manager — substituto drop-in para ESP32Manager.

Detecta "hey buddy" usando o modelo ONNX treinado localmente,
sem precisar de ESP32. Mesma interface pública do ESP32Manager:
  start(), stop(), register_wake_callback(),
  check_and_clear_wake(), is_connected(), get_status(), running

Métodos extras para compartilhamento de microfone com Whisper STT:
  pause()   — libera o mic (bloqueia até stream fechado)
  resume()  — reabre mic e retoma detecção
"""

import os
import threading
import time
import numpy as np
import pyaudio
from typing import Optional, Callable

# Caminho dos modelos ONNX (relativo a este arquivo)
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_SRC_DIR))
_DEFAULT_MODEL_DIR = os.path.join(_REPO_ROOT, 'rpi5-chatbot', 'models', 'openwakeword')
_DEFAULT_MODEL_PATH = os.path.join(_DEFAULT_MODEL_DIR, 'hey_buddy.onnx')


class OpenWakeWordManager:
    """
    Gerenciador de wake word usando openWakeWord + ONNX no próprio RPi5.

    Interface idêntica ao ESP32Manager para ser usado como substituto
    transparente em app.py.
    """

    CHUNK = 1280    # 80 ms @ 16 kHz (exigido pelo openWakeWord)
    RATE  = 16000
    FORMAT = pyaudio.paInt16
    CHANNELS = 1

    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL_PATH,
        threshold: float = 0.5,
        debounce_time: float = 2.0,
        input_device_index: Optional[int] = None,
        # Parâmetros ignorados (compatibilidade com ESP32Manager)
        baud_rate: int = 115200,
        reconnect_interval: int = 5,
    ):
        self.model_path = model_path
        self.threshold = threshold
        self.debounce_time = debounce_time
        self.input_device_index = input_device_index

        # Estado da thread (interface ESP32Manager)
        self.running = False
        self.connected = False  # True depois que o modelo carrega e stream abre
        self._thread: Optional[threading.Thread] = None
        self._oww = None

        # Wake word detection (thread-safe)
        self._lock = threading.Lock()
        self._wake_detected = False
        self._last_wake_time = 0.0
        self._wake_callback: Optional[Callable] = None

        # Estatísticas
        self.wake_count = 0

        # Compartilhamento de mic com Whisper STT
        self._is_paused = False
        self._stream_released = threading.Event()
        self._stream_released.set()   # começa "liberado" (thread ainda não rodou)

    # -------------------------------------------------------------------------
    # Interface ESP32Manager
    # -------------------------------------------------------------------------

    def register_wake_callback(self, callback: Callable):
        self._wake_callback = callback

    def start(self):
        if self.running:
            print("⚠️  OpenWakeWordManager já está rodando")
            return

        # Carregar modelo
        try:
            from openwakeword.model import Model
            self._oww = Model(
                wakeword_models=[self.model_path],
                inference_framework="onnx",
                melspec_model_path=os.path.join(_DEFAULT_MODEL_DIR, "melspectrogram.onnx"),
                embedding_model_path=os.path.join(_DEFAULT_MODEL_DIR, "embedding_model.onnx"),
            )
        except Exception as e:
            print(f"❌ [OWW] Falha ao carregar modelo {self.model_path}: {e}")
            return

        self.running = True
        self._is_paused = False
        self._stream_released.clear()   # thread irá abrir o stream

        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="OpenWakeWordManager"
        )
        self._thread.start()
        print("🚀 OpenWakeWordManager iniciado")

    def stop(self):
        if not self.running:
            return
        print("🛑 Parando OpenWakeWordManager...")
        self.running = False
        self._is_paused = False         # desbloqueia thread se estiver em pausa
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.connected = False
        print("✅ OpenWakeWordManager parado")

    def check_and_clear_wake(self) -> bool:
        """Consumo único — thread-safe para rotas Flask."""
        with self._lock:
            if self._wake_detected:
                self._wake_detected = False
                return True
        return False

    def is_connected(self) -> bool:
        return self.connected

    def get_status(self) -> dict:
        return {
            "connected": self.connected,
            "running": self.running,
            "wake_count": self.wake_count,
            "model_path": self.model_path,
            "is_paused": self._is_paused,
        }

    # -------------------------------------------------------------------------
    # Compartilhamento de mic com Whisper STT
    # -------------------------------------------------------------------------

    def pause(self):
        """
        Para de ler áudio e libera o microfone.
        Bloqueia até o stream PyAudio ser fechado (seguro para abrir o mic
        imediatamente depois).
        """
        if not self.running or self._is_paused:
            print(f"🎙️  [OWW] pause() ignorado (running={self.running}, paused={self._is_paused})")
            return
        print("🎙️  [OWW] Pausando — aguardando microfone ser liberado...")
        self._is_paused = True
        released = self._stream_released.wait(timeout=1.5)
        if released:
            print("🎙️  [OWW] Microfone liberado com sucesso")
        else:
            print("⚠️  [OWW] Timeout aguardando microfone ser liberado (1.5s)")

    def resume(self):
        """
        Reabre o mic e retoma detecção de wake word.
        Chame depois que o Whisper STT liberar o microfone.
        """
        if not self.running:
            print(f"🎙️  [OWW] resume() ignorado (running={self.running})")
            return
        print("🎙️  [OWW] Retomando — aguardando SO liberar dispositivo...")
        # Small delay so the OS/ALSA fully releases the device before OWW tries to reopen it.
        # Without this, open_stream() can race against the caller's PyAudio.terminate()
        # and fail with [Errno -9985] Device unavailable.
        time.sleep(0.15)
        self._stream_released.clear()
        self._is_paused = False
        print("🎙️  [OWW] Flag de pausa removida — loop irá reabrir microfone")

    # -------------------------------------------------------------------------
    # Loop de áudio / inferência
    # -------------------------------------------------------------------------

    def _listen_loop(self):
        p = pyaudio.PyAudio()
        stream = None

        def find_input_device():
            if self.input_device_index is not None:
                info = p.get_device_info_by_index(self.input_device_index)
                return self.input_device_index, int(info["defaultSampleRate"])
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info["maxInputChannels"] > 0:
                    return i, int(info["defaultSampleRate"])
            return None, self.RATE

        def open_stream(device_idx, device_rate, native_chunk):
            if device_idx is None:
                raise RuntimeError("Nenhum dispositivo de entrada encontrado")
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
            print(f"🎙️  [OWW] Abrindo microfone (device_idx={device_idx}, rate={device_rate} Hz)...")
            stream = open_stream(device_idx, device_rate, native_chunk)
            self.connected = True
            print(f"👂 [OWW] Ouvindo wake word... (mic @ {device_rate} Hz"
                  + (f", resample → {self.RATE} Hz)" if needs_resample else ")"))

            while self.running:
                # --- Pausa: libera mic para Whisper ---
                if self._is_paused:
                    if stream is not None:
                        print("🎙️  [OWW] Fechando stream do microfone para liberar ao STT...")
                        close_stream(stream)
                        stream = None
                        self.connected = False
                        print("🎙️  [OWW] Stream fechado — sinalizando liberação")
                    self._stream_released.set()
                    while self._is_paused and self.running:
                        time.sleep(0.05)
                    if not self.running:
                        break
                    # Reabre o stream depois que Whisper liberar o mic
                    print("🎙️  [OWW] Tentando reabrir microfone após STT...")
                    self._stream_released.clear()
                    try:
                        stream = open_stream(device_idx, device_rate, native_chunk)
                        self.connected = True
                        print("🎙️  [OWW] Microfone reaberto com sucesso — retomando detecção")
                        if self._oww:
                            self._oww.reset()
                    except Exception as e:
                        print(f"⚠️  [OWW] Falha ao reabrir mic: {e} — tentando novamente em 0.5s")
                        time.sleep(0.5)
                    continue

                # --- Inferência ---
                if stream is None:
                    # Stream failed to reopen after a pause — retry on next iteration
                    time.sleep(0.1)
                    continue
                try:
                    # Non-blocking: poll available frames so we never block in read()
                    # and always honour _is_paused checks at the top of the loop.
                    # This also makes OWW resilient to USB device stalls.
                    try:
                        available = stream.get_read_available()
                    except Exception:
                        available = 0
                    if available < native_chunk:
                        time.sleep(0.005)
                        continue
                    audio_data = stream.read(native_chunk, exception_on_overflow=False)
                except OSError as e:
                    print(f"⚠️  [OWW] Erro de leitura do mic: {e}")
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
                    self._handle_wake_word(score)

        except Exception as e:
            print(f"❌ [OWW] Erro no loop de escuta: {e}")
        finally:
            if stream is not None:
                close_stream(stream)
            self.running = False
            self.connected = False
            self._stream_released.set()
            p.terminate()

    def _handle_wake_word(self, score: float):
        current_time = time.time()
        if current_time - self._last_wake_time < self.debounce_time:
            return

        with self._lock:
            self._wake_detected = True
            self._last_wake_time = current_time
            self.wake_count += 1

        print(f"🎙️  [OWW] Wake word detectado! (score: {score:.3f}, total: {self.wake_count})")

        if self._wake_callback:
            try:
                self._wake_callback()
            except Exception as e:
                print(f"❌ [OWW] Erro no callback: {e}")
