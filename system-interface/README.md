# system-interface — Runtime app

Flask web app with RFID login, local wake word detection, Whisper STT, Ollama LLM, and Supertonic TTS. Runs entirely on the Raspberry Pi 5 — no internet required.

## Running

First install on a fresh Pi (see `../rpi5-chatbot/setup.sh`). Then:

```bash
cd system-interface
bash start.sh
```

Open **http://localhost:5000** in the browser.

`start.sh` starts Ollama, warms the default model, calibrates the VAD, and launches Flask on port 5000.

## Features

- **RFID login** — MFRC522 reader identifies users and loads per-user history
- **Local wake word** — openWakeWord (`hey_buddy`) runs on the Pi's USB microphone
- **Voice pipeline** — Whisper STT → Ollama LLM → Supertonic TTS, with SSE streaming to the UI
- **Web UI** — chat, admin, and user management served locally
- **Battery aware** — UPS HAT fuel gauge exposes remaining charge
- **100% offline** — all assets local, no CDNs or external APIs

## Wake word

openWakeWord runs in-process on the USB mic. Models live in `../rpi5-chatbot/models/openwakeword/` (`hey_buddy.onnx` + embedding + melspectrogram), loaded by `src/openwakeword_manager.py`.

Configure via `.env`:

```bash
WAKE_WORD_ENABLED=true
WAKE_WORD_DEBOUNCE_TIME=2.0
```

Flow: wake word detected → chat opens, feedback sound plays, mic arms → VAD records until silence → Whisper transcribes → Ollama generates → Supertonic speaks.

## Layout

```
system-interface/
├── src/
│   ├── app.py                  # Flask entry point
│   ├── database.py             # SQLite users + conversation history
│   ├── openwakeword_manager.py # Wake word detection
│   ├── rfid_manager.py         # MFRC522 RFID reader
│   ├── battery_monitor.py      # UPS HAT fuel gauge
│   ├── telemetry.py            # Structured logging
│   └── sse_manager.py          # Server-sent events for UI updates
├── voice_assistant/            # Ollama, Supertonic, streaming, personalities
├── templates/  static/         # Web UI
├── data/                       # SQLite DBs
├── start.sh                    # Launcher
└── .env.example                # Configuration template
```

## Configuration (`.env`)

Copy `.env.example` to `.env` and adjust:

- `OLLAMA_MODEL`, `OLLAMA_URL` — LLM endpoint
- `AUDIO_DEVICE`, `MICROPHONE_DEVICE` — ALSA names (run `test_audio_devices.py` to list)
- `WHISPER_*` — whisper.cpp paths (defaults from setup.sh)
- `SUPERTONIC_LANGUAGE`, `SUPERTONIC_PERSONALITY` — TTS voice
- `WAKE_WORD_ENABLED`, `WAKE_WORD_DEBOUNCE_TIME` — wake word behavior

## API quick reference

```bash
curl http://localhost:5000/api/voice/status
curl -X POST http://localhost:5000/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Olá!", "rfid": "TEST001", "user_id": 1}'
curl http://localhost:5000/api/chat/history/TEST001
```

## Troubleshooting

- **Ollama not reachable**: `systemctl --user status ollama`; ensure `OLLAMA_URL` matches.
- **No audio devices**: `python test_audio_devices.py` to list ALSA inputs/outputs.
- **Wake word not triggering**: check `src/openwakeword_manager.py` logs on boot; confirm the mic named in `MICROPHONE_DEVICE` is the one receiving your voice.
- **RFID not reading**: confirm SPI enabled (`ls /dev/spidev*`) and user in `spi`/`gpio` groups.
