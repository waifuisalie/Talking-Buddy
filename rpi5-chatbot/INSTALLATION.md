# Raspberry Pi 5 Installation Guide - Voice Chatbot System

**Target System**: Raspberry Pi 5, Debian 13, headless (terminal only)

**Prerequisites Already Installed**:
- Python 3
- pygame, pyaudio, pyserial, numpy
- git
- platformio
- nvim
- ollama with gemma3:1b
- fastfetch

---

## Phase 1: Install System Dependencies

### 1.1 Update System
```bash
sudo apt update
sudo apt upgrade -y
```

### 1.2 Install Build Tools
```bash
sudo apt install -y build-essential cmake git wget curl
```

### 1.3 Install Audio Development Libraries
```bash
sudo apt install -y portaudio19-dev libsdl2-dev libasound2-dev
```

### 1.4 Verify Installations
```bash
cmake --version
gcc --version
```

---

## Phase 2: Install whisper.cpp

### 2.1 Clone whisper.cpp Repository
```bash
cd ~
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
```

### 2.2 Build whisper.cpp
```bash
mkdir build
cd build
cmake ..
cmake --build . --config Release
```

### 2.3 Verify Binary
```bash
ls -lh ~/whisper.cpp/build/bin/whisper-cli
~/whisper.cpp/build/bin/whisper-cli --help
```

### 2.4 Download Whisper Model (ggml-base.bin)
```bash
cd ~/whisper.cpp/models
bash download-ggml-model.sh base
```

### 2.5 Verify Model Download
```bash
ls -lh ~/whisper.cpp/models/ggml-base.bin
```

**Expected output**: File size around 142 MB

---

## Phase 3: Install Piper TTS

### 3.1 Download Piper Pre-built Binary for ARM64
```bash
cd ~
wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_arm64.tar.gz
```

### 3.2 Extract Piper
```bash
mkdir -p ~/piper
tar -xzf piper_arm64.tar.gz -C ~/piper
```

### 3.3 Verify Piper Binary
```bash
ls -lh ~/piper/piper/piper
~/piper/piper/piper --version
```

### 3.4 Download Brazilian Portuguese TTS Model
```bash
cd ~/piper/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json
```

### 3.5 Verify Model Files
```bash
ls -lh ~/piper/piper/pt_BR-faber-medium.onnx*
```

### 3.6 Test Piper TTS
```bash
echo "Olá, isso é um teste do sistema de voz" | ~/piper/piper/piper --model ~/piper/piper/pt_BR-faber-medium.onnx --output_file /tmp/test.wav
```

### 3.7 Check Test Audio File
```bash
ls -lh /tmp/test.wav
file /tmp/test.wav
```

**Expected output**: WAV audio file, around 50-100 KB

---

## Phase 4: Configure Ollama Models

### 4.1 Verify Ollama Service
```bash
systemctl status ollama
```

If not running:
```bash
sudo systemctl start ollama
sudo systemctl enable ollama
```

### 4.2 Verify Existing Model
```bash
ollama list
```

**Expected**: `gemma3:1b` should be listed

### 4.3 Create Custom Portuguese Model
```bash
cd ~/Documents/TCC_dos_guri/TCC-dos-guri/fucking_with_AI/chatbot
ollama create gemma3-ptbr -f Modelfile.gemma3-ptbr
```

### 4.4 Verify Custom Model Creation
```bash
ollama list
```

**Expected**: Both `gemma3:1b` and `gemma3-ptbr` should be listed

### 4.5 Test Custom Model (Optional)
```bash
ollama run gemma3-ptbr "Hello, how are you?"
```

**Expected**: Response should be in Portuguese despite English input

---

## Phase 5: Configure Python Virtual Environment

### 5.1 Navigate to Chatbot Directory
```bash
cd ~/Documents/TCC_dos_guri/TCC-dos-guri/fucking_with_AI/chatbot
```

### 5.2 Activate Virtual Environment
```bash
source venv/bin/activate
```

### 5.3 Verify Python Packages (Already Installed)
```bash
pip list | grep -E "pygame|pyaudio|pyserial|numpy|requests"
```

**Expected**: All packages should be listed

If any are missing:
```bash
pip install pygame pyaudio pyserial numpy requests
```

---

## Phase 6: Configure Paths in config.py

### 6.1 Check Current Configuration
```bash
cat config.py | grep -A 2 "whisper.cpp\|piper"
```

### 6.2 Update Paths (If Needed)

