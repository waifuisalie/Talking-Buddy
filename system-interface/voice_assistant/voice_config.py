"""
Configurações do sistema de voz
Adaptado do rpi5-chatbot para integração com system-interface
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class VoiceConfig:
    """Configuração centralizada do sistema de voz"""
    
    # Ollama LLM
    ollama_url: str = "http://localhost:11434/api/chat"
    ollama_model: str = "gemma3:1b"  # 🔥 ATUALIZADO: Melhor modelo para português
    ollama_temperature: float = 0.5  # OTIMIZADO: Reduzido de 0.7 para respostas mais rápidas
    ollama_max_tokens: int = 300  # Limite aumentado para respostas completas
    ollama_timeout: int = 120  # 2 minutos (Raspberry Pi pode ser lento)
    
    # Audio Output (hardware)
    audio_device: str = "default"  # ALSA device (default, hw:0,0, plughw:0,0, etc)
    audio_sample_rate: int = 22050
    
    # Audio Input (microfone USB)
    microphone_device: str = "plughw:2,0"  # ALSA device para microfone
    microphone_sample_rate: int = 16000  # Whisper usa 16kHz
    
    # Diretórios
    temp_dir: str = "/tmp"
    audio_static_dir: str = "static/audio"
    
    # Whisper STT (controle de voz)
    whisper_enabled: bool = False  # Habilitado via .env
    whisper_model: str = "ggml-base.bin"
    whisper_model_path: str = os.path.expanduser("~/whisper.cpp/models")
    whisper_binary: str = os.path.expanduser("~/whisper.cpp/build/bin/main")
    whisper_language: str = "auto"  # Auto-detect; overridden per-request by user's language
    whisper_threads: int = 4
    
    # VAD (Voice Activity Detection)
    silence_threshold: int = 30  # RMS threshold para detectar fala
    silence_duration: float = 0.5  # 🔥 OTIMIZADO: Reduzido de 1.5s para resposta mais rápida
    min_audio_length: float = 0.3  # 🔥 OTIMIZADO: Reduzido de 0.5s para aceitar comandos curtos

    # Supertonic TTS
    tts_engine: str = "supertonic"
    supertonic_enabled: bool = True
    supertonic_language: str = "pt"
    supertonic_personality: str = "neutral"
    
    @classmethod
    def from_env(cls) -> 'VoiceConfig':
        """Carrega configuração de variáveis de ambiente (.env)"""
        return cls(
            # Ollama
            ollama_model=os.getenv('OLLAMA_MODEL', 'gemma3:1b'),  # 🔥 ATUALIZADO
            ollama_url=os.getenv('OLLAMA_URL', 'http://localhost:11434/api/chat'),
            # Audio devices
            audio_device=os.getenv('AUDIO_DEVICE', 'plughw:3,0'),  # USB Audio por padrão
            microphone_device=os.getenv('MICROPHONE_DEVICE', 'plughw:2,0'),
            # Whisper STT
            whisper_enabled=os.getenv('WHISPER_ENABLED', 'false').lower() == 'true',
            whisper_binary=os.path.expanduser(os.getenv('WHISPER_BINARY', '~/whisper.cpp/build/bin/main')),
            whisper_model=os.getenv('WHISPER_MODEL', 'ggml-base.bin'),
            whisper_model_path=os.path.expanduser(os.getenv('WHISPER_MODEL_PATH', '~/whisper.cpp/models')),
            # Supertonic TTS
            tts_engine='supertonic',
            supertonic_enabled=True,
            supertonic_language=os.getenv('SUPERTONIC_LANGUAGE', 'pt'),
            supertonic_personality=os.getenv('SUPERTONIC_PERSONALITY', 'neutral'),
        )
    
    def auto_detect_audio_device(self):
        """
        Detecta automaticamente o melhor dispositivo de áudio
        DESABILITADO: Usa configuração do .env diretamente
        """
        # Não faz nada - usa dispositivo configurado no .env
        print(f"🔊 [Config] Usando dispositivo de áudio: {self.audio_device}")
        pass
    
    def validate(self) -> tuple[bool, list[str]]:
        """Valida configuração e retorna (is_valid, errors)"""
        errors = []
        
        # Verificar diretório de áudio
        if not os.path.exists(self.audio_static_dir):
            try:
                os.makedirs(self.audio_static_dir, exist_ok=True)
            except Exception as e:
                errors.append(f"Erro ao criar diretório de áudio: {e}")
        
        return (len(errors) == 0, errors)

