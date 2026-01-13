# TalkingBuddy Voice Assistant

A fully local, battery-powered voice assistant using open-source AI technologies. Built for the Raspberry Pi 5 with ESP32-S3 wake word detection.

## Features

- 🎤 **Wake Word Detection** - "Marvin" activation using ESP32-S3 with TensorFlow Lite
- 🇧🇷 **Full Brazilian Portuguese Support** - Speech recognition, language model, and text-to-speech all in PT-BR
- 🔋 **Battery-Powered Operation** - Intelligent sleep states power savings
- 🏠 **Fully Local** - Runs entirely offline on Raspberry Pi 5, no cloud dependencies
- 🧩 **Modular Architecture** - Separate STT, LLM, and TTS components for easy customization

## Quick Start

For a quick introduction, see [rpi5-chatbot/QUICK_START.md](rpi5-chatbot/QUICK_START.md)

For complete installation instructions, see [rpi5-chatbot/INSTALLATION.md](rpi5-chatbot/INSTALLATION.md)

## Hardware Requirements

### Core Components
- **Raspberry Pi 5** (8GB RAM recommended)
- **ESP32-S3** with I2S microphone (for wake word detection)
- **USB Microphone** (for conversation audio input)
- **Audio Output** (3.5mm jack, HDMI, or I2S DAC)

See [hardware/](hardware/) for complete bill of materials and wiring guides.

## Architecture

```
                    ┌─────────────┐
                    │  ESP32-S3   │
                    │ Wake Word   │
                    │  "Marvin"   │
                    └──────┬──────┘
                           │ Serial (115200 baud)
                           ▼
┌──────────────────────────────────────────────────────────┐
│                   Raspberry Pi 5                         │
│                                                          │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐           │
│  │ Whisper  │──▶│  Ollama   │──▶│  Piper   │           │
│  │   STT    │   │    LLM    │   │   TTS    │           │
│  │ (PT-BR)  │   │ (Gemma3)  │   │ (PT-BR)  │           │
│  └────┬─────┘   └───────────┘   └─────┬────┘           │
│       │                                 │                │
└───────┼─────────────────────────────────┼────────────────┘
        │                                 │
    Microphone                        Speaker
```

## Technology Stack

| Component | Technology | Model/Version |
|-----------|------------|---------------|
| **Wake Word** | ESP32-S3 + TensorFlow Lite | Marvin wake word model |
| **Speech-to-Text** | whisper.cpp | ggml-base.bin (multilingual, PT-BR) |
| **Language Model** | Ollama | Gemma3 1B or Qwen2.5 1.5B (PT-BR variants) |
| **Text-to-Speech** | Piper TTS | pt_BR-faber-medium.onnx |
| **Platform** | Raspberry Pi 5 | Debian 13 |

## Project Structure

```
TalkingBuddy-Voice-Assistant/
├── rpi5-chatbot/              # Python voice chatbot system
│   ├── src/                   # Source code (14 Python modules)
│   ├── models/                # Ollama Modelfile configurations
│   └── docs/                  # User documentation
│
├── esp32-wake-word/           # ESP32-S3 wake word detection firmware
│   ├── src/                   # C++ source code
│   ├── lib/                   # Libraries (TensorFlow Lite, audio processing)
│   └── data/                  # Audio feedback files
│
└── hardware/                  # Hardware documentation
    ├── parts-list.md          # Bill of materials
    └── wiring-guide.md        # Connection diagrams
```

## Usage Example

1. **Wake the assistant** - Say "Marvin"
2. **Wait for confirmation** - System says "Sim?" (Yes?)
3. **Ask your question** - Speak in Portuguese
4. **Hear the response** - Natural Portuguese speech
5. **End conversation** - Say "tchau" or "até logo" to trigger sleep mode

## Power Management

The system uses intelligent two-tier sleep states:

- **Light Sleep** (1s wake time) - Ollama model loaded, ready for conversation
- **Deep Sleep** (5-10s wake time) - Ollama model unloaded for maximum power savings

## Installation

### Prerequisites
- Raspberry Pi 5 with Debian 13
- ESP32-S3 connected via USB (/dev/ttyACM0)
- USB microphone
- Internet connection (for initial setup only)

### Quick Installation

```bash
git clone <repository-url>
cd TalkingBuddy-Voice-Assistant/rpi5-chatbot
bash setup.sh
```

The setup script will:
1. Install system dependencies
2. Build whisper.cpp with ggml-base.bin model
3. Install Piper TTS with Brazilian Portuguese voice
4. Set up Ollama and create custom PT-BR model
5. Create Python virtual environment
6. Run verification tests

For detailed step-by-step instructions, see [rpi5-chatbot/INSTALLATION.md](rpi5-chatbot/INSTALLATION.md)

## Documentation

### User Guides
- [Quick Start Guide](rpi5-chatbot/QUICK_START.md) - Get running quickly
- [Installation Guide](rpi5-chatbot/INSTALLATION.md) - Complete setup instructions
- [Hardware Guide](hardware/README.md) - BOM and wiring diagrams

### Feature Documentation
- [ESP32 Wake Word System](rpi5-chatbot/docs/ESP32_WAKE_WORD_SYSTEM.md) - Wake word integration details
- [Sleep States Explained](rpi5-chatbot/docs/SLEEP_STATES_EXPLAINED.md) - Power management internals
- [VAD Tuning Guide](rpi5-chatbot/docs/VAD_TUNING_GUIDE.md) - Voice activity detection configuration

### Advanced Topics
- [Modelfile Guide](rpi5-chatbot/docs/MODELFILE_GUIDE.md) - Custom Ollama model configuration
- [Wake Word Integration](rpi5-chatbot/docs/WAKE_WORD_INTEGRATION.md) - Architecture overview

## License

MIT License - See [LICENSE](LICENSE) for details


## Acknowledgments

This project builds upon the excellent work of:
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) by Georgi Gerganov
- [Ollama](https://ollama.ai/) for local LLM inference
- [Piper TTS](https://github.com/rhasspy/piper) by Rhasspy
- [ESP32 DIY Alexa](https://github.com/atomic14/diy-alexa) by Chris Greening for ESP32 wake word detection

## Support

For issues and questions:
- Check the [documentation](rpi5-chatbot/docs/)
- Review [common issues](rpi5-chatbot/INSTALLATION.md#troubleshooting)
- Open an issue on GitHub

---

