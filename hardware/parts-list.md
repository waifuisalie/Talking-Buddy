# TalkingBuddy Voice Assistant - Bill of Materials (BOM)

Complete parts list for building the TalkingBuddy Voice Assistant system.

## Core Components

| Component | Qty | Description | Est. Cost (USD) | Notes |
|-----------|-----|-------------|-----------------|-------|
| **Raspberry Pi 5 (4GB)** | 1 | Main processing unit | $60 | 8GB version also supported |
| **ESP32-S3 Dev Board** | 1 | Wake word detection | $15 | Must have 8MB PSRAM |
| **microSD Card (64GB)** | 1 | Storage (Class 10/A1) | $10 | 32GB minimum, 64GB+ recommended |
| **USB Microphone** | 1 | Audio input for conversations | $15 | ALSA-compatible |
| **I2S Microphone (ICS-43434)** | 1 | Audio input for wake word | $3-5 | Or INMP441 equivalent |
| **5V/5A Power Supply** | 1 | USB-C for RPi5 | $12 | Official RPi power supply recommended |

**Core Components Subtotal:** ~$115-120

## Audio Output (Choose One Option)

### Option 1: Simple (3.5mm Audio Jack)
| Component | Qty | Description | Est. Cost (USD) |
|-----------|-----|-------------|-----------------|
| **Powered Speakers** | 1 | 3.5mm input | $10-20 |

### Option 2: Quality (I2S DAC + Amplifier)
| Component | Qty | Description | Est. Cost (USD) |
|-----------|-----|-------------|-----------------|
| **HifiBerry DAC** | 1 | I2S audio DAC | $25-35 |
| **Speaker (3W, 4Ω)** | 1 | Audio output | $5-10 |

### Option 3: Budget (USB Audio)
| Component | Qty | Description | Est. Cost (USD) |
|-----------|-----|-------------|-----------------|
| **USB Audio Adapter** | 1 | Simple USB sound card | $8-12 |
| **Powered Speakers** | 1 | 3.5mm input | $10-20 |

## User Interface (Optional)

| Component | Qty | Description | Est. Cost (USD) | Purpose |
|-----------|-----|-------------|-----------------|---------|
| **Tactile Buttons** | 3 | 6mm push buttons | $2 | Power, Mute, User modes |
| **RGB LED (Common Cathode)** | 1 | Status indicator | $1 | Listening/Processing/Speaking states |
| **Green LED** | 1 | Power indicator | $0.50 | System power on |
| **Potentiometer (10kΩ)** | 1 | Rotary or slide | $2 | Volume control |
| **OLED Display (128x64, I2C)** | 1 | SSD1306 or SH1106 | $8-12 | Status text, animations |
| **MCP3008 ADC** | 1 | 8-channel 10-bit ADC | $3 | For analog inputs (if not using I2C) |
| **Resistors (220Ω, 10kΩ)** | Set | Assorted | $2 | LED current limiting, pull-ups |
| **Capacitors (0.1µF, 10µF)** | Set | Ceramic, electrolytic | $2 | Power filtering, debouncing |

**User Interface Subtotal:** ~$20-25 (for full setup)

## Enclosure & Assembly

| Component | Qty | Description | Est. Cost (USD) |
|-----------|-----|-------------|-----------------|
| **3D Printing Filament** | 200g | PLA or PETG | $5 |
| **Heatsink + Fan** | 1 | RPi5 active cooling kit | $8-12 |
| **Jumper Wires** | Set | Dupont female-female, male-female | $5 |
| **Breadboard** | 1 | Half-size or full | $5 |
| **Screws & Standoffs** | Set | M2.5 (RPi), M3 (case) | $5 |
| **USB Cables** | 2 | USB-C power, USB-A for mic | $8 |

**Enclosure & Assembly Subtotal:** ~$36-41

## Total Cost Estimates

| Configuration | Components | Estimated Total |
|---------------|------------|-----------------|
| **Minimal (3.5mm audio)** | Core + Simple speakers | ~$130-140 |
| **Recommended (I2S DAC)** | Core + HifiBerry + UI | ~$185-200 |
| **Full Featured** | All components | ~$210-230 |
| **Budget Build** | Core + USB audio only | ~$135-145 |

*Prices are estimates and vary by region, supplier, and time. Check current prices on Amazon, AliExpress, Adafruit, SparkFun, etc.*

