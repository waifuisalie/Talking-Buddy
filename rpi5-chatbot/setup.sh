#!/bin/bash
# TalkingBuddy Voice Assistant - Automated Setup Script
# Raspberry Pi 5 installation automation

set -e  # Exit on error

echo "🤖 TalkingBuddy Voice Assistant - Setup"
echo "========================================"
echo ""

# Phase 1: System dependencies
echo "📦 Phase 1: Installing system dependencies..."
sudo apt update
sudo apt install -y build-essential cmake git wget curl
sudo apt install -y portaudio19-dev libsdl2-dev libasound2-dev

# Phase 2: whisper.cpp
echo ""
echo "🎤 Phase 2: Installing whisper.cpp..."
cd ~
if [ ! -d "whisper.cpp" ]; then
    git clone https://github.com/ggerganov/whisper.cpp.git
    cd whisper.cpp
    mkdir -p build
    cd build
    cmake ..
    cmake --build . --config Release
else
    echo "whisper.cpp already exists, skipping download..."
fi

cd ~/whisper.cpp/models
if [ ! -f "ggml-base.bin" ]; then
    echo "Downloading ggml-base.bin model..."
    bash download-ggml-model.sh base
else
    echo "ggml-base.bin model already exists, skipping download..."
fi

# Phase 3: Piper TTS
echo ""
echo "🔊 Phase 3: Installing Piper TTS..."
cd ~
if [ ! -d "piper" ]; then
    wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_arm64.tar.gz
    mkdir -p ~/piper
    tar -xzf piper_arm64.tar.gz -C ~/piper
    rm piper_arm64.tar.gz
else
    echo "Piper already exists, skipping download..."
fi

cd ~/piper/piper
if [ ! -f "pt_BR-faber-medium.onnx" ]; then
    echo "Downloading Brazilian Portuguese TTS model..."
    wget https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx
    wget https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json
else
    echo "PT-BR TTS model already exists, skipping download..."
fi

# Phase 4: Ollama setup
echo ""
echo "🧠 Phase 4: Setting up Ollama..."
if ! systemctl is-active --quiet ollama 2>/dev/null; then
    echo "Ollama service not running. Please install Ollama first:"
    echo "  curl -fsSL https://ollama.com/install.sh | sh"
    echo "Then run this script again."
    exit 1
fi

echo "Pulling base model (gemma3:1b)..."
ollama pull gemma3:1b

# Phase 5: Python environment
echo ""
echo "🐍 Phase 5: Setting up Python environment..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Phase 6: Create custom model
echo ""
echo "🎯 Phase 6: Creating custom Portuguese model..."
cd models/
bash create_model.sh

# Phase 7: Verify installation
echo ""
echo "✅ Phase 7: Verifying installation..."
cd "$SCRIPT_DIR"
python src/run_chatbot.py --test

echo ""
echo "✨ Setup complete!"
echo ""
echo "To start the chatbot:"
echo "  cd $(basename $SCRIPT_DIR)"
echo "  source venv/bin/activate"
echo "  python src/run_chatbot.py --wake-mode keyboard --model gemma3-ptbr"
echo ""
echo "For production with ESP32 wake word:"
echo "  python src/run_chatbot.py --wake-mode serial --model gemma3-ptbr"
echo ""
