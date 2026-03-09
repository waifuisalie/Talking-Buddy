# CLAUDE.md — TalkingBuddy Voice Assistant

## Project Overview

TalkingBuddy is a fully local, battery-powered voice assistant for **Raspberry Pi 5**, built as a university project. It speaks and understands **Brazilian Portuguese** (PT-BR) by default and runs entirely offline.

**Pipeline:** Wake word (ESP32-S3) → STT (whisper.cpp) → LLM (Ollama/Gemma3) → TTS (Piper/Supertonic) → Speaker

---

## Repository Structure

```
Talking-Buddy/
├── rpi5-chatbot/              # Main Python voice chatbot system
│   ├── src/                   # 14 Python modules (core logic)
│   ├── models/                # Ollama Modelfile configs + personalities.yaml
│   ├── docs/                  # Technical documentation
│   ├── run.sh                 # Main launcher script (use this to run)
│   ├── setup.sh               # Full installation script
│   └── requirements.txt       # Python deps (pygame, pyaudio, pyserial, etc.)
│
├── esp32-wake-word/           # ESP32-S3 C++ firmware (PlatformIO project)
│   ├── src/                   # C++ source (Application, states, Speaker, etc.)
│   └── lib/                   # TFLite Micro, audio_input, audio_output libs
│
└── hardware/                  # BOM and wiring guides
```

---

## Key Source Files (rpi5-chatbot/src/)

| File | Role |
|------|------|
| `run_chatbot.py` | CLI entry point — argparse, calls `VoiceChatbot` |
| `voice_chatbot.py` | Main orchestrator, state machine, all callbacks |
| `config.py` | All configuration dataclasses (`ChatbotConfig`, etc.) |
| `whisper_stt.py` | Audio recording + VAD + whisper CLI transcription |
| `ollama_llm.py` | Ollama API client (blocking + streaming) |
| `piper_tts.py` | Piper TTS synthesis (PT-BR, subprocess-based) |
| `supertonic_tts.py` | Supertonic 2 TTS (9x faster, multilingual: pt/en/es) |
| `esp32_wake_listener.py` | Serial/keyboard wake word listener |
| `sleep_manager.py` | Ollama service start/stop for power management |
| `timeout_manager.py` | Conversation (30s) and idle (5min) timers |
| `dismissal_detector.py` | Detects "tchau", "até logo" → triggers light sleep |
| `personality_manager.py` | Loads `models/personalities.yaml`, resolves model names |
| `audio_utils.py` | `AudioPlayer` (queue-based), `StateManager`, temp file cleanup |
| `audio_device_detector.py` | Auto-detects PyAudio input/output devices |
| `gpio_controller.py` | RGB LED feedback via GPIO (BCM pins: R=17, G=27, B=22, Y=23) |
| `conversation.py` | Conversation history manager (max 10 exchanges) |
| `hardware_monitor.py` | CPU/memory/temperature monitoring |

---

## How to Run

```bash
cd rpi5-chatbot
bash run.sh [args]          # Recommended: pre-flight checks + venv activation

# Or directly:
source venv/bin/activate
python src/run_chatbot.py [args]
```

### Common CLI Arguments

```bash
# Wake modes
--wake-mode serial          # ESP32 via /dev/ttyACM0 (default)
--wake-mode keyboard        # Press 'w' key (for testing without ESP32)
--wake-mode disabled        # Always listening

# Start modes
--start-mode light_sleep    # Default: wait for wake word (Ollama loaded)
--start-mode listening      # Always-on listening (testing)
--start-mode deep_sleep     # Minimal power (Ollama off)

# Models
--model gemma3-ptbr         # Default model
--model qwen2.5:1.5b        # Best quality (slower)
--model gemma3:1b           # Fastest

# Language & TTS
--language pt               # Portuguese (default)
--language en               # English
--language es               # Spanish
--tts-engine piper          # Default (PT-BR only)
--tts-engine supertonic     # 9x faster, multilingual

# Personality
--personality casual
--personality formal
--personality humorous
--base-model gemma3         # Base for personality model naming
--list-personalities        # Show all available personalities

# Interaction
--interaction-mode conversation   # Default: continuous chat
--interaction-mode single-shot    # Alexa-style: 1 Q&A then sleep

# Audio devices
--list-devices              # Show all audio devices
--input-device 'USB'        # Override mic by name or index
--output-device 'Headphones'

# Misc
--test                      # Run system diagnostics
--say "hello"               # Test TTS
--clear-history             # Wipe conversation history
```

---

## System States

```
deep_sleep → (wake word) → light_sleep → (wake word) → listening → processing → speaking
                                    ↑                       |
                                    └──────────── timeout / dismissal / single-shot
```

