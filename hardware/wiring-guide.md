# TalkingBuddy Voice Assistant - Wiring Guide

Detailed connection diagrams for assembling the hardware.

## System Overview

The TalkingBuddy system consists of three main subsystems:
1. **ESP32-S3** - Wake word detection with I2S microphone
2. **Raspberry Pi 5** - Main processing with USB microphone
3. **Audio Output** - Speaker system

---

## ESP32-S3 to I2S Microphone (ICS-43434)

### Pin Connections

| ICS-43434 Pin | ESP32-S3 Pin | Function | Notes |
|---------------|--------------|----------|-------|
| **VDD** | **3.3V** | Power | Do NOT use 5V! |
| **GND** | **GND** | Ground | Common ground |
| **SCK** (Serial Clock) | **GPIO 5** | Bit clock | I2S_SCK |
| **WS** (Word Select) | **GPIO 4** | L/R channel select | I2S_WS |
| **SD** (Serial Data) | **GPIO 6** | Audio data | I2S_SD |
| **L/R** | **GND** or **3.3V** | Channel select | GND=Left, 3.3V=Right |

### Wiring Diagram

```
ESP32-S3                      ICS-43434 Microphone
┌─────────────┐              ┌──────────────┐
│             │              │              │
│     3.3V ───┼──────────────┼─ VDD         │
│      GND ───┼──────────────┼─ GND         │
│   GPIO 5 ───┼──────────────┼─ SCK         │
│   GPIO 4 ───┼──────────────┼─ WS          │
│   GPIO 6 ───┼──────────────┼─ SD          │
│             │              │              │
│             │         GND ─┼─ L/R         │
└─────────────┘              └──────────────┘
```

### Configuration in code.h:
```cpp
#define I2S_MIC_SERIAL_CLOCK GPIO_NUM_5      // SCK
#define I2S_MIC_LEFT_RIGHT_CLOCK GPIO_NUM_4  // WS
#define I2S_MIC_SERIAL_DATA GPIO_NUM_6       // SD
#define I2S_MIC_CHANNEL I2S_CHANNEL_FMT_ONLY_LEFT
```

---

## ESP32-S3 to Raspberry Pi 5 (UART Serial)

### Pin Connections

| ESP32-S3 Pin | RPi5 Pin | Function | Notes |
|--------------|----------|----------|-------|
| **TX (GPIO 43)** | **RX (GPIO 15, Pin 10)** | ESP32 transmit to Pi | Serial data |
| **RX (GPIO 44)** | **TX (GPIO 14, Pin 8)** | Pi transmit to ESP32 | Serial data |
| **GND** | **GND (Pin 6 or 14)** | Common ground | **CRITICAL** |

### Wiring Diagram

```
ESP32-S3                  Raspberry Pi 5 (40-pin GPIO)
┌──────────┐             ┌─────────────────────────┐
│          │             │ Pin 1  [3.3V]           │
│  TX (43) ├─────────────┼ Pin 10 [GPIO 15] RX     │
│  RX (44) ├─────────────┼ Pin 8  [GPIO 14] TX     │
│   GND    ├─────────────┼ Pin 6  [GND]            │
│          │             │                         │
│  USB-C   │             │ USB-C Power             │
│  (Power) │             │ (5V/5A)                 │
└──────────┘             └─────────────────────────┘
```

### Serial Configuration
- **Baud Rate:** 115200
- **Data Bits:** 8
- **Parity:** None
- **Stop Bits:** 1
- **Flow Control:** None

**Device on RPi5:** `/dev/ttyAMA0` or `/dev/serial0`

### Enable Serial on Raspberry Pi 5

Edit `/boot/config.txt`:
```ini
# Enable UART (disable Bluetooth on serial0)
dtoverlay=disable-bt
enable_uart=1
```

Edit `/boot/cmdline.txt`:
Remove `console=serial0,115200` if present.

Reboot after changes.

---

## Raspberry Pi 5 to USB Microphone

### Connection
- Simply plug USB microphone into any USB-A port on Raspberry Pi 5
- No special wiring required

### Verify Detection
```bash
# List audio capture devices
arecord -l

# Expected output:
# card 1: Device [USB PnP Sound Device], device 0: USB Audio [USB Audio]
```

### Configure in chatbot config.py:
```python
capture_device_name: str = "plughw:CARD=Device,DEV=0"
```

