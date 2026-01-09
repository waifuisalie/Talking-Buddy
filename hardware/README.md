# TalkingBuddy Voice Assistant - Hardware Overview

This directory contains hardware documentation for the TalkingBuddy Voice Assistant system.

## System Components

### Core Computing
- **Raspberry Pi 5** (4GB or 8GB RAM)
  - CPU: Quad-core ARM Cortex-A76 @ 2.4GHz
  - Runs the voice chatbot system (STT, LLM, TTS)
  - Power: 5V/5A USB-C

### Wake Word Detection
- **ESP32-S3 Development Board**
  - Dual-core Xtensa LX7 @ 240MHz
  - 8MB PSRAM (recommended)
  - Runs TensorFlow Lite wake word model
  - Power: 5V via USB or 3.3V direct

### Audio Input
- **I2S Microphone** (ESP32) - ICS-43434 or compatible
  - For wake word detection
  - Always-on listening
  - Low power consumption (~0.3W)

- **USB Microphone** (Raspberry Pi)
  - For conversation audio
  - Better quality than analog
  - ALSA compatible

### Audio Output
Choose one:
- **3.5mm Audio Jack** (built-in RPi5)
- **HDMI Audio** (via HDMI output)
- **I2S DAC** (e.g., HifiBerry DAC) - Best quality

## System Architecture

```
┌────────────────────────────────────────────────────────────┐
│                     ESP32-S3 Module                        │
│  ┌──────────────┐    ┌──────────────┐    ┌─────────┐     │
│  │ I2S Mic      │───▶│ TensorFlow   │───▶│  UART   │     │
│  │ (ICS-43434)  │    │ Lite Model   │    │  TX/RX  │     │
│  └──────────────┘    └──────────────┘    └────┬────┘     │
│                       "Marvin" Detection       │          │
└────────────────────────────────────────────────┼──────────┘
                                                 │ Serial
                                                 │ (115200)
┌────────────────────────────────────────────────┼──────────┐
│                    Raspberry Pi 5              │          │
│  ┌─────────┐                            ┌─────▼────┐     │
│  │   USB   │◀──────────────┐            │  UART    │     │
│  │  Mic    │               │            │  (GPIO)  │     │
│  └────┬────┘               │            └──────────┘     │
│       │                    │                              │
│  ┌────▼─────┐    ┌─────────▼─────┐    ┌──────────┐     │
│  │ Whisper  │───▶│    Ollama     │───▶│  Piper   │     │
│  │   STT    │    │ Gemma3/Qwen2.5│    │   TTS    │     │
│  └──────────┘    └───────────────┘    └────┬─────┘     │
│                                             │            │
│  ┌──────────────────────────────────────────▼─────────┐ │
│  │          Audio Output (3.5mm/HDMI/I2S)             │ │
│  └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

## Power Consumption

| State | Components Active | Power Draw | Notes |
|-------|------------------|------------|-------|
| **Deep Sleep** | ESP32 only | ~0.3-0.5W | Ollama unloaded, waiting for wake word |
| **Light Sleep** | ESP32 + Ollama loaded | ~2-3W | Model in memory, fast wake (<1s) |
| **Active** | Full system | ~5-8W | During conversation |
| **Processing** | CPU intensive | ~10-15W | LLM inference peak |

**Battery Operation:**
- With 20,000mAh power bank (~74Wh):
  - Deep sleep: ~148-246 hours (6-10 days)
  - Light sleep: ~25-37 hours
  - Mixed use (90% sleep, 10% active): ~100-150 hours (4-6 days)

## Connections

### ESP32 to Raspberry Pi (UART)
| ESP32 Pin | RPi5 Pin | Function |
|-----------|----------|----------|
| TX (GPIO43) | RX (GPIO15) | Serial data to Pi |
| RX (GPIO44) | TX (GPIO14) | Serial data from Pi |
| GND | GND | Common ground |

**Serial Settings:** 115200 baud, 8N1

### I2S Microphone to ESP32
| Microphone | ESP32 Pin | Function |
|------------|-----------|----------|
| SCK | GPIO5 | Serial clock |
| WS | GPIO4 | Word select (L/R) |
| SD | GPIO6 | Serial data |
| VDD | 3.3V | Power |
| GND | GND | Ground |

### USB Microphone to Raspberry Pi
- Connect via USB-A port
- Appears as ALSA device: `plughw:CARD=Device,DEV=0`

### Audio Output
**Option 1: 3.5mm Jack**
- Built-in on Raspberry Pi 5
- Simple plug-and-play

**Option 2: I2S DAC (e.g., HifiBerry)**
- Better audio quality
- Configure in `/boot/config.txt`

## Assembly Instructions

### 1. ESP32-S3 Setup
1. Flash firmware using PlatformIO
2. Connect I2S microphone to GPIO pins 4, 5, 6
3. Upload SPIFFS filesystem with audio files
4. Test wake word detection

### 2. Raspberry Pi 5 Setup
1. Install Debian 13
2. Run chatbot setup script
3. Connect USB microphone
4. Configure audio output

### 3. Connect ESP32 to Raspberry Pi
1. Connect ESP32 TX → RPi RX (GPIO15)
2. Connect ESP32 RX → RPi TX (GPIO14)
3. Connect GND → GND
4. Connect ESP32 USB for power

### 4. Testing
1. Power on both devices
2. Say "Marvin" to test wake word
3. Run chatbot in keyboard mode first
4. Switch to serial mode for production

## Enclosure Options

### Desktop Unit
- 3D printed case for RPi5 + ESP32
- Ventilation for cooling
- Mounting for microphone and speaker

### Portable Unit
- Battery pack integration
- Compact form factor
- External speaker connection

## Bill of Materials

See [parts-list.md](parts-list.md) for complete component list with prices.

## Wiring Diagrams

See [wiring-guide.md](wiring-guide.md) for detailed connection diagrams.

## Troubleshooting

### ESP32 not detected
- Check USB cable (data, not charge-only)
- Verify drivers installed
- Try different USB port

### Wake word not detecting
- Check microphone connections
- Verify I2S pins match config.h
- Adjust detection threshold in code

### Raspberry Pi audio issues
- Check ALSA device names: `arecord -l`
- Verify output device: `aplay -l`
- Test microphone: `arecord -d 5 test.wav && aplay test.wav`

### Serial communication failure
- Verify baud rate (115200)
- Check TX/RX connections (not crossed)
- Ensure common ground connection

## Performance Optimization

### For Best Audio Quality
- Use I2S DAC instead of 3.5mm jack
- Position microphone away from speaker
- Use noise-canceling microphone

### For Best Response Time
- Use Gemma3 1B model (fastest)
- Keep system in light sleep mode
- Optimize Ollama for CPU

### For Battery Life
- Use deep sleep when possible
- Lower screen brightness (if using)
- Disable unused peripherals

---

For more details, see the main project documentation in `rpi5-chatbot/`.
