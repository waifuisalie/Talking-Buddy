"""
Configuration settings for the voice chatbot system — Raspberry Pi 5 Edition

Only `WhisperConfig` and the `tlog`/`set_timing_debug` helpers are consumed at
runtime (by `whisper_stt.py` and `system-interface/src/app.py`). Everything
else has been removed.
"""

from dataclasses import dataclass
from typing import Optional
import os
import time

# --- Timing debug ---
_timing_debug = False

def set_timing_debug(enabled: bool):
    global _timing_debug
    _timing_debug = enabled

def tlog(label: str, t0: float = None) -> float:
    """Log a timing checkpoint. Returns current time.

    Usage:
        t0 = tlog("whisper-cli iniciado")          # marca início
        tlog("transcrição concluída", t0)           # marca fim e imprime delta
    """
    now = time.time()
    if _timing_debug:
        if t0 is not None:
            print(f"[TIMING] {label}: {now - t0:.3f}s")
        else:
            print(f"[TIMING] {label}")
    return now


@dataclass
class WhisperConfig:
    # Model and binary paths
    model_path: str = os.path.expanduser("~/whisper.cpp/models/ggml-base.bin")
    cli_binary: str = os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli")
    faster_whisper_model: str = "base"

    # Language and processing
    language: str = "pt"
    threads: int = 4
    audio_ctx: int = 512

    # Audio recording settings
    sample_rate: int = 16000
    chunk_size: int = 1024

    # ALSA capture device (overridden by system-interface via env vars)
    capture_device_name: str = "plughw:CARD=Device,DEV=0"
    capture_device: int = 1

    auto_detect_input: bool = True
    input_device_preference: Optional[str] = None

    # VAD — tune silence_threshold against RMS debug output
    silence_threshold: int = 30
    silence_duration: float = 1.5
    min_audio_length: float = 0.5
    debug_mode: bool = True
