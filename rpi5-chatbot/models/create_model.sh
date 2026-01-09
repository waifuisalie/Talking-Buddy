#!/bin/bash
# Create custom Portuguese-forced Ollama model for RPI5
# This script creates gemma3-ptbr from your existing gemma3:1b model

set -e  # Exit on error

echo "🚀 Creating custom Portuguese model: gemma3-ptbr"
echo ""

# Check if ollama is running
if ! systemctl is-active --quiet ollama 2>/dev/null; then
    echo "⚠️  Ollama service is not running"
    echo "   Attempting to start..."
    sudo systemctl start ollama || {
        echo "❌ Failed to start Ollama service"
        echo "   Try manually: sudo systemctl start ollama"
        exit 1
    }
    sleep 2
fi

# Check if gemma3:1b exists
if ! ollama list | grep -q "gemma3:1b"; then
    echo "❌ Base model 'gemma3:1b' not found"
    echo "   Please install it first: ollama pull gemma3:1b"
    exit 1
fi

# Check if gemma3-ptbr already exists
if ollama list | grep -q "gemma3-ptbr"; then
    echo "⚠️  Model 'gemma3-ptbr' already exists"
    read -p "   Do you want to recreate it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "✅ Keeping existing model"
        exit 0
    fi
    echo "   Removing old model..."
    ollama rm gemma3-ptbr || true
fi

# Create the custom model
echo "📝 Creating gemma3-ptbr from Modelfile.gemma3-ptbr..."
if [ ! -f "Modelfile.gemma3-ptbr" ]; then
    echo "❌ Modelfile.gemma3-ptbr not found in current directory"
    echo "   Make sure you're running this from the chatbot_rpi5 directory"
    exit 1
fi

ollama create gemma3-ptbr -f Modelfile.gemma3-ptbr

# Verify creation
if ollama list | grep -q "gemma3-ptbr"; then
    echo ""
    echo "✅ Successfully created gemma3-ptbr!"
    echo ""
    echo "📊 Available models:"
    ollama list
    echo ""
    echo "🎯 You can now run the chatbot with:"
    echo "   ./run_chatbot.py --model gemma3-ptbr --wake-mode keyboard"
else
    echo ""
    echo "❌ Failed to create gemma3-ptbr"
    echo "   Check Ollama logs: journalctl -u ollama -n 50"
    exit 1
fi
