# Changelog

All notable changes to the TalkingBuddy Voice Assistant project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-11-19

### Added
- Full Brazilian Portuguese voice assistant functionality
- ESP32-S3 wake word detection with "Marvin" trigger word
- Intelligent two-tier sleep states (light sleep / deep sleep)
- 85-92% power savings through wake word integration
- Modular architecture with separate STT, LLM, and TTS components
- Conversation memory with automatic context management
- Voice activity detection (VAD) for speech endpoint detection
- Natural dismissal detection ("tchau", "até logo")
- Dual timeout system (30-second conversation, 5-minute idle)
- Hardware monitoring (CPU, memory, temperature)
- Custom Ollama Modelfiles for Portuguese language enforcement

### Hardware Support
- Raspberry Pi 5 (Debian 13)
- ESP32-S3 with I2S microphone (ICS-43434)
- USB microphone support (ALSA plughw device)
- Multiple audio output options (3.5mm, HDMI, I2S DAC)

### Documentation
- Complete installation guide for Raspberry Pi 5
- ESP32 wake word system documentation
- Hardware bill of materials and wiring guides
- VAD tuning guide for microphone calibration
- Modelfile configuration guide
- Sleep states technical deep-dive

### Technology Stack
- whisper.cpp (ggml-base.bin multilingual model with PT-BR)
- Ollama (Gemma3 1B, Qwen2.5 1.5B with Portuguese variants)
- Piper TTS (pt_BR-faber-medium Brazilian Portuguese voice)
- TensorFlow Lite Micro (ESP32 wake word detection)
- PyAudio + pygame (audio input/output)
- pyserial (ESP32 serial communication)

### Performance
- Response time: 2-3 seconds (Gemma3 1B on RPi5)
- Wake word latency: <500ms
- Memory usage: 1-2GB depending on model
- Power consumption: ~0.3-0.5W (wake word listening), ~3-5W (active conversation)

---

## Future Releases

### [Unreleased]
Ideas for future improvements:
- Web interface for configuration
- Multiple wake word support
- Voice training for better recognition
- Integration with home automation systems
- Cloud fallback for complex queries (optional)
- Multi-language support beyond Portuguese
- Speaker recognition for personalization
