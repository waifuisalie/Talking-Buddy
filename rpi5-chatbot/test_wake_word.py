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
import numpy as np

# Import pyaudio and enumerate devices BEFORE installing the ALSA error
# suppressor — the ctypes hook interferes with PortAudio device probing.
import pyaudio

_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = os.path.join(_DIR, "models", "openwakeword", "hey_buddy.onnx")

model_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
threshold  = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5

if not os.path.exists(model_path):
    print(f"Error: model not found: {model_path}")
    print("  Run 'git pull' to get the model files, or pass the path as an argument.")
    sys.exit(1)

# Find a USB mic (or any input device that supports 16 kHz) before suppressing
# ALSA errors, while PortAudio can still enumerate devices properly.
CHUNK, RATE = 1280, 16000
_p = pyaudio.PyAudio()
input_index = None
for i in range(_p.get_device_count()):
    info = _p.get_device_info_by_index(i)
    if info["maxInputChannels"] < 1:
        continue
    try:
        if _p.is_format_supported(RATE, input_device=i, input_channels=1,
                                   input_format=pyaudio.paInt16):
            input_index = i
            print(f"Using mic: [{i}] {info['name']}")
            break
    except ValueError:
        continue
_p.terminate()

if input_index is None:
    print("Error: no input device found that supports 16 kHz. Check your microphone.")
    sys.exit(1)

# NOW install ALSA error suppressor (keeps the module-level ref to avoid segfault).
try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    _EH_TYPE = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    _EH_CB = _EH_TYPE(lambda *a: None)  # module-level ref keeps it alive
    _asound.snd_lib_error_set_handler(_EH_CB)
except Exception:
    pass

from openwakeword.model import Model

_MODEL_DIR = os.path.dirname(model_path)
print(f"Loading model: {model_path}")
oww = Model(
    wakeword_models=[model_path],
    inference_framework="onnx",
    melspec_model_path=os.path.join(_MODEL_DIR, "melspectrogram.onnx"),
    embedding_model_path=os.path.join(_MODEL_DIR, "embedding_model.onnx"),
)

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
