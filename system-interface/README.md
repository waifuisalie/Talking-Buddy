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

## AI Specializations (RAG)

Specializations are shared knowledge bases (corpora) built from PDFs. Each corpus is created once by an admin and can then be assigned to any user account. When a user with a specialization asks a knowledge question, the assistant retrieves relevant passages from that corpus before generating its answer.

All management is done via the `ingest.py` CLI. Run every command from the `system-interface/` directory. **Ollama must be running** (`bash start.sh` or `systemctl --user start ollama`) for PDF ingestion, because each text chunk is sent to the embedding model (`granite-embedding:278m`).

### Typical workflow

1. **Create a corpus** — assign a slug (identifier) and a display name
2. **Ingest PDFs** — text is extracted, chunked (~500 tokens, 80-token overlap), and embedded
3. **Assign to a user** — in the web UI, edit the user account and pick the specialization

### Corpus management

```bash
# Create a new specialization
python -m voice_assistant.ingest corpus create \
    --slug medicina \
    --name "Medicina Geral" \
    --description "Conteúdo de medicina para a equipe de enfermagem" \
    --language pt-BR

# List all specializations (shows ID, slug, name, doc/chunk counts, language, enabled status)
python -m voice_assistant.ingest corpus list

# Delete a specialization
# WARNING: irreversible — removes all documents, chunks, vector embeddings, and PDF files on disk
python -m voice_assistant.ingest corpus delete --slug medicina
```

`corpus create` options:

| Option | Required | Default | Notes |
|--------|----------|---------|-------|
| `--slug` | yes | — | Short identifier, no spaces (e.g. `medicina`, `direito`) |
| `--name` | yes | — | Display name shown in the web UI |
| `--description` | no | `""` | Optional free-text description |
| `--language` | no | `pt-BR` | Metadata only — does not change embedding behavior |

### Document management

```bash
# Ingest a PDF into a corpus (Ollama must be running)
python -m voice_assistant.ingest doc add \
    --corpus medicina \
    --pdf /path/to/manual_clinico.pdf

# List documents in a corpus (shows ID, filename, page count, chunk count, ingest date)
python -m voice_assistant.ingest doc list --corpus medicina

# Remove a single document (use the ID shown by doc list)
python -m voice_assistant.ingest doc delete --doc-id 3
```

`doc add` runs 5 steps and prints progress: SHA-256 check → copy to `data/rag/corpora/<slug>/` → extract text → chunk → embed via Ollama. Large PDFs can take several minutes; each chunk is a separate Ollama HTTP call.

### Important notes

- **PDFs must have a text layer.** Scanned images (no OCR) produce no text and the ingest aborts.
- **Duplicate detection.** Re-ingesting the same file (same SHA-256) is a no-op — safe to re-run.
- **`corpus delete` is irreversible** and cascades: DB rows + the `data/rag/corpora/<slug>/` directory on disk are both removed.
- Users assigned to a deleted corpus keep their `specialization_id` in the DB, but RAG is silently skipped at chat time (the corpus no longer exists). Edit the user account to clear the assignment.
- The dispatcher (gemma3:1b) classifies each message before RAG runs. Only messages classified as `RAG` trigger a vector search; chitchat goes straight to the LLM.

### Memory embedding backfill

If user memories are missing their vector entry (e.g. after a DB migration), regenerate embeddings with:

```bash
python -m voice_assistant.ingest memory backfill
```

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
