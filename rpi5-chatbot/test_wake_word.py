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

# Find the first input device and its native sample rate BEFORE installing the
# ALSA error suppressor (PortAudio enumerates cleanly while ALSA is in its normal state).
RATE = 16000   # openWakeWord requires 16 kHz
CHUNK = 1280   # 80 ms at 16 kHz

print(f"[DEBUG] Enumerating PyAudio devices...")
_p = pyaudio.PyAudio()
print(f"[DEBUG] Total devices found: {_p.get_device_count()}")
input_index = None
device_rate = RATE
for i in range(_p.get_device_count()):
    info = _p.get_device_info_by_index(i)
    print(f"[DEBUG]   [{i}] {info['name']}  in={info['maxInputChannels']}  out={info['maxOutputChannels']}  rate={info['defaultSampleRate']}")
    if info["maxInputChannels"] > 0 and input_index is None:
        input_index = i
        device_rate = int(info["defaultSampleRate"])
        print(f"[DEBUG]   ^^^ selected as input device (native rate: {device_rate} Hz)")
_p.terminate()
print(f"[DEBUG] Done enumerating. input_index={input_index}  device_rate={device_rate}")

if input_index is None:
    print("Error: no input device found. Check your microphone.")
    sys.exit(1)

# If the mic doesn't natively support 16 kHz, open at its native rate and
# resample each chunk to 16 kHz before passing to openWakeWord.
native_chunk = int(CHUNK * device_rate / RATE)
needs_resample = device_rate != RATE
print(f"[DEBUG] native_chunk={native_chunk}  needs_resample={needs_resample}")
if needs_resample:
    print(f"  (resampling {device_rate} Hz → {RATE} Hz per chunk)")

# NOW install ALSA error suppressor — keep _EH_CB at module level to avoid segfault.
try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    _EH_TYPE = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    _EH_CB = _EH_TYPE(lambda *a: None)
    _asound.snd_lib_error_set_handler(_EH_CB)
except Exception:
    pass

print(f"[DEBUG] Installing ALSA error suppressor...")
from openwakeword.model import Model

_MODEL_DIR = os.path.dirname(model_path)
print(f"[DEBUG] model_path={model_path}")
print(f"[DEBUG] _MODEL_DIR={_MODEL_DIR}")
import os as _os2
for fname in ["hey_buddy.onnx", "hey_buddy.onnx.data", "melspectrogram.onnx", "embedding_model.onnx"]:
    fpath = _os2.path.join(_MODEL_DIR, fname)
    exists = _os2.path.exists(fpath)
    size = _os2.path.getsize(fpath) if exists else 0
    print(f"[DEBUG]   {fname}: {'OK' if exists else 'MISSING'}  ({size} bytes)")

print(f"Loading model: {model_path}")
oww = Model(
    wakeword_models=[model_path],
    inference_framework="onnx",
    melspec_model_path=os.path.join(_MODEL_DIR, "melspectrogram.onnx"),
    embedding_model_path=os.path.join(_MODEL_DIR, "embedding_model.onnx"),
)

print(f"[DEBUG] Opening PyAudio stream: device={input_index}  rate={device_rate}  frames={native_chunk}")
p = pyaudio.PyAudio()
try:
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=device_rate,
        input=True,
        frames_per_buffer=native_chunk,
        input_device_index=input_index,
    )
except Exception as e:
    print(f"[DEBUG] p.open() FAILED: {e}")
    # Try default device at default rate as last resort
    print(f"[DEBUG] Retrying with default device and rate...")
    try:
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=device_rate,
                        input=True, frames_per_buffer=native_chunk)
        print(f"[DEBUG] Default device open OK")
    except Exception as e2:
        print(f"[DEBUG] Default device also failed: {e2}")
        p.terminate()
        sys.exit(1)
print(f"[DEBUG] Stream opened successfully")

print(f"Listening... say 'hey buddy'  (threshold: {threshold}, Ctrl+C to stop)\n")
try:
    while True:
        raw = np.frombuffer(stream.read(native_chunk, exception_on_overflow=False), dtype=np.int16)
        if needs_resample:
            audio = np.interp(
                np.linspace(0, len(raw) - 1, CHUNK),
                np.arange(len(raw)),
                raw
            ).astype(np.int16)
        else:
            audio = raw
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
