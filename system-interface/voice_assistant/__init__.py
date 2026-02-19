"""
Voice Assistant Module
Integrated voice and text interaction with Ollama LLM, Piper TTS and Whisper STT
Usa módulos do rpi5-chatbot para evitar duplicação
"""

from .voice_config import VoiceConfig
from .ollama_client import OllamaClient
from .tts_client import TTSClient
from .audio_player import HardwareAudioPlayer
from .conversation_history import ConversationHistory

__all__ = [
    'VoiceConfig',
    'OllamaClient',
    'TTSClient',
    'HardwareAudioPlayer',
    'ConversationHistory'
]
