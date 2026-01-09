"""
Speech-to-Text module using whisper.cpp CLI (not stream) - RPI5 Edition

This implementation:
1. Records audio while user speaks using ALSA device names
2. Detects silence to know when user finished
3. Saves audio to temp WAV file
4. Runs whisper CLI on the file
5. Returns clean transcription text

RPI5 MODIFICATIONS:
- Uses ALSA device name (plughw:CARD=Device,DEV=0) instead of card index
- Auto-detects PyAudio device index from ALSA name for stability
"""

import subprocess
import wave
import tempfile
import time
import threading
from pathlib import Path
from typing import Optional, Callable
import numpy as np
import warnings
import os

# Suppress numpy warnings for sqrt of negative values (happens with silent audio)
warnings.filterwarnings('ignore', category=RuntimeWarning, module='numpy')

try:
    import pyaudio
except ImportError:
    print("⚠️  PyAudio not installed. Run: pip install pyaudio")
    pyaudio = None

import config


class WhisperSTT:
    """Handles speech-to-text using whisper.cpp CLI with VAD - RPI5 Edition"""

    def __init__(self, whisper_config: config.WhisperConfig, callback: Optional[Callable[[str], None]] = None):
        self.config = whisper_config
        self.callback = callback

        # Audio recording
        self.audio = None
        self.stream = None
        self.is_running = False
        self.is_recording = False
        self.is_paused = False  # Pause recording (e.g., when chatbot is speaking)

        # VAD (Voice Activity Detection) settings - now configurable
        self.silence_threshold = self.config.silence_threshold
        self.silence_duration_limit = self.config.silence_duration
        self.min_audio_length = self.config.min_audio_length
        self.debug_mode = self.config.debug_mode

        # Recording buffers
        self.audio_frames = []
        self.last_audio_time = 0

        # Debug monitoring
        self.last_debug_time = 0
        self.debug_interval = 2.0  # Print RMS every 2 seconds in debug mode

        # Threading
        self.recording_thread = None
        self.processing_lock = threading.Lock()

    def _find_device_index_by_name(self, device_name: str) -> Optional[int]:
        """Find PyAudio device index by ALSA device name"""
        if not self.audio:
            return None

        try:
            # Search for device by name pattern
            device_count = self.audio.get_device_count()
            for i in range(device_count):
                info = self.audio.get_device_info_by_index(i)
                # Check if device supports input
                if info['maxInputChannels'] > 0:
                    # Match by name (e.g., "USB" in device_name matches "USB PnP Sound Device")
                    if 'USB' in device_name and 'USB' in info['name']:
                        print(f"🎤 Found USB microphone: {info['name']} (index {i})")
                        return i

            print(f"⚠️  Could not find device matching '{device_name}', using default")
            return None

        except Exception as e:
            print(f"⚠️  Error finding device by name: {e}, using default")
            return None

    def start(self) -> bool:
        """Start the audio recording system"""
        if not pyaudio:
            print("❌ PyAudio not available")
            return False

        try:
            # Set ALSA environment variable for device selection
            if hasattr(self.config, 'capture_device_name') and self.config.capture_device_name:
                os.environ['AUDIODEV'] = self.config.capture_device_name

            # Suppress ALSA warnings (cosmetic only, doesn't affect functionality)
            from contextlib import redirect_stderr
            with open(os.devnull, 'w') as devnull:
                with redirect_stderr(devnull):
                    self.audio = pyaudio.PyAudio()

            # Try to find device by name if configured
            device_index = None
            if hasattr(self.config, 'capture_device_name') and self.config.capture_device_name:
                device_index = self._find_device_index_by_name(self.config.capture_device_name)

            # Fallback to config.capture_device if name search failed
            if device_index is None and self.config.capture_device >= 0:
                device_index = self.config.capture_device

            # Open audio stream
            stream_kwargs = {
                'format': pyaudio.paInt16,
                'channels': 1,
                'rate': self.config.sample_rate,
                'input': True,
                'frames_per_buffer': self.config.chunk_size
            }

            # Only add device index if we found one
            if device_index is not None:
                stream_kwargs['input_device_index'] = device_index

            self.stream = self.audio.open(**stream_kwargs)

            self.is_running = True
            self.is_paused = False  # Ensure not paused on start

            # Start recording thread
            self.recording_thread = threading.Thread(target=self._recording_loop, daemon=True, name="WhisperRecording")
            self.recording_thread.start()

            print("🎤 Whisper STT (CLI mode) started successfully!")
            return True

        except Exception as e:
            print(f"❌ Error starting Whisper STT: {e}")
            print(f"   Device config: {getattr(self.config, 'capture_device_name', 'not set')}")
            return False

    def stop(self):
        """Stop the audio recording system"""
        # Set flag first to signal recording thread to exit
        self.is_running = False

        # Wait for recording thread to finish gracefully
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=2.0)
            if self.recording_thread.is_alive():
                print("⚠️  Recording thread did not exit cleanly")

        # Now it's safe to close the audio stream
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if self.audio:
            self.audio.terminate()
            self.audio = None

        print("🛑 Whisper STT stopped")

    def pause_recording(self):
        """Pause audio recording (e.g., when chatbot is speaking)"""
        if not self.is_paused:
            self.is_paused = True
            if self.debug_mode:
                print("⏸️  Recording paused (preventing acoustic feedback)")

    def resume_recording(self):
        """Resume audio recording"""
        if self.is_paused:
            self.is_paused = False
            # Clear any accumulated frames during pause
            self.audio_frames = []
            self.is_recording = False
            if self.debug_mode:
                print("▶️  Recording resumed")

    def _recording_loop(self):
        """Main recording loop with VAD"""
        print("👂 Listening for speech...")
        if self.debug_mode:
            print(f"🔧 Debug mode enabled - Threshold: {self.silence_threshold}")
            print(f"🔧 Will show RMS levels every {self.debug_interval}s")

        while self.is_running:
            try:
                # Skip processing if recording is paused (e.g., chatbot is speaking)
                if self.is_paused:
                    time.sleep(0.1)  # Avoid busy-waiting
                    continue

                # Read audio chunk
                audio_data = self.stream.read(self.config.chunk_size, exception_on_overflow=False)
                audio_array = np.frombuffer(audio_data, dtype=np.int16)

                # Calculate RMS (volume level)
                rms = np.sqrt(np.mean(audio_array**2))

                # Debug output - show RMS levels periodically
                current_time = time.time()
                if self.debug_mode and (current_time - self.last_debug_time) >= self.debug_interval:
                    status = "🗣️ SPEECH" if rms > self.silence_threshold else "🤫 silence"
                    print(f"🔊 RMS: {rms:6.1f} | Threshold: {self.silence_threshold} | {status}")
                    self.last_debug_time = current_time

                # Voice Activity Detection
                if rms > self.silence_threshold:
                    # Speech detected
                    if not self.is_recording:
                        print("🗣️  Speech detected, recording...")
                        self.is_recording = True
                        self.audio_frames = []

                    self.audio_frames.append(audio_data)
                    self.last_audio_time = time.time()

                elif self.is_recording:
                    # Silence detected while recording
                    silence_duration = time.time() - self.last_audio_time

                    # Still add frames during short silence
                    if silence_duration < self.silence_duration_limit:
                        self.audio_frames.append(audio_data)
                    else:
                        # Long enough silence - process the audio
                        print(f"🤐 Silence detected ({silence_duration:.1f}s), processing...")
                        self._process_recorded_audio()
                        self.is_recording = False
                        self.audio_frames = []

            except Exception as e:
                if self.is_running:  # Only log if not intentionally stopped
                    print(f"❌ Error in recording loop: {e}")
                break

    def _process_recorded_audio(self):
        """Process the recorded audio with whisper CLI"""
        if not self.audio_frames:
            return

        # Check minimum duration
        duration = len(self.audio_frames) * self.config.chunk_size / self.config.sample_rate
        if duration < self.min_audio_length:
            print(f"⏭️  Audio too short ({duration:.1f}s), skipping...")
            return

        with self.processing_lock:
            try:
                # Save audio to temp WAV file
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                    temp_path = temp_audio.name

                    # Write WAV file
                    with wave.open(temp_path, 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
                        wf.setframerate(self.config.sample_rate)
                        wf.writeframes(b''.join(self.audio_frames))

                print(f"💾 Audio saved ({duration:.1f}s), transcribing...")

                # Run whisper CLI
                transcription = self._transcribe_audio_file(temp_path)

                # Cleanup temp file
                Path(temp_path).unlink(missing_ok=True)

                if transcription:
                    print(f"✅ Transcription: {transcription}")

                    # Trigger callback
                    if self.callback:
                        self.callback(transcription)

            except Exception as e:
                print(f"❌ Error processing audio: {e}")

    def _transcribe_audio_file(self, audio_path: str) -> Optional[str]:
        """Transcribe audio file using whisper CLI"""
        try:
            # Build whisper command
            cmd = [
                self.config.cli_binary,
                "-m", self.config.model_path,
                "-l", self.config.language,
                "-t", str(self.config.threads),
                "--no-timestamps",
                "-otxt",  # Output as text
                "-f", audio_path
            ]

            # Add optional flags
            if hasattr(self.config, 'audio_ctx') and self.config.audio_ctx:
                cmd.extend(["-ac", str(self.config.audio_ctx)])

            # Run whisper
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Read output text file (whisper creates filename.wav.txt)
                output_file = audio_path + ".txt"
                if Path(output_file).exists():
                    with open(output_file, 'r', encoding='utf-8') as f:
                        text = f.read().strip()

                    # Cleanup output file
                    Path(output_file).unlink(missing_ok=True)

                    return self._clean_transcription(text)
                else:
                    # Fallback: parse stdout
                    text = result.stdout.strip()
                    if text:
                        return self._clean_transcription(text)
            else:
                print(f"❌ Whisper error: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            print("❌ Whisper transcription timed out")
            return None
        except Exception as e:
            print(f"❌ Error running whisper: {e}")
            return None

    def _clean_transcription(self, text: str) -> str:
        """Clean up transcription text"""
        import re

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # NOTE: Removed aggressive word filtering that was removing legitimate words
        # Previously removed: um|uh|er|ah - but "um" is a valid Portuguese article/number
        # This was causing context loss. Let the LLM handle artifact filtering instead.
        # The AI model is better at understanding context than regex patterns.

        # Remove trailing periods if multiple
        text = re.sub(r'\.+$', '.', text)

        # Ensure capitalization
        if text and text[0].islower():
            text = text[0].upper() + text[1:]

        return text.strip()

    def is_available(self) -> bool:
        """Check if whisper CLI is available"""
        try:
            if not Path(self.config.cli_binary).exists():
                print(f"❌ Whisper binary not found: {self.config.cli_binary}")
                return False

            if not Path(self.config.model_path).exists():
                print(f"❌ Whisper model not found: {self.config.model_path}")
                return False

            return True
        except Exception as e:
            print(f"❌ Error checking availability: {e}")
            return False
