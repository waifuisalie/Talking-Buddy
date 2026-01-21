"""
Audio utilities for the voice chatbot system - RPI5 Edition

RPI5 MODIFICATIONS:
- Configures SDL to use ALSA backend
- Sets ALSA device for HifiBerry DAC output (hw:CARD=sndrpihifiberry,DEV=0)
- Device name stability across reboots
"""

import pygame
import time
import threading
import os
from pathlib import Path
from enum import Enum
from typing import Optional, Callable

# Import config to get audio device settings
try:
    import config
    AUDIO_CONFIG = config.AudioConfig()
except ImportError:
    AUDIO_CONFIG = None

class AudioState(Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"

class AudioPlayer:
    """Handles audio playback with state management - RPI5 Edition"""

    def __init__(self, audio_config: Optional[config.AudioConfig] = None):
        # Use provided config or default
        self.audio_config = audio_config or AUDIO_CONFIG

        # Set SDL environment variables for ALSA device selection
        if self.audio_config and hasattr(self.audio_config, 'playback_device_name'):
            os.environ['SDL_AUDIODRIVER'] = 'alsa'
            os.environ['AUDIODEV'] = self.audio_config.playback_device_name
            print(f"🔊 Audio output: {self.audio_config.playback_device_name}")

        # Initialize pygame mixer
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
        self.state = AudioState.IDLE
        self.current_file = None
        self.is_playing = False
        self.is_looping = False  # Track loop playback
        self._playback_thread = None
        self._stop_event = threading.Event()

    def play(self, audio_file: str, blocking: bool = True,
             on_start: Optional[Callable] = None,
             on_finish: Optional[Callable] = None) -> bool:
        """Play an audio file"""
        try:
            if not Path(audio_file).exists():
                print(f"❌ Audio file not found: {audio_file}")
                return False

            # Stop any current playback
            self.stop()

            self.current_file = audio_file
            self.state = AudioState.PLAYING
            self.is_playing = True

            if on_start:
                on_start()

            print(f"🔊 Playing: {Path(audio_file).name}")

            if blocking:
                return self._play_blocking(on_finish)
            else:
                self._playback_thread = threading.Thread(
                    target=self._play_non_blocking,
                    args=(on_finish,),
                    daemon=True
                )
                self._playback_thread.start()
                return True

        except Exception as e:
            print(f"❌ Error playing audio: {e}")
            self.state = AudioState.IDLE
            self.is_playing = False
            return False

    def _play_blocking(self, on_finish: Optional[Callable] = None) -> bool:
        """Play audio in blocking mode"""
        try:
            pygame.mixer.music.load(self.current_file)
            pygame.mixer.music.play()

            # Wait for playback to finish
            while pygame.mixer.music.get_busy() and not self._stop_event.is_set():
                time.sleep(0.1)

            if on_finish and not self._stop_event.is_set():
                on_finish()

            self.state = AudioState.IDLE
            self.is_playing = False
            return True

        except Exception as e:
            print(f"❌ Error in blocking playback: {e}")
            self.state = AudioState.IDLE
            self.is_playing = False
            return False

    def _play_non_blocking(self, on_finish: Optional[Callable] = None):
        """Play audio in non-blocking mode"""
        try:
            pygame.mixer.music.load(self.current_file)
            pygame.mixer.music.play()

            # Wait for playback to finish
            while pygame.mixer.music.get_busy() and not self._stop_event.is_set():
                time.sleep(0.1)

            if on_finish and not self._stop_event.is_set():
                on_finish()

        except Exception as e:
            print(f"❌ Error in non-blocking playback: {e}")
        finally:
            self.state = AudioState.IDLE
            self.is_playing = False

    def play_loop(self, audio_file: str, on_start: Optional[Callable] = None) -> bool:
        """
        Play an audio file in a continuous loop (non-blocking)
        Use stop_loop() to stop the looping playback
        """
        try:
            if not Path(audio_file).exists():
                print(f"❌ Audio file not found: {audio_file}")
                return False

            # Stop any current playback
            self.stop()

            self.current_file = audio_file
            self.state = AudioState.PLAYING
            self.is_playing = True
            self.is_looping = True

            if on_start:
                on_start()

            print(f"🔊 Playing (loop): {Path(audio_file).name}")

            # Start looping playback in background thread
            self._playback_thread = threading.Thread(
                target=self._play_loop_thread,
                daemon=True
            )
            self._playback_thread.start()
            return True

        except Exception as e:
            print(f"❌ Error playing loop audio: {e}")
            self.state = AudioState.IDLE
            self.is_playing = False
            self.is_looping = False
            return False

    def _play_loop_thread(self):
        """Background thread for looping playback"""
        try:
            pygame.mixer.music.load(self.current_file)
            pygame.mixer.music.play(-1)  # -1 = loop indefinitely

            # Wait until stop is requested
            while self.is_looping and not self._stop_event.is_set():
                time.sleep(0.1)

            pygame.mixer.music.stop()

        except Exception as e:
            print(f"❌ Error in loop playback: {e}")
        finally:
            self.state = AudioState.IDLE
            self.is_playing = False
            self.is_looping = False

    def stop_loop(self):
        """Stop looping playback"""
        if self.is_looping:
            self.is_looping = False
            self._stop_event.set()
            pygame.mixer.music.stop()

            # Wait for playback thread to finish (but not if we're in that thread)
            if self._playback_thread and self._playback_thread.is_alive():
                if threading.current_thread() != self._playback_thread:
                    self._playback_thread.join(timeout=1.0)

            self.state = AudioState.IDLE
            self.is_playing = False
            self._stop_event.clear()
            print("🛑 Loop playback stopped")

    def stop(self):
        """Stop current playback"""
        if self.is_playing or self.is_looping:
            self.is_looping = False
            self._stop_event.set()
            pygame.mixer.music.stop()

            # Wait for playback thread to finish (but not if we're in that thread)
            if self._playback_thread and self._playback_thread.is_alive():
                if threading.current_thread() != self._playback_thread:
                    self._playback_thread.join(timeout=1.0)

            self.state = AudioState.IDLE
            self.is_playing = False
            self._stop_event.clear()
            print("🛑 Audio playback stopped")

    def pause(self):
        """Pause current playback"""
        if self.state == AudioState.PLAYING:
            pygame.mixer.music.pause()
            self.state = AudioState.PAUSED
            print("⏸️ Audio paused")

    def resume(self):
        """Resume paused playback"""
        if self.state == AudioState.PAUSED:
            pygame.mixer.music.unpause()
            self.state = AudioState.PLAYING
            print("▶️ Audio resumed")

    def get_state(self) -> AudioState:
        """Get current audio state"""
        return self.state

    def is_busy(self) -> bool:
        """Check if audio is currently playing"""
        return self.is_playing or pygame.mixer.music.get_busy()

    def cleanup(self):
        """Clean up audio resources"""
        self.stop()
        pygame.mixer.quit()

class StateManager:
    """Manages the overall state of the chatbot system"""

    def __init__(self):
        self.current_state = "idle"
        self.state_callbacks = {}
        self._lock = threading.Lock()

    def set_state(self, new_state: str, data: dict = None):
        """Set the current state and trigger callbacks"""
        with self._lock:
            old_state = self.current_state
            self.current_state = new_state

            print(f"🔄 State: {old_state} → {new_state}")

            # Trigger callbacks for the new state
            if new_state in self.state_callbacks:
                for callback in self.state_callbacks[new_state]:
                    try:
                        callback(old_state, new_state, data or {})
                    except Exception as e:
                        print(f"❌ Error in state callback: {e}")

    def get_state(self) -> str:
        """Get the current state"""
        with self._lock:
            return self.current_state

    def is_state(self, state: str) -> bool:
        """Check if currently in a specific state"""
        return self.get_state() == state

    def register_callback(self, state: str, callback: Callable):
        """Register a callback for a specific state"""
        if state not in self.state_callbacks:
            self.state_callbacks[state] = []
        self.state_callbacks[state].append(callback)

    def unregister_callback(self, state: str, callback: Callable):
        """Unregister a callback for a specific state"""
        if state in self.state_callbacks:
            try:
                self.state_callbacks[state].remove(callback)
            except ValueError:
                pass

class SilenceDetector:
    """Detects when user has stopped speaking"""

    def __init__(self, threshold: float = 2.0):
        self.threshold = threshold
        self.last_activity_time = 0
        self.is_monitoring = False
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self.callbacks = []

    def start_monitoring(self):
        """Start monitoring for silence"""
        if not self.is_monitoring:
            self.is_monitoring = True
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_silence, daemon=True)
            self._monitor_thread.start()
            print("👂 Silence detector started")

    def stop_monitoring(self):
        """Stop monitoring for silence"""
        if self.is_monitoring:
            self.is_monitoring = False
            self._stop_event.set()
            if self._monitor_thread:
                self._monitor_thread.join(timeout=1.0)
            print("🛑 Silence detector stopped")

    def update_activity(self):
        """Update the last activity time"""
        self.last_activity_time = time.time()

    def get_silence_duration(self) -> float:
        """Get current silence duration"""
        if self.last_activity_time == 0:
            return 0
        return time.time() - self.last_activity_time

    def register_callback(self, callback: Callable[[float], None]):
        """Register a callback to be called when silence threshold is reached"""
        self.callbacks.append(callback)

    def _monitor_silence(self):
        """Monitor for silence threshold"""
        while self.is_monitoring and not self._stop_event.is_set():
            time.sleep(0.5)

            if self.last_activity_time > 0:
                silence_duration = self.get_silence_duration()

                if silence_duration >= self.threshold:
                    # Trigger callbacks
                    for callback in self.callbacks:
                        try:
                            callback(silence_duration)
                        except Exception as e:
                            print(f"❌ Error in silence callback: {e}")

                    # Reset activity time to avoid repeated triggers
                    self.last_activity_time = 0

