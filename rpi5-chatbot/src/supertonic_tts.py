"""
Text-to-Speech module using Supertonic 2

Supertonic 2 is a multilingual TTS engine that provides:
- 9x faster synthesis than Piper (RTF 0.033 vs 0.297)
- 24 voices (8 per language: F1-F5 female, M1-M3 male)
- 3 languages: Portuguese (pt), English (en), Spanish (es)
- Smaller model: 66M parameters (305MB)
"""

import tempfile
import time
import re
from pathlib import Path
from typing import Optional
import numpy as np
import config as _config

# Personality-to-Voice mapping (9 personalities → 8 unique voices)
PERSONALITY_VOICES = {
    "short": "M1",       # Brief → professional male
    "detailed": "F3",    # Thorough → patient female
    "casual": "F1",      # Friendly → warm female
    "neutral": "M2",     # Default → neutral male
    "formal": "M3",      # Professional → authoritative male
    "humorous": "F2",    # Witty → energetic female
    "empathetic": "F4",  # Understanding → caring female
    "educational": "F3", # Teaching → SHARES with 'detailed' (patient female)
    "storyteller": "F5"  # Narrative → expressive female
}

class SupertonicTTS:
    """Handles text-to-speech using Supertonic 2"""

    def __init__(self, supertonic_config):
        """
        Initialize Supertonic TTS

        Args:
            supertonic_config: SupertonicConfig instance with language and personality
        """
        self.config = supertonic_config
        self.temp_files = []  # Track temporary files for cleanup
        self.tts = None       # Lazy-loaded TTS instance
        self._initialized = False

    def _initialize_tts(self):
        """Lazy-load Supertonic TTS engine"""
        if self._initialized:
            return True

        try:
            from supertonic import TTS
            self.tts = TTS()
            self._initialized = True
            print(f"✅ Supertonic 2 TTS initialized (language: {self.config.language}, personality: {self.config.personality})")
            return True
        except ImportError:
            print("❌ Supertonic not installed. Run: pip install supertonic")
            return False
        except Exception as e:
            print(f"❌ Failed to initialize Supertonic TTS: {e}")
            return False

    def synthesize(self, text: str, output_file: Optional[str] = None) -> Optional[str]:
        """Convert text to speech and return the audio file path"""
        try:
            # Ensure TTS is initialized
            if not self._initialize_tts():
                return None

            # Clean text for better TTS
            clean_text = self._clean_text_for_tts(text)

            if not clean_text.strip():
                print("❌ No text to synthesize")
                return None

            # Generate output file path
            if output_file is None:
                timestamp = int(time.time() * 1000)
                output_file = f"{self.config.temp_dir}/tts_response_{timestamp}.wav"

            # Get voice style based on personality
            voice_id = PERSONALITY_VOICES.get(self.config.personality, "M2")  # Default to neutral
            voice_style = self.tts.get_voice_style(voice_id)

            print(f"🔊 Generating speech ({voice_id}): '{clean_text[:50]}{'...' if len(clean_text) > 50 else ''}'")

            # Synthesize audio
            t_tts = _config.tlog(f"[TTS] síntese iniciada ({len(clean_text)} chars)")
            wav_array, duration = self.tts.synthesize(
                clean_text,
                voice_style=voice_style,
                lang=self.config.language
            )

            # Save to file
            self.tts.save_audio(wav_array, output_file)
            _config.tlog("[TTS] síntese concluída", t_tts)

            if Path(output_file).exists():
                # Track temp file for cleanup
                self.temp_files.append(output_file)
                print(f"✅ Speech generated: {output_file} ({float(duration[0]):.2f}s)")
                return output_file
            else:
                print(f"❌ Failed to save audio file: {output_file}")
                return None

        except Exception as e:
            print(f"❌ Error with Supertonic TTS: {e}")
            import traceback
            traceback.print_exc()
            return None

    def synthesize_to_temp(self, text: str) -> Optional[str]:
        """Synthesize text to a temporary file"""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            return self.synthesize(text, temp_file.name)

    def _clean_text_for_tts(self, text: str) -> str:
        """
        Clean text for better TTS pronunciation

        Reused from piper_tts.py with modifications for Supertonic
        """
        # Remove markdown formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Remove bold
        text = re.sub(r'\*(.*?)\*', r'\1', text)      # Remove italic
        text = re.sub(r'_(.*?)_', r'\1', text)        # Remove underline
        text = re.sub(r'`(.*?)`', r'\1', text)        # Remove code blocks

        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

        # Clean up special characters but keep basic punctuation
        text = re.sub(r'[^\w\s.,!?;:()"\'-]', '', text)

        # Handle common abbreviations and contractions (English)
        if self.config.language == "en":
            replacements = {
                "don't": "do not",
                "won't": "will not",
                "can't": "cannot",
                "I'm": "I am",
                "you're": "you are",
                "it's": "it is",
                "that's": "that is",
                "there's": "there is",
                "here's": "here is",
                "what's": "what is",
                "where's": "where is",
                "we're": "we are",
                "they're": "they are",
                "I've": "I have",
                "you've": "you have",
                "we've": "we have",
                "they've": "they have",
                "I'll": "I will",
                "you'll": "you will",
                "we'll": "we will",
                "they'll": "they will"
            }

            for contraction, expansion in replacements.items():
                text = re.sub(r'\b' + re.escape(contraction) + r'\b', expansion, text, flags=re.IGNORECASE)

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Ensure proper sentence ending
        if text and not text.endswith(('.', '!', '?')):
            text += '.'

        return text

    def is_available(self) -> bool:
        """Check if Supertonic TTS is available and configured correctly"""
        try:
            # Try to initialize
            if not self._initialize_tts():
                return False

            # Test with a simple synthesis
            test_text = "Test" if self.config.language == "en" else \
                       "Prueba" if self.config.language == "es" else \
                       "Teste"

            test_result = self.synthesize(test_text, "/tmp/supertonic_test.wav")
            if test_result:
                # Clean up test file
                Path(test_result).unlink(missing_ok=True)
                return True
            else:
                return False

        except Exception as e:
            print(f"❌ Error checking Supertonic availability: {e}")
            return False

    def get_voice_info(self) -> dict:
        """Get information about the current voice configuration"""
        voice_id = PERSONALITY_VOICES.get(self.config.personality, "M2")

        info = {
            "engine": "Supertonic 2",
            "language": self.config.language,
            "personality": self.config.personality,
            "voice_id": voice_id,
            "model_size": "66M parameters (305MB)",
            "available_voices": {
                "female": ["F1", "F2", "F3", "F4", "F5"],
                "male": ["M1", "M2", "M3"]
            },
            "personality_mapping": PERSONALITY_VOICES
        }

        return info

    def cleanup_temp_files(self):
        """Clean up temporary audio files"""
        cleaned = 0
        for temp_file in self.temp_files:
            try:
                if Path(temp_file).exists():
                    Path(temp_file).unlink()
                    cleaned += 1
            except Exception as e:
                print(f"❌ Error cleaning up {temp_file}: {e}")

        if cleaned > 0:
            print(f"🧹 Cleaned up {cleaned} temporary audio files")

        self.temp_files.clear()

    def __del__(self):
        """Cleanup when object is destroyed"""
        self.cleanup_temp_files()
