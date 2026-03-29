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

# Collect input device indices BEFORE installing the ALSA error suppressor
# (PortAudio enumerates cleanly while ALSA is in its normal state).
CHUNK, RATE = 1280, 16000
_p = pyaudio.PyAudio()
_candidates = [
    i for i in range(_p.get_device_count())
    if _p.get_device_info_by_index(i)["maxInputChannels"] > 0
]
_names = {i: _p.get_device_info_by_index(i)["name"] for i in _candidates}
_p.terminate()

# NOW install ALSA error suppressor so stream-open probing is silent.
# Keep _EH_CB at module level — if it gets GC'd, ALSA calls freed memory → segfault.
try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    _EH_TYPE = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    _EH_CB = _EH_TYPE(lambda *a: None)
    _asound.snd_lib_error_set_handler(_EH_CB)
except Exception:
    pass

# Try to actually open each candidate at 16 kHz (PortAudio resamples if needed).
input_index = None
_probe = pyaudio.PyAudio()
for i in _candidates:
    try:
        _s = _probe.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                         input=True, frames_per_buffer=CHUNK,
                         input_device_index=i, start=False)
        _s.close()
        input_index = i
        print(f"Using mic: [{i}] {_names[i]}")
        break
    except Exception:
        continue
_probe.terminate()

if input_index is None:
    print("Error: no input device found that supports 16 kHz. Check your microphone.")
    sys.exit(1)

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
