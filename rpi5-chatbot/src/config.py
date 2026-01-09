"""
Configuration settings for the voice chatbot system - Raspberry Pi 5 Edition

IMPORTANT: This config is specifically tuned for Raspberry Pi 5 with:
- USB microphone (plughw:CARD=Device,DEV=0)
- HifiBerry DAC output (hw:CARD=sndrpihifiberry,DEV=0)
- Paths in /root/ directory
- gemma3-ptbr model for Portuguese
"""

from dataclasses import dataclass
from pathlib import Path
import os

@dataclass
class WhisperConfig:
    # Model and binary paths - Uses home directory for portability
    model_path: str = os.path.expanduser("~/whisper.cpp/models/ggml-base.bin")  # Multilingual (PT-BR support)
    cli_binary: str = os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli")  # CLI binary (not whisper-stream!)

    # Language and processing
    language: str = "pt"  # Portuguese (change to "en" for English)
    threads: int = 4  # Use all RPi5 cores
    audio_ctx: int = 512  # Reduced context for faster processing

    # Audio recording settings
    sample_rate: int = 16000  # Whisper expects 16kHz
    chunk_size: int = 1024  # PyAudio chunk size

    # ALSA device configuration - STABLE across reboots
    # Use ALSA device name instead of card index for reliability
    capture_device_name: str = "plughw:CARD=Device,DEV=0"  # USB PnP Sound Device (microphone)
    capture_device: int = -1  # Will be auto-detected from device_name, -1 = use name directly

    # VAD (Voice Activity Detection) settings
    # Adjust silence_threshold based on debug output (🔊 RMS values):
    # - Too high (500+): Won't detect speech at all
    # - Too low (<20): Will trigger on background noise
    # - Recommended: Set 20-30% above your typical speaking RMS level
    silence_threshold: int = 30  # RMS threshold for speech detection (tune with debug mode)
    silence_duration: float = 1.5  # Seconds of silence before stopping recording
    min_audio_length: float = 0.5  # Minimum seconds of audio to process
    debug_mode: bool = True  # Enable debug output (RMS levels, etc.)

@dataclass
class OllamaConfig:
    url: str = "http://localhost:11434/api/chat"  # Using /chat endpoint for proper message handling
    model: str = "gemma3-ptbr"  # Default: gemma3 with forced Portuguese (fastest for RPi5)
    temperature: float = 0.7
    max_tokens: int = 250
    timeout: int = 30

    # Available 1B models (recommended for Raspberry Pi 5):
    # NATIVE PORTUGUESE (no forcing):
    #   - qwen2.5:1.5b         (4.50/5 quality, 3.42s, 1.5-2.0 GB) ⭐ QUALITY
    #   - gemma3:1b            (4.25/5 quality, 2.05s, 1.0 GB) ⚡ FASTEST
    #   - gemma3:1b-it-qat     (4.25/5 quality, 2.91s, 1.0 GB) 🎯 TUNED
    #   - llama3.2:1b          (4.00/5 quality, 3.49s, 1.5 GB) 📈 BALANCED
    #
    # PORTUGUESE-FORCED (via Modelfile) - RECOMMENDED FOR CONSISTENCY:
    #   - gemma3-ptbr          (same as gemma3:1b, but forces Portuguese) ⭐ DEFAULT
    #   - qwen2.5-ptbr         (same as above, but forces Portuguese)
    #   - gemma3-it-qat-ptbr   (same as above, but forces Portuguese)
    #   - llama3.2-ptbr        (same as above, but forces Portuguese)
    #   - mistral-ptbr         (7B model, not recommended for RPi5)
    #
    # To switch models:
    #   model: str = "gemma3:1b"        # Use native Gemma3 (fastest)
    #   model: str = "gemma3-ptbr"      # Use Gemma3 with forced Portuguese (RECOMMENDED)
    #   model: str = "llama3.2:1b"      # Use Llama3.2 (best quality)

@dataclass
class PiperConfig:
    binary: str = os.path.expanduser("~/piper/piper/piper")
    model: str = "pt_BR-faber-medium.onnx"  # Brazilian Portuguese TTS model
    model_path: str = os.path.expanduser("~/piper/piper/")
    temp_dir: str = "/tmp"

@dataclass
class AudioConfig:
    silence_threshold: float = 1.0  # seconds
    sample_rate: int = 16000
    chunk_size: int = 1024

    # ALSA output device configuration - STABLE across reboots
    # HifiBerry DAC output (card 2, device 0)
    playback_device_name: str = "hw:CARD=sndrpihifiberry,DEV=0"  # HifiBerry DAC

@dataclass
class ConversationConfig:
    max_history: int = 10  # Keep last 10 exchanges
    system_prompt: str = ""  # Empty for better results with small models

class ChatbotConfig:
    """Main configuration class for the voice chatbot - RPI5 Edition"""

    def __init__(self):
        self.whisper = WhisperConfig()
        self.ollama = OllamaConfig()
        self.piper = PiperConfig()
        self.audio = AudioConfig()
        self.conversation = ConversationConfig()

    def validate(self):
        """Validate that all required files and services exist"""
        errors = []

        # Check whisper files
        if not Path(self.whisper.model_path).exists():
            errors.append(f"Whisper model not found: {self.whisper.model_path}")

        if not Path(self.whisper.cli_binary).exists():
            errors.append(f"Whisper CLI binary not found: {self.whisper.cli_binary}")

        # Check piper files
        if not Path(self.piper.binary).exists():
            errors.append(f"Piper binary not found: {self.piper.binary}")

        piper_model_full_path = Path(self.piper.model_path) / self.piper.model
        if not piper_model_full_path.exists():
            errors.append(f"Piper model not found: {piper_model_full_path}")

        # Check temp directory
        if not Path(self.piper.temp_dir).exists():
            errors.append(f"Temp directory not found: {self.piper.temp_dir}")

        return errors

    @classmethod
    def from_env(cls):
        """Create config from environment variables"""
        config = cls()

        # Override with environment variables if they exist
        if os.getenv("WHISPER_MODEL_PATH"):
            config.whisper.model_path = os.getenv("WHISPER_MODEL_PATH")

        if os.getenv("WHISPER_CLI_BINARY"):
            config.whisper.cli_binary = os.getenv("WHISPER_CLI_BINARY")

        if os.getenv("OLLAMA_URL"):
            config.ollama.url = os.getenv("OLLAMA_URL")

        if os.getenv("OLLAMA_MODEL"):
            config.ollama.model = os.getenv("OLLAMA_MODEL")

        if os.getenv("PIPER_BINARY"):
            config.piper.binary = os.getenv("PIPER_BINARY")

        if os.getenv("PIPER_MODEL_PATH"):
            config.piper.model_path = os.getenv("PIPER_MODEL_PATH")

        return config
