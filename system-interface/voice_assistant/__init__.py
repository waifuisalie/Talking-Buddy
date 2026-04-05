"""
Voice Assistant Module
Integrated voice and text interaction with Ollama LLM, Supertonic TTS and Whisper STT
"""

from .voice_config import VoiceConfig
from .ollama_client import OllamaClient
from .audio_player import HardwareAudioPlayer
from .conversation_history import ConversationHistory
from .supertonic_tts_client import SupertonicTTSClient
from .streaming import SentenceDetector, StreamingTTSProcessor
from .personality_manager import PersonalityManager
from .rag_manager import RAGManager
from . import memory_manager

__all__ = [
    'VoiceConfig',
    'OllamaClient',
    'HardwareAudioPlayer',
    'ConversationHistory',
    'SupertonicTTSClient',
    'SentenceDetector',
    'StreamingTTSProcessor',
    'PersonalityManager',
    'RAGManager',
    'memory_manager',
]
