#!/bin/bash
# TalkingBuddy Voice Assistant - Convenience Wrapper
# Run chatbot from anywhere with automatic venv activation

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Run setup.sh first."
    exit 1
fi

source venv/bin/activate
python src/run_chatbot.py "$@"
