"""
Text-to-Speech module using Piper
"""

import subprocess
import tempfile
import time
import re
from pathlib import Path
from typing import Optional
import config

class PiperTTS:
    """Handles text-to-speech using Piper"""

    def __init__(self, piper_config: config.PiperConfig):
        self.config = piper_config
        self.temp_files = []  # Track temporary files for cleanup

    def synthesize(self, text: str, output_file: Optional[str] = None) -> Optional[str]:
        """Convert text to speech and return the audio file path"""
        try:
            # Clean text for better TTS
            clean_text = self._clean_text_for_tts(text)

            if not clean_text.strip():
                print("❌ No text to synthesize")
                return None

            # Generate output file path
            if output_file is None:
                timestamp = int(time.time() * 1000)
                output_file = f"{self.config.temp_dir}/tts_response_{timestamp}.wav"

            # Full path to model
            model_path = Path(self.config.model_path) / self.config.model

            cmd = [
                self.config.binary,
                "--model", str(model_path),
                "--output_file", output_file
            ]

            print(f"🔊 Generating speech: '{clean_text[:50]}{'...' if len(clean_text) > 50 else ''}'")

            # Run Piper
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            stdout, stderr = process.communicate(input=clean_text)

            if process.returncode == 0 and Path(output_file).exists():
                # Track temp file for cleanup
                self.temp_files.append(output_file)
                print(f"✅ Speech generated: {output_file}")
                return output_file
            else:
                print(f"❌ Piper error (exit code {process.returncode}): {stderr}")
                return None

        except Exception as e:
            print(f"❌ Error with Piper TTS: {e}")
            return None

    def synthesize_to_temp(self, text: str) -> Optional[str]:
        """Synthesize text to a temporary file"""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            return self.synthesize(text, temp_file.name)

    def _clean_text_for_tts(self, text: str) -> str:
        """Clean text for better TTS pronunciation"""
        # Remove markdown formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Remove bold
        text = re.sub(r'\*(.*?)\*', r'\1', text)      # Remove italic
        text = re.sub(r'_(.*?)_', r'\1', text)        # Remove underline
        text = re.sub(r'`(.*?)`', r'\1', text)        # Remove code blocks

        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

        # Clean up special characters but keep basic punctuation
        text = re.sub(r'[^\w\s.,!?;:()"\'-]', '', text)

        # Handle common abbreviations and contractions
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
        """Check if Piper TTS is available and configured correctly"""
        try:
            # Check if binary exists
            if not Path(self.config.binary).exists():
                print(f"❌ Piper binary not found: {self.config.binary}")
                return False

            # Check if model exists
            model_path = Path(self.config.model_path) / self.config.model
            if not model_path.exists():
                print(f"❌ Piper model not found: {model_path}")
                return False

            # Test with a simple synthesis
            test_result = self.synthesize("Test", "/tmp/piper_test.wav")
            if test_result:
                # Clean up test file
                Path(test_result).unlink(missing_ok=True)
                return True
            else:
                return False

        except Exception as e:
            print(f"❌ Error checking Piper availability: {e}")
            return False

    def get_voice_info(self) -> dict:
        """Get information about the current voice model"""
        model_path = Path(self.config.model_path) / self.config.model
        json_path = model_path.with_suffix('.onnx.json')

        info = {
            "model": self.config.model,
            "model_path": str(model_path),
            "model_exists": model_path.exists(),
            "config_exists": json_path.exists()
        }

        # Try to read model config if it exists
        if json_path.exists():
            try:
                import json
                with open(json_path, 'r') as f:
                    model_config = json.load(f)
                    info.update({
                        "language": model_config.get("language", "unknown"),
                        "dataset": model_config.get("dataset", "unknown"),
                        "speaker": model_config.get("speaker_id_map", {})
                    })
            except Exception as e:
                print(f"❌ Error reading model config: {e}")

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