---

## Alternative Configurations

### Portable/Battery-Powered Build
**Additional Components:**
| Component | Qty | Description | Est. Cost (USD) |
|-----------|-----|-------------|-----------------|
| **Power Bank (20,000mAh)** | 1 | USB-C PD output, 5V/3A+ | $25-40 |
| **DC-DC Buck Converter** | 1 | 5V/5A output (if power bank insufficient) | $8 |
| **Battery Management Board** | 1 | Optional for custom battery | $5-10 |

**Portable Build Cost:** Add ~$30-50 to base configuration

### Performance Build (Raspberry Pi 5 8GB)
| Component | Qty | Description | Est. Cost (USD) |
|-----------|-----|-------------|-----------------|
| **Raspberry Pi 5 (8GB)** | 1 | More RAM for larger models | $80 |
| **NVMe SSD (256GB)** | 1 | Faster storage via M.2 HAT | $30-40 |
| **Official Active Cooler** | 1 | Better thermal management | $5 |

**Performance Build Cost:** Add ~$60-70 to base configuration

### Desktop/Always-On Build
Emphasizes:
- Better speakers (bookshelf speakers + amplifier)
- Larger enclosure with better ventilation
- Wired Ethernet (though offline capable)
- Powered USB hub for peripherals

---

## Purchasing Notes

### Recommended Suppliers

**USA:**
- **Amazon** - Fast shipping, easy returns
- **Adafruit** - Quality components, great documentation
- **SparkFun** - Similar to Adafruit
- **Micro Center** - In-store pickup available

**International:**
- **AliExpress** - Budget option, longer shipping
- **Banggood** - Similar to AliExpress
- **Mouser/Digikey** - Professional-grade, higher prices

**Raspberry Pi:**
- **Approved Resellers** - Check raspberrypi.com/resellers
- **CanaKit** - Complete starter kits available

### Quality Considerations

**Critical Components (Don't Cheap Out):**
1. **Power Supply** - Use official Raspberry Pi power supply or equivalent quality
2. **microSD Card** - Use Class 10, A1-rated from reputable brand (SanDisk, Samsung)
3. **ESP32-S3** - Ensure it has 8MB PSRAM for TensorFlow Lite models
4. **USB Microphone** - Better quality = better speech recognition

**OK to Economize:**
- Generic jumper wires
- Generic buttons and LEDs
- 3D printing filament
- Enclosure hardware

### Bulk Discounts
If building multiple units:
- 5+ units: ~10-15% savings on components
- 10+ units: ~20-25% savings
- Custom PCB becomes cost-effective at 10+ units

---

## Optional Upgrades

### Enhanced Audio Quality
| Component | Est. Cost (USD) | Benefit |
|-----------|-----------------|---------|
| **USB Audio Interface (Focusrite Scarlett)** | $100-150 | Professional audio quality |
| **Studio Microphone + Stand** | $50-100 | Better speech recognition |
| **Powered Studio Monitors** | $100-200 | High-fidelity audio output |

### Enhanced Display
| Component | Est. Cost (USD) | Benefit |
|-----------|-----------------|---------|
| **Touchscreen (3.5" or 5")** | $20-40 | Interactive UI |
| **Larger OLED (2.4")** | $15-20 | Better visibility |

### Connectivity
| Component | Est. Cost (USD) | Benefit |
|-----------|-----------------|---------|
| **Bluetooth Module** | $5-10 | Wireless audio output |
| **WiFi Antenna** | $5 | Better signal (if using network features) |

---

## Tools Required

If you don't already have these:
- Soldering iron + solder (~$20-30 for beginner kit)
- Wire strippers (~$10)
- Small Phillips screwdriver (~$5)
- Multimeter (~$15, helpful for debugging)
- Hot glue gun (~$10, for cable management)

**Tools Total:** ~$60-70 (one-time investment)

---

## Where to Save Money

1. **Skip optional UI components** initially (buttons, LEDs, display)
2. **Use 3.5mm audio** instead of I2S DAC
3. **Buy from AliExpress** if comfortable with longer shipping
4. **Reuse old USB microphone** if you have one
5. **Print enclosure at local makerspace** instead of buying filament

**Absolute Minimum Cost:** ~$100-115 (core components only, reusing what you have)

---

For assembly instructions, see [README.md](README.md) and [wiring-guide.md](wiring-guide.md).
