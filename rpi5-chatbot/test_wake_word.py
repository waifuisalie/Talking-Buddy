#!/usr/bin/env python3
"""
Test script for the hey_buddy openWakeWord model.

Usage:
  python test_wake_word.py                        # use default model
  python test_wake_word.py /path/to/model.onnx    # custom model path
  python test_wake_word.py /path/to/model.onnx 0.4  # custom threshold

Say "hey buddy" — scores above 0.5 count as a detection.
"""
import os
import sys
import ctypes

# Suppress ALSA error spam before importing pyaudio
try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    _EH = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    _asound.snd_lib_error_set_handler(_EH(lambda *a: None))
except Exception:
    pass

import numpy as np
import pyaudio
from openwakeword.model import Model

_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = os.path.join(_DIR, "models", "openwakeword", "hey_buddy.onnx")

model_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5

if not os.path.exists(model_path):
    print(f"Error: model not found: {model_path}")
    print("  Run 'git pull' to get the model files, or pass the path as an argument.")
    sys.exit(1)

_MODEL_DIR = os.path.dirname(model_path)
_MELSPEC = os.path.join(_MODEL_DIR, "melspectrogram.onnx")
_EMBEDDING = os.path.join(_MODEL_DIR, "embedding_model.onnx")

print(f"Loading model: {model_path}")
oww = Model(
    wakeword_models=[model_path],
    inference_framework="onnx",
    melspec_model_path=_MELSPEC,
    embedding_model_path=_EMBEDDING,
)

CHUNK, RATE = 1280, 16000
p = pyaudio.PyAudio()
stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK,
)

print(f"Listening... say 'hey buddy'  (threshold: {threshold}, Ctrl+C to stop)\n")
try:
    while True:
        audio = np.frombuffer(stream.read(CHUNK, exception_on_overflow=False), dtype=np.int16)
        score = oww.predict(audio).get("hey_buddy", 0)
        if score > threshold:
            print(f"\n*** HEY BUDDY DETECTED! (score: {score:.3f}) ***")
        elif score > 0.2:
            print(f"  maybe... ({score:.3f})", end="\r")
except KeyboardInterrupt:
    pass

stream.stop_stream()
stream.close()
p.terminate()
print("\nDone.")
