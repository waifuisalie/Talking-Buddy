# TalkingBuddy ESP32 Wake Word Detector

This firmware implements wake word detection for the TalkingBuddy voice assistant system using an ESP32-S3 microcontroller with an I2S microphone.

## Overview

The ESP32 continuously listens for the wake word **"Marvin"** using TensorFlow Lite for Microcontrollers. When detected, it sends a serial message to the Raspberry Pi 5 to activate the main voice chatbot system.

This is a simplified, power-efficient wake word detector that communicates with the Raspberry Pi via USB serial. It does NOT perform command recognition - that's handled by the Raspberry Pi's LLM system.

## Hardware Requirements

- **Microcontroller**: ESP32-S3-DevKitC-1 (16MB Flash, 8MB OPI PSRAM)
- **Microphone**: ICS-43434 I2S MEMS microphone
- **Connection**: USB to Raspberry Pi 5

### Wiring (ICS-43434 to ESP32-S3)

| ICS-43434 Pin | ESP32-S3 Pin | Function |
|---------------|--------------|----------|
| SCK           | GPIO 5       | Serial Clock |
| WS            | GPIO 4       | Word Select (Left/Right) |
| SD            | GPIO 6       | Serial Data |
| VDD           | 3.3V         | Power |
| GND           | GND          | Ground |

**Microphone Configuration**: Left channel (WS connected to GND or low)

## Serial Communication Protocol

When the wake word is detected, the ESP32 sends via USB serial (115200 baud):

```
🎙️ MARVIN_DETECTED (confidence: 0.98)
WAKE_WORD_DETECTED
```

The Raspberry Pi listens for the `WAKE_WORD_DETECTED` message to trigger the chatbot.

## Building and Flashing

This project uses PlatformIO for compilation and upload.

### Prerequisites

```bash
# Install PlatformIO
pip install platformio

# Or use your IDE's PlatformIO extension (VS Code, CLion, etc.)
```

### Build and Upload

```bash
cd esp32-wake-word

# Build firmware
pio run

# Upload to ESP32-S3 (connected via USB)
pio run --target upload

# Monitor serial output
pio device monitor
```

### Upload Settings

The `platformio.ini` configuration:
- **Upload port**: `/dev/ttyACM1` (native USB)
- **Monitor port**: `/dev/ttyACM0` (serial output)
- **Baud rate**: 115200

Adjust ports if your system assigns different device names.

## Configuration

### Adjusting Wake Word Sensitivity

If you're having problems detecting the wake word "Marvin", adjust the detection threshold:

**File**: `src/state_machine/DetectWakeWordState.cpp` (line 59)

```cpp
if (output > 0.95)  // Default threshold
```

- **Lower threshold** (e.g., `0.90`) = More sensitive, more false positives
- **Higher threshold** (e.g., `0.98`) = Less sensitive, fewer false positives

You can also log the detection confidence to see what values you're getting:

```cpp
Serial.printf("Detection confidence: %.2f\n", output);
```

### GPIO Pin Configuration

**File**: `src/config.h`

```cpp
#define I2S_MIC_SERIAL_CLOCK GPIO_NUM_5      // SCK  -> GPIO 5
#define I2S_MIC_LEFT_RIGHT_CLOCK GPIO_NUM_4  // WS   -> GPIO 4
#define I2S_MIC_SERIAL_DATA GPIO_NUM_6       // SD   -> GPIO 6
```

Modify these if you need to use different pins.

## Project Structure

```
esp32-wake-word/
├── platformio.ini              # PlatformIO configuration
├── src/
│   ├── main.cpp                # Entry point, I2S setup
│   ├── Application.cpp/h       # Main state machine
│   ├── Speaker.cpp/h           # Audio feedback (optional)
│   ├── IndicatorLight.cpp/h    # LED indicator
│   ├── config.h                # GPIO and hardware config
│   └── state_machine/
│       ├── DetectWakeWordState.cpp/h  # Wake word detection logic
│       └── States.h            # State machine interface
├── lib/
│   ├── audio_input/            # I2S microphone sampling
│   ├── audio_processor/        # Audio preprocessing (FFT, MFCC)
│   ├── neural_network/         # TensorFlow Lite inference
│   └── tfmicro/                # TensorFlow Lite Micro library
├── data/
│   └── *.wav                   # Audio feedback files (optional)
└── include/
    └── README                  # Include directory placeholder
```

## How It Works

1. **Continuous Listening**: I2S microphone samples audio at 16kHz
2. **Audio Processing**: Generates spectrograms using FFT and MFCC
3. **Neural Network**: TensorFlow Lite Micro runs Marvin detection model
4. **Threshold Check**: If confidence > 0.95, wake word detected
5. **Serial Communication**: Sends `WAKE_WORD_DETECTED` to Raspberry Pi
6. **Loop**: Returns to listening state (no command recognition)

### Power Consumption

- **Always-on listening**: ~0.3-0.5W
- **Detection frequency**: ~100ms per inference
- **Average detection time**: 108ms (logged every 100 runs)

This enables the Raspberry Pi to sleep while maintaining wake word capability.

## Troubleshooting

### Wake Word Not Detected

1. **Check serial monitor** - You should see "Average detection time 108ms" messages
2. **Lower threshold** - Edit `DetectWakeWordState.cpp` line 59 to use `0.90` instead of `0.95`
3. **Verify microphone wiring** - Ensure I2S connections match GPIO configuration
4. **Check microphone channel** - ICS-43434 should be configured for left channel

### Build Errors

```
fatal error: tensorflow/lite/micro/...
```

**Solution**: The `tfmicro` library should be in `lib/tfmicro/`. Ensure you've cloned the complete repository with all submodules.

### Upload Fails

```
Could not open /dev/ttyACM1
```

**Solution**:
- Check USB connection
- Verify device appears in `ls /dev/ttyACM*`
- Update `platformio.ini` with correct port
- Add your user to `dialout` group: `sudo usermod -a -G dialout $USER`

## Integration with TalkingBuddy

This ESP32 firmware is designed to work with the TalkingBuddy Raspberry Pi 5 chatbot system:

- **ESP32 role**: Always-on wake word detection
- **Raspberry Pi role**: Conversational AI (Whisper STT, Ollama LLM, Piper TTS)
- **Communication**: USB serial at 115200 baud
- **Power savings**: 85-92% compared to Raspberry Pi always-on listening

See the main repository README for full system documentation.

## Credits and Attribution

This firmware is based on the [DIY Alexa](https://github.com/atomic14/diy-alexa) project by Chris Greening, adapted for the TalkingBuddy system with:

- Simplified wake word detection (removed wit.ai command recognition)
- Serial communication protocol for Raspberry Pi integration
- Updated for ESP32-S3 with OPI PSRAM support
- GPIO configuration for ICS-43434 I2S microphone
- Brazilian Portuguese voice assistant integration

Original DIY Alexa project components used:
- TensorFlow Lite Micro wake word detection
- Marvin wake word model
- Audio processing pipeline (FFT, MFCC)
- I2S sampling infrastructure

## License

See the main repository LICENSE file for licensing information.