---

## Audio Output Options

### Option 1: 3.5mm Audio Jack (Simplest)

**Connection:**
- Plug powered speakers or headphones into 3.5mm jack on Raspberry Pi 5

**Configure in config.py:**
```python
playback_device_name: str = "hw:CARD=Headphones,DEV=0"
```

---

### Option 2: I2S DAC (HifiBerry - Best Quality)

#### Pin Connections (HifiBerry DAC+)

| HifiBerry Pin | RPi5 GPIO Pin | Function |
|---------------|---------------|----------|
| **BCK** | **Pin 12 (GPIO 18)** | Bit clock |
| **LRCK** | **Pin 35 (GPIO 19)** | L/R clock |
| **DATA** | **Pin 40 (GPIO 21)** | Audio data |
| **VCC** | **Pin 2 (5V)** | Power |
| **GND** | **Pin 6 (GND)** | Ground |

#### Wiring Diagram

```
HifiBerry DAC+          Raspberry Pi 5 GPIO
┌─────────────┐        ┌───────────────────────┐
│  L-OUT  ────┼────────┤ Speaker Left +        │
│  R-OUT  ────┼────────┤ Speaker Right +       │
│  GND    ────┼────────┤ Speaker -             │
│             │        │                       │
│  BCK    ────┼────────┤ Pin 12 (GPIO 18)      │
│  LRCK   ────┼────────┤ Pin 35 (GPIO 19)      │
│  DATA   ────┼────────┤ Pin 40 (GPIO 21)      │
│  VCC    ────┼────────┤ Pin 2 (5V)            │
│  GND    ────┼────────┤ Pin 6 (GND)           │
└─────────────┘        └───────────────────────┘
```

#### Configure Raspberry Pi OS

Edit `/boot/config.txt`:
```ini
# Enable HifiBerry DAC+
dtoverlay=hifiberry-dacplus
# Disable onboard audio
dtparam=audio=off
```

Reboot after changes.

#### Configure in config.py:
```python
playback_device_name: str = "hw:CARD=sndrpihifiberry,DEV=0"
```

---

### Option 3: HDMI Audio

**Connection:**
- Connect HDMI cable to monitor/TV with speakers

**Configure in config.py:**
```python
playback_device_name: str = "hw:CARD=vc4hdmi0,DEV=0"  # HDMI 0
# or
playback_device_name: str = "hw:CARD=vc4hdmi1,DEV=0"  # HDMI 1
```

---

## Optional: User Interface Components

### Status LEDs

#### RGB LED (Common Cathode)

| RGB LED Pin | RPi5 GPIO Pin | Resistor | Function |
|-------------|---------------|----------|----------|
| **Red** | **GPIO 17 (Pin 11)** | 220Ω | Red channel |
| **Green** | **GPIO 27 (Pin 13)** | 220Ω | Green channel |
| **Blue** | **GPIO 22 (Pin 15)** | 220Ω | Blue channel |
| **Cathode (-)** | **GND (Pin 9)** | - | Common ground |

#### Wiring Diagram

```
        220Ω           RPi5
Red  ───────┬─────── GPIO 17 (Pin 11)
            │
Green ──────┼─────── GPIO 27 (Pin 13)
            │
Blue ───────┼─────── GPIO 22 (Pin 15)
            │
Cathode ────┴─────── GND (Pin 9)
```

---

### Buttons

#### Tactile Push Buttons (3x)

| Button | RPi5 GPIO Pin | Function | Pull-up |
|--------|---------------|----------|---------|
| **Power** | **GPIO 23 (Pin 16)** | Shutdown script | Internal |
| **Mute** | **GPIO 24 (Pin 18)** | Disable microphone | Internal |
| **User** | **GPIO 25 (Pin 22)** | Cycle modes | Internal |

#### Button Wiring (Pull-up Configuration)

```
Button                RPi5
  ┌─┐
  │ │ Push Button
  └┬┘
   ├──────────────── GPIO Pin (with internal pull-up enabled)
   │
   └──────────────── GND
```

**Configuration in Python:**
```python
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup(23, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Power button
GPIO.setup(24, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Mute button
GPIO.setup(25, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # User button
```

---

### OLED Display (I2C - SSD1306)

#### Pin Connections