def cleanup_temp_files(directory: str = "/tmp", pattern: str = "tts_response_*.wav"):
    """Clean up temporary audio files"""
    try:
        import glob
        files = glob.glob(f"{directory}/{pattern}")
        cleaned = 0

        for file_path in files:
            try:
                Path(file_path).unlink()
                cleaned += 1
            except Exception as e:
                print(f"❌ Error cleaning {file_path}: {e}")

        if cleaned > 0:
            print(f"🧹 Cleaned up {cleaned} temporary audio files")

    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

def test_audio_system() -> bool:
    """Test if the audio system is working"""
    try:
        # Test pygame mixer initialization
        pygame.mixer.init()

        # Create a simple test tone
        import numpy as np

        # Generate a simple test tone
        sample_rate = 22050
        duration = 0.5
        frequency = 440  # A4 note

        t = np.linspace(0, duration, int(sample_rate * duration), False)
        wave = np.sin(2 * np.pi * frequency * t)

        # Convert to pygame sound
        sound_array = (wave * 32767).astype(np.int16)
        stereo_array = np.zeros((len(sound_array), 2), dtype=np.int16)
        stereo_array[:, 0] = sound_array
        stereo_array[:, 1] = sound_array

        sound = pygame.sndarray.make_sound(stereo_array)
        sound.play()

        time.sleep(duration + 0.1)  # Wait for sound to finish

        pygame.mixer.quit()
        print("✅ Audio system test passed")
        return True

    except Exception as e:
        print(f"❌ Audio system test failed: {e}")
        return False
