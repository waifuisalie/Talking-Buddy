#!/usr/bin/env python3
"""
Audio Device Detector and Configurator
Helps identify and configure the correct audio devices
"""
import pyaudio
import sys

def list_audio_devices():
    p = pyaudio.PyAudio()
    print("\n Available Audio Devices:\n")
    print(f"{'Index':<6} {'Name':<50} {'Channels':<10} {'Type'}")
    print("-" * 80)

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        channels = info.get('maxInputChannels') if info.get('maxInputChannels') > 0 else info.get('maxOutputChannels')
        dev_type = "Input" if info.get('maxInputChannels') > 0 else "Output"
        print(f"{i:<6} {info['name']:<50} {channels:<10} {dev_type}")

    p.terminate()
    print("\n")

if __name__ == "__main__":
    list_audio_devices()
    print("To configure audio:")
    print("1. Identify your output device (speaker/headphone) index")
    print("2. Identify your input device (microphone) index")
    print("3. Update .env file with ALSA device strings")
    print("   Example: AUDIO_DEVICE=plughw:3,0")