| OLED Pin | RPi5 Pin | Function |
|----------|----------|----------|
| **VCC** | **Pin 1 (3.3V)** | Power |
| **GND** | **Pin 9 (GND)** | Ground |
| **SCL** | **Pin 5 (GPIO 3)** | I2C Clock |
| **SDA** | **Pin 3 (GPIO 2)** | I2C Data |

#### Wiring Diagram

```
OLED (128x64)         Raspberry Pi 5
┌──────────┐         ┌────────────────┐
│   VCC    ├─────────┤ Pin 1 (3.3V)   │
│   GND    ├─────────┤ Pin 9 (GND)    │
│   SCL    ├─────────┤ Pin 5 (GPIO 3) │
│   SDA    ├─────────┤ Pin 3 (GPIO 2) │
└──────────┘         └────────────────┘
```

#### Enable I2C on Raspberry Pi

```bash
sudo raspi-config
# Interface Options → I2C → Enable

# Verify I2C devices
sudo i2cdetect -y 1
# Should show device at 0x3C or 0x3D
```

---

## Power Distribution

### Option 1: Separate Power Supplies (Simplest)
```
Wall Outlet
    │
    ├─── USB-C (5V/5A) ──→ Raspberry Pi 5
    └─── USB-C/Micro ─────→ ESP32-S3
```

### Option 2: Single Power Supply with USB Hub
```
Wall Outlet
    │
USB Power Supply (5V/10A)
    │
Powered USB Hub
    ├─── USB-C ──→ Raspberry Pi 5 (5V/5A)
    ├─── USB ────→ ESP32-S3 (5V/1A)
    └─── USB ────→ USB Microphone
```

### Option 3: Battery Powered
```
20,000mAh Power Bank (USB-C PD)
    │
    ├─── USB-C PD (5V/5A) ──→ Raspberry Pi 5
    └─── USB-A (5V/2A) ─────→ ESP32-S3
```

---

## Complete System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      External Connections                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Wall Power ──→ [5V/5A PSU] ──→ RPi5 USB-C                  │
│             └──→ [ESP32 USB]                                 │
│                                                              │
│  USB Mic ──────────────────────→ RPi5 USB-A                 │
│  Speakers ←────────────────────── RPi5 3.5mm/I2S            │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     Internal Connections                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ESP32-S3 ←──[I2S]──← MEMS Mic (ICS-43434)                 │
│     │                                                        │
│     └──[UART]──→ RPi5 GPIO (TX/RX)                         │
│                                                              │
│  RPi5 GPIO ──→ Status LEDs                                  │
│          ├───→ Buttons (Power, Mute, User)                 │
│          └───→ OLED Display (I2C)                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Testing Checklist

### ESP32 Tests
- [ ] I2S microphone detected (check serial output)
- [ ] Wake word "Marvin" triggers detection
- [ ] Serial communication sends "WAKE_WORD_DETECTED\n"

### Raspberry Pi Tests
- [ ] USB microphone detected (`arecord -l`)
- [ ] Audio playback works (`aplay test.wav`)
- [ ] Serial port accessible (`ls /dev/ttyAMA0`)
- [ ] GPIO buttons respond (if connected)
- [ ] I2C display shows output (if connected)

### Integration Tests
- [ ] ESP32 wake word triggers RPi chatbot
- [ ] Full conversation flow works end-to-end
- [ ] No audio feedback loops
- [ ] Power consumption acceptable

---

## Troubleshooting

### ESP32 Issues

**"I2S microphone not detected"**
- Check VDD is 3.3V, NOT 5V
- Verify pin connections match config.h
- Test with I2S scanner sketch

**"Wake word not triggering"**
- Lower detection threshold in code (0.95 → 0.90)
- Check microphone positioning
- View serial output for confidence scores

### Raspberry Pi Issues

**"USB microphone not found"**
```bash
# Check if device detected
lsusb
# Check ALSA devices
arecord -L
```

**"No serial communication"**
- Verify UART enabled in /boot/config.txt
- Check TX/RX not swapped
- Ensure common ground connection

**"Audio output not working"**
```bash
# Test audio
speaker-test -t wav -c 2
# Check output devices
aplay -L
```

### GPIO Issues

**"Buttons not responding"**
- Enable internal pull-ups in code
- Add 0.1µF capacitor for debouncing
- Check continuity with multimeter

---

For software setup, see [../rpi5-chatbot/INSTALLATION.md](../rpi5-chatbot/INSTALLATION.md).
