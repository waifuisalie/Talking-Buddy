# rpi5-chatbot — install assets

This directory holds install-time assets only. **The runtime app lives in `../system-interface/`**.

## When to use this

On a fresh Raspberry Pi 5:

```bash
cd rpi5-chatbot
bash setup.sh        # 8 phases, 20–40 min depending on network and Ollama pulls
sudo reboot          # picks up SPI + user-group changes
```

Then launch the app:

```bash
cd ../system-interface
bash start.sh        # serves http://localhost:5000
```

## What `setup.sh` does (8 phases)

1. System dependencies (`build-essential`, `cmake`, `portaudio19-dev`, `libsdl2-dev`, …)
2. Build **whisper.cpp** from source + download `ggml-base.bin`
3. Install **Ollama** service
4. Pull base model (`gemma3:1b`)
5. Create `rpi5-chatbot/venv` + install `openwakeword`, `supertonic`, `faster-whisper`
6. Generate and create Ollama personality models (`{base}-ptbr-{style}` × 9 styles)
7. Set up `system-interface/venv` and initialize DB
8. Configure hardware (enable SPI for RFID, add user to `spi`/`gpio`/`dialout`/`audio` groups)

## Layout

```
rpi5-chatbot/
├── setup.sh              # fresh-install provisioning
├── requirements.txt      # rpi5-chatbot venv (minimal — numpy, pyaudio)
├── src/
│   ├── config.py         # WhisperConfig dataclass (imported by system-interface)
│   └── whisper_stt.py    # WhisperSTT class     (imported by system-interface)
├── models/
│   ├── personalities.yaml          # 9 personality definitions
│   ├── generate_personalities.py   # generates per-base-model Modelfiles
│   ├── create_all_personalities.sh # runs `ollama create` for each
│   ├── create_model.sh             # helper invoked by create_all_personalities.sh
│   ├── gemma3/ qwen2.5/ llama3.2/  # generated Modelfiles (9 per base)
│   └── openwakeword/               # hey_buddy.onnx + embedding + melspectrogram (consumed by system-interface)
└── venv/                 # created by setup.sh
```

Runtime imports that pin files here: `system-interface/src/app.py` prepends `rpi5-chatbot/src/` to `sys.path` and imports `WhisperSTT` + `WhisperConfig`. `system-interface/src/openwakeword_manager.py` loads models from `rpi5-chatbot/models/openwakeword/`.

Don't move or delete those two dirs without updating the system-interface imports.