The config.py expects these paths (which should now match):
- Whisper model: `/home/waifuisalie/whisper.cpp/models/ggml-base.bin`
- Whisper CLI: `/home/waifuisalie/whisper.cpp/build/bin/whisper-cli`
- Piper binary: `/home/waifuisalie/piper/piper/piper`
- Piper model: `pt_BR-faber-medium.onnx`
- Piper model path: `/home/waifuisalie/piper/piper/`

**If paths are different**, edit with:
```bash
nvim config.py
```

Update the following lines:
- Line ~14: `model_path: str = "/home/waifuisalie/whisper.cpp/models/ggml-base.bin"`
- Line ~15: `cli_binary: str = "/home/waifuisalie/whisper.cpp/build/bin/whisper-cli"`
- Line ~66: `binary: str = "/home/waifuisalie/piper/piper/piper"`
- Line ~68: `model_path: str = "/home/waifuisalie/piper/piper/"`

### 6.3 Create Conversation History Directory
```bash
mkdir -p ~/.voice_chatbot
```

---

## Phase 7: ESP32 Wake Word Setup

### 7.1 Check ESP32 Connection
With ESP32 connected via USB:
```bash
ls -l /dev/ttyACM*
```

**Expected**: `/dev/ttyACM0` should be listed

### 7.2 Check User Permissions
```bash
groups
```

If `dialout` is NOT listed:
```bash
sudo usermod -a -G dialout $USER
```

**Note**: You'll need to log out and back in for group changes to take effect

### 7.3 Test ESP32 Serial Communication
```bash
python test_esp32_serial.py
```

**Expected**:
- "Listening for wake word on /dev/ttyACM0..."
- When you say "Marvin": "WAKE_WORD_DETECTED"

Press Ctrl+C to exit test

---

## Phase 8: System Testing

### 8.1 Run Configuration Test
```bash
python run_chatbot.py --test
```

**Expected**: All checks should pass:
- Configuration loaded successfully
- Audio system initialized
- Ollama service available
- Piper TTS available

### 8.2 Test TTS Only
```bash
python run_chatbot.py --say "Olá, meu nome é o assistente de voz. Como posso ajudar?"
```

**Expected**: You should hear Portuguese speech output

### 8.3 Test Full System (Keyboard Wake Mode)
```bash
python run_chatbot.py --wake-mode keyboard --model gemma3-ptbr
```

**Instructions**:
1. Press `w` + Enter to simulate wake word
2. System says "Sim?" (listening state)
3. Speak in Portuguese
4. System responds in Portuguese
5. Say "tchau" or "até logo" to trigger sleep
6. Press Ctrl+C to exit

### 8.4 Test Full System (ESP32 Wake Mode - Production)
```bash
python run_chatbot.py --wake-mode serial --serial-port /dev/ttyACM0 --model gemma3-ptbr
```

**Instructions**:
1. Say "Marvin" to wake
2. Wait for "Sim?" confirmation
3. Speak your question in Portuguese
4. Listen to response
5. Say "tchau" to put system to sleep
6. Press Ctrl+C to exit

---

## Phase 9: Verify End-to-End Pipeline

### 9.1 Full Portuguese Test
```bash
python run_chatbot.py --wake-mode serial --model gemma3-ptbr
```

**Test Flow**:
1. **Wake**: Say "Marvin"
2. **Input**: "Qual é a capital do Brasil?"
3. **Expected Response**: Portuguese answer (e.g., "A capital do Brasil é Brasília")
4. **Dismiss**: Say "tchau" or "até logo"
5. **Expected**: System enters sleep mode

### 9.2 Check Conversation History
```bash
cat ~/.voice_chatbot/conversation.json
```

**Expected**: JSON file with your conversation history

---

## Troubleshooting

### Issue: "Ollama service not available"
```bash
# Check if ollama is running
systemctl status ollama

# Start ollama
sudo systemctl start ollama

# Enable on boot
sudo systemctl enable ollama
```

### Issue: "whisper-cli: command not found"
```bash
# Verify binary exists
ls -l ~/whisper.cpp/build/bin/whisper-cli

# Check config.py path matches
grep "cli_binary" config.py
```

### Issue: "Piper binary not found"
```bash
# Verify binary exists
ls -l ~/piper/piper/piper

# Make executable
chmod +x ~/piper/piper/piper

# Test manually
~/piper/piper/piper --version
```

### Issue: "Permission denied: /dev/ttyACM0"
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Log out and back in for changes to take effect
# Or reboot:
sudo reboot

