"""
Voice Assistant Module
Integrated voice and text interaction with Ollama LLM, Piper TTS, Supertonic TTS and Whisper STT
"""

from .voice_config import VoiceConfig
from .ollama_client import OllamaClient
from .tts_client import TTSClient
from .audio_player import HardwareAudioPlayer
from .conversation_history import ConversationHistory
from .supertonic_tts_client import SupertonicTTSClient
from .streaming import SentenceDetector, StreamingTTSProcessor

__all__ = [
    'VoiceConfig',
    'OllamaClient',
    'TTSClient',
    'HardwareAudioPlayer',
    'ConversationHistory',
    'SupertonicTTSClient',
    'SentenceDetector',
    'StreamingTTSProcessor',
]
