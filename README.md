# TalkingBuddy Voice Assistant

A fully local, battery-powered voice assistant for the **Raspberry Pi 5**, built as a university project. Speaks and understands **Brazilian Portuguese** by default and runs entirely offline. Accessed through a Flask web UI on the device.

## Features

- 🎤 **Local wake word** — openWakeWord runs on the Pi (no external MCU)
- 🇧🇷 **Brazilian Portuguese first** — STT, LLM, and TTS all in PT-BR (EN/ES also supported)
- 🔑 **RFID login** — MFRC522 reader identifies users and loads per-user conversation history
- 🌐 **Web UI** — Flask app at `http://localhost:5000` with chat, admin, and user management
- 📚 **AI Specializations (RAG)** — per-user knowledge bases built from PDFs; relevant passages injected into LLM context automatically
- 🧠 **Per-user memory** — the assistant remembers facts across conversations (toggleable per user)
- 🌍 **Translation mode** — two-panel real-time interpreter supporting PT↔EN and PT↔ES
- 🔋 **Battery-aware** — UPS HAT reports remaining charge in the UI
- 🏠 **Fully local** — no cloud dependencies; everything runs on the Pi

## Pipeline

```
Wake word (openWakeWord) → STT (whisper.cpp) → Dispatcher (intent classification)
                                              → RAG retrieval (optional, per user)
                                              → LLM (Ollama / Gemma3)
                                              → TTS (Supertonic) → Speaker
```

## Hardware

- **Raspberry Pi 5** (8 GB RAM)
- **USB microphone**
- **HDMI audio extractor** on HDMI 1 (`plughw:CARD=vc4hdmi1,DEV=0`) — any ALSA-reachable output works
- **MFRC522 RFID** reader over SPI
- **UPS HAT** with MAX17040 fuel gauge (optional, for battery readout)

## Installation

One-time setup on a fresh Pi:

```bash
git clone <repository-url> Talking-Buddy
cd Talking-Buddy/rpi5-chatbot
bash setup.sh          # 8 phases: system deps, whisper.cpp, Ollama + personality models, Supertonic, system-interface venv, hardware config
sudo reboot            # picks up SPI + group changes
```

Then launch the app:

```bash
cd Talking-Buddy/system-interface
bash start.sh          # starts Ollama, warms models, calibrates VAD, serves Flask on :5000
```

## Repository layout

```
Talking-Buddy/
├── system-interface/          # Runtime app (Flask, voice assistant, RFID, DB)
│   ├── src/                   # app.py entry point + DB, telemetry, SSE, wake-word, RFID
│   ├── voice_assistant/       # Ollama client, Supertonic TTS, streaming, personalities
│   │   └── ingest.py          # CLI for managing AI specializations (RAG corpora + PDFs)
│   ├── templates/ static/     # Web UI
│   ├── data/rag/corpora/      # PDF storage for specializations
│   └── start.sh               # Launcher
│
├── rpi5-chatbot/              # Install-time assets only (no runtime app)
│   ├── setup.sh               # Fresh-install provisioning
│   ├── src/                   # config.py + whisper_stt.py — imported by system-interface via sys.path
│   └── models/                # personalities.yaml + Modelfile generators + openwakeword ONNX
```

## Technology stack

| Component | Tech | Model |
|-----------|------|-------|
| Wake word | openWakeWord (ONNX) | `hey_buddy` (rpi5-chatbot/models/openwakeword/) |
| STT | whisper.cpp | `ggml-base.bin` (multilingual) |
| LLM | Ollama | Gemma3 1B / Qwen2.5 1.5B PT-BR personality variants |
| TTS | Supertonic 2 | multilingual (pt/en/es), 8 voices |
| Web UI | Flask + SSE | templates + vanilla JS |
| Platform | Raspberry Pi 5 | Debian 13 |

## Managing AI Specializations

Specializations (RAG corpora built from PDFs) are managed via a CLI tool. See the full guide in [system-interface/README.md](system-interface/README.md#ai-specializations-rag), which covers creating corpora, ingesting PDFs, listing, and deleting.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

Built on: [whisper.cpp](https://github.com/ggerganov/whisper.cpp), [Ollama](https://ollama.ai/), [Supertonic](https://pypi.org/project/supertonic/), [openWakeWord](https://github.com/dscripka/openWakeWord).