# Verify group membership after login
groups
```

### Issue: PyAudio "PortAudio not found"
```bash
# Install PortAudio development files
sudo apt install -y portaudio19-dev

# Reinstall PyAudio
pip uninstall pyaudio
pip install pyaudio
```

### Issue: Responses in English instead of Portuguese
```bash
# Use the -ptbr model variant
python run_chatbot.py --model gemma3-ptbr --language pt-br

# Or recreate the custom model
ollama create gemma3-ptbr -f Modelfile.gemma3-ptbr
```

### Issue: "No module named 'serial'"
```bash
pip install pyserial
```

---

## Quick Reference Commands

### Start Chatbot (Production Mode)
```bash
cd ~/Documents/TCC_dos_guri/TCC-dos-guri/fucking_with_AI/chatbot
source venv/bin/activate
python run_chatbot.py --wake-mode serial --model gemma3-ptbr
```

### Start Chatbot (Testing Mode - Keyboard Wake)
```bash
cd ~/Documents/TCC_dos_guri/TCC-dos-guri/fucking_with_AI/chatbot
source venv/bin/activate
python run_chatbot.py --wake-mode keyboard --model gemma3-ptbr
```

### Start Chatbot (Always-On Mode - No Wake Word)
```bash
cd ~/Documents/TCC_dos_guri/TCC-dos-guri/fucking_with_AI/chatbot
source venv/bin/activate
python run_chatbot.py --wake-mode disabled --model gemma3-ptbr
```

### Clear Conversation History
```bash
python run_chatbot.py --clear-history
```

### Test TTS
```bash
python run_chatbot.py --say "Este é um teste"
```

### View All Available Models
```bash
ollama list
```

### Monitor Ollama Logs
```bash
journalctl -u ollama -f
```

---

## Performance Notes for Raspberry Pi 5

### Recommended Settings (config.py)
- **Model**: `gemma3:1b` or `gemma3-ptbr` (1.0 GB RAM, 2.05s response)
- **Max tokens**: 150-250
- **Temperature**: 0.7
- **Whisper model**: ggml-base.bin (good balance)

### For Better Speed
- Use `gemma3-ptbr` model (fastest)
- Lower `max_tokens` to 150 in config.py
- Lower `temperature` to 0.5 in config.py

### For Better Quality
- Keep default settings
- Increase `max_tokens` to 250
- Consider `qwen2.5:1.5b` if more RAM available

---

## System Architecture Summary

```
ESP32-S3 (Wake Word "Marvin")
    ↓
Serial → esp32_wake_listener.py
    ↓
VoiceChatbot (State: LISTENING)
    ↓
PyAudio + whisper.cpp → WhisperSTT (Portuguese transcription)
    ↓
OllamaLLM (gemma3-ptbr model) → Portuguese response
    ↓
PiperTTS (pt_BR-faber-medium) → WAV audio
    ↓
Pygame Mixer → Speaker output
    ↓
dismissal_detector.py → Sleep on "tchau"
```

---

## Installation Complete Checklist

- [ ] Phase 1: System dependencies installed
- [ ] Phase 2: whisper.cpp compiled and model downloaded
- [ ] Phase 3: Piper TTS installed with PT-BR model
- [ ] Phase 4: Custom Ollama model created (gemma3-ptbr)
- [ ] Phase 5: Python environment configured
- [ ] Phase 6: Paths updated in config.py
- [ ] Phase 7: ESP32 serial connection verified
- [ ] Phase 8: System tests passed
- [ ] Phase 9: End-to-end Portuguese pipeline verified

---

**Installation Time Estimate**: 30-45 minutes (depends on download speeds and compilation)

**Storage Required**: ~3-4 GB total
- whisper.cpp + model: ~500 MB
- Piper + model: ~150 MB
- Ollama gemma3:1b: ~1.5 GB
- Build tools and libraries: ~500 MB
- Working space: ~500 MB

**System Ready**: After completing all phases, you'll have a fully functional voice-activated AI assistant that:
- Wakes with "Marvin" (ESP32)
- Listens and transcribes in Portuguese (Whisper)
- Responds intelligently in Portuguese (Ollama + Gemma3)
- Speaks responses naturally (Piper TTS)
- Sleeps on "tchau" (dismissal detection)
- Runs entirely locally on Raspberry Pi 5

---

For more details, see:
- `ESP32_WAKE_WORD_SYSTEM.md` - Wake word system documentation
- `SLEEP_STATES_EXPLAINED.md` - Sleep modes technical details
- `README.md` - Project overview
- `QUICK_START.md` - Quick reference guide
