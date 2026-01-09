"""
Voice Chatbot Package

A modular voice-to-voice chatbot system integrating:
- whisper.cpp for speech-to-text
- Ollama for language model inference
- Piper for text-to-speech
"""

from .voice_chatbot import VoiceChatbot
from .config import ChatbotConfig

__version__ = "0.1.0"
__all__ = ["VoiceChatbot", "ChatbotConfig"]