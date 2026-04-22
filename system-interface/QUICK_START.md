# Quick Start

## TL;DR

On a fresh Pi, run `../rpi5-chatbot/setup.sh` once. Then to launch:

```bash
cd system-interface
bash start.sh
```

Open **http://localhost:5000**.

`start.sh` handles Ollama startup, model warmup, VAD calibration, and Flask.

---

## Pre-flight checklist

- [ ] Ollama running (`systemctl --user status ollama`)
- [ ] Default model pulled (`ollama list | grep gemma3`)
- [ ] Personality models created (`ollama list | grep ptbr-`)
- [ ] ALSA devices reachable (`python test_audio_devices.py`)
- [ ] `.env` copied from `.env.example` and adjusted for local audio devices
- [ ] SPI enabled for RFID (`ls /dev/spidev*`)
- [ ] User in `spi`, `gpio`, `dialout`, `audio` groups

---

## Usage flow

1. **Login** — tap RFID card; greeting appears on the robot screen.
2. **Open chat** — click the robot to reveal the chat panel; history loads.
3. **Talk** — say "hey buddy" (wake word) or type; response streams back as text + audio.
4. **Timers** — inactivity tiers pause during conversation and resume when idle.

---

## Key `.env` settings

```bash
OLLAMA_MODEL=gemma3:1b
OLLAMA_URL=http://localhost:11434/api/chat

AUDIO_DEVICE=plughw:3,0
MICROPHONE_DEVICE=plughw:2,0

SUPERTONIC_LANGUAGE=pt
SUPERTONIC_PERSONALITY=neutral

WAKE_WORD_ENABLED=true
WAKE_WORD_DEBOUNCE_TIME=2.0
```

---

## API smoke tests

```bash
curl http://localhost:5000/api/voice/status

curl -X POST http://localhost:5000/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Olá!", "rfid": "TEST001", "user_id": 1}'

curl http://localhost:5000/api/chat/history/TEST001
```

---

## Troubleshooting

**Voice system not available** — check Ollama:
```bash
curl http://localhost:11434/api/tags
systemctl --user start ollama
```

**No audio output** — list devices and update `.env`:
```bash
aplay -L
speaker-test -c2 -t wav
```

**Wake word not firing** — confirm the mic referenced by `MICROPHONE_DEVICE` is the one you speak into; watch `openwakeword_manager` logs on boot.

**RFID unresponsive** — check SPI (`ls /dev/spidev*`) and that your user is in `spi` + `gpio` groups.

---

## Expected performance (RPi5, 8 GB)

- Response: 1–3 s (streaming starts sub-second)
- RAM: ~1.2 GB with `gemma3:1b`
- CPU: 40–60% during generation