- **light_sleep**: Ollama loaded, Whisper OFF, waiting for ESP32 signal
- **deep_sleep**: Ollama stopped, minimal power, 5-10s wake latency
- **listening**: Whisper STT active, VAD capturing audio
- **processing**: LLM generating response
- **speaking**: TTS audio playing (mic paused to prevent feedback)

Timeouts:
- **Conversation timeout**: 30s of silence → light_sleep
- **Idle timeout**: 5 minutes in light_sleep → deep_sleep

---

## Configuration (config.py)

Key defaults tuned for RPi5:
- **STT model**: `~/whisper.cpp/models/ggml-base.bin` (multilingual)
- **STT binary**: `~/whisper.cpp/build/bin/whisper-cli`
- **Mic**: `plughw:CARD=Device,DEV=0` (USB PnP), auto-detection enabled
- **Output**: `hw:CARD=sndrpihifiberry,DEV=0` (HifiBerry DAC)
- **LLM**: `gemma3-ptbr` via Ollama at `http://localhost:11434`
- **Piper binary**: `~/piper/piper/piper`
- **Piper model**: `pt_BR-faber-medium.onnx`
- **VAD threshold**: RMS 30 (tune with debug mode)
- **Silence duration**: 1.5s before STT is triggered
- **Streaming**: enabled by default (`use_streaming=True`)

Config can be overridden via environment variables: `WHISPER_MODEL_PATH`, `WHISPER_CLI_BINARY`, `OLLAMA_URL`, `OLLAMA_MODEL`, `PIPER_BINARY`, `PIPER_MODEL_PATH`.

---

## Personality System

Personalities defined in `models/personalities.yaml`. Model name convention:

```
{base_model}-ptbr-{personality}
# e.g., gemma3-ptbr-casual, qwen2.5-ptbr-formal
```

Each personality has a `system_prompt` in Portuguese (localized at runtime for other languages).

---

## Hardware

- **Raspberry Pi 5** (8GB RAM), Debian 13
- **ESP32-S3** with ICS-43434 I2S mic → serial `/dev/ttyACM0` (115200 baud)
- **USB mic**: `plughw:CARD=Device,DEV=0`
- **HifiBerry DAC**: `hw:CARD=sndrpihifiberry,DEV=0`
- **RGB LED**: BCM pins Red=17, Green=27, Blue=22, Yellow=23
- **Serial port**: `/dev/ttyACM0`

---

## ESP32 Firmware

Located in `esp32-wake-word/`. Built with **PlatformIO**.

- Uses TensorFlow Lite Micro for "Marvin" wake word detection
- Sends serial signal to RPi5 when wake word detected
- Plays audio feedback via I2S speaker

---

## Audio Feedback Sounds

Stored in `rpi5-chatbot/sounds/`:
- `wake_beep.wav` — wake word detected
- `processing_beep.wav` — LLM processing
- `ready_beep.wav` — ready to listen
- `deep_sleep_tone.wav` — entering deep sleep
- `loading_tone.wav` — loading model (played in loop)
- `shutdown_tone.wav` — system shutdown

---

## VAD Tuning

Enable `debug_mode=True` in `WhisperConfig` to see RMS values. Tune `silence_threshold` so it's 20-30% above ambient noise. A smoothed rolling RMS window (~0.2s) filters transient spikes.

Typical ranges:
- Background noise: RMS 5-15
- Normal speech: RMS 50-200
- Default threshold: 30

---

## Development Notes

- **No cloud dependencies** — everything runs locally on RPi5
- **Two TTS engines**: Piper (PT-BR only, subprocess) and Supertonic 2 (multilingual, pip package)
- **Streaming LLM + incremental TTS**: sentences synthesized and queued as LLM streams, cutting latency
- **VAD handled inside `whisper_stt.py`** — `SilenceDetector` from `audio_utils` is NOT used anymore
- Mic is **paused during TTS playback** to prevent acoustic feedback loop
- Ollama uses `/api/chat` endpoint (not `/api/generate`) for proper message history
- Conversation history capped at 10 exchanges (20 messages: user + assistant)
- GPIO LED can be disabled via `GPIOConfig.enabled = False`

---

## Common Issues

- **Ollama not running**: `sudo systemctl start ollama` or `systemctl --user start ollama`
- **No mic detected**: run `python src/run_chatbot.py --list-devices`
- **VAD not triggering**: lower `silence_threshold` in `config.py` or use debug mode
- **ESP32 not detected**: use `--wake-mode keyboard` for testing
- **Whisper binary missing**: `cd ~/whisper.cpp/build && cmake --build .`
- **Piper missing**: re-run `bash setup.sh`
