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

# Suppress ALSA error spam before importing pyaudio.
# IMPORTANT: keep _EH_CB at module level — if it gets garbage collected,
# ALSA will call freed memory and segfault when the mic is probed.
try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    _EH_TYPE = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    _EH_CB = _EH_TYPE(lambda *a: None)  # module-level ref keeps it alive
    _asound.snd_lib_error_set_handler(_EH_CB)
except Exception:
    pass

import numpy as np
import pyaudio
from openwakeword.model import Model

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, "src"))
from audio_device_detector import AudioDeviceDetector

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

detector = AudioDeviceDetector()
input_device = detector.detect_input_device()
input_index = input_device.index if input_device else None
if input_device:
    print(f"Using mic: [{input_index}] {input_device.name}")

p = pyaudio.PyAudio()
stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK,
    input_device_index=input_index,
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
