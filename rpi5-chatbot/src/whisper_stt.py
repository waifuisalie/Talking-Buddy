"""
Speech-to-Text module using whisper.cpp CLI - RPI5 Edition

This implementation:
1. Records audio while user speaks using ALSA device names
2. Detects silence to know when user finished
3. Saves audio to temp WAV file
4. Runs whisper-cli subprocess on the file (-t 4 -ac 512 for fast ARM inference)
5. Returns clean transcription text

RPI5 MODIFICATIONS:
- Uses ALSA device name (plughw:CARD=Device,DEV=0) instead of card index
- Auto-detects PyAudio device index from ALSA name for stability
- Uses -ac 512 to cap audio context window for faster Cortex-A76 inference
"""

import queue
import subprocess
import wave
import tempfile
import time
import threading
from collections import deque
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

from contextlib import contextmanager

@contextmanager
def _suppress_audio_init_noise():
    """Redirect fd 2 to /dev/null during PyAudio() init.

    redirect_stderr() only moves Python's sys.stderr; ALSA and Jack write
    directly to the underlying OS file-descriptor 2, so they slip through.
    Replacing fd 2 at the OS level silences both.
    """
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_fd = os.dup(2)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    try:
        yield
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)

import config


class WhisperSTT:
    """Handles speech-to-text using whisper.cpp CLI with VAD - RPI5 Edition"""

    def __init__(self, whisper_config: config.WhisperConfig, callback: Optional[Callable[[str], None]] = None,
                 on_speech_detected: Optional[Callable[[], None]] = None,
                 device_detector: Optional['audio_device_detector.AudioDeviceDetector'] = None):
        self.config = whisper_config
        self.callback = callback
        self.on_speech_detected = on_speech_detected  # NEW: Callback when speech is detected
        self.device_detector = device_detector  # NEW: Audio device detector for auto-detection

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
        self._audio_lock = threading.Lock()  # mutual exclusion: calibration vs recording

        # Recording buffers
        self.audio_frames = []
        self.last_audio_time = 0

        # Debug monitoring
        self.last_debug_time = 0
        self.debug_interval = 2.0  # Print RMS every 2 seconds in debug mode

        # Threading
        self.recording_thread = None
        self._is_processing = False          # True while Whisper worker is running
        self._processing_queue = queue.Queue(maxsize=1)  # Frames handed off to worker
        self._processing_thread = None       # Worker thread for Whisper

    def _matches_hw_address(self, device_name: str, info_name_lower: str) -> bool:
        """Match ALSA numeric addresses like plughw:2,0 against PyAudio names."""
        try:
            import re
            hw_match = re.search(r'(?:^|:)(?:plughw|hw):(\d+),(\d+)', device_name.lower())
            if not hw_match:
                return False
            card_num, dev_num = hw_match.groups()
            return f"hw:{card_num},{dev_num}" in info_name_lower
        except Exception:
            return False

    def _find_device_index_by_name(self, device_name: str) -> Optional[int]:
        """Find PyAudio input device index from ALSA-like device name."""
        if not self.audio:
            return None

        try:
            device_count = self.audio.get_device_count()
            device_name_lower = device_name.lower()

            for i in range(device_count):
                info = self.audio.get_device_info_by_index(i)
                if info['maxInputChannels'] <= 0:
                    continue

                info_name_lower = info['name'].lower()

                # 1) Exact substring match
                if device_name_lower in info_name_lower:
                    print(f"🎤 Found matching device: {info['name']} (index {i})")
                    return i

                # 2) Numeric ALSA match (plughw:2,0 -> (hw:2,0))
                if self._matches_hw_address(device_name, info_name_lower):
                    print(f"🎤 Found device by hw address: {info['name']} (index {i})")
                    return i

                # 3) USB keyword match
                if 'usb' in device_name_lower and 'usb' in info_name_lower:
                    print(f"🎤 Found USB microphone: {info['name']} (index {i})")
                    return i

                # 4) Card name from ALSA syntax (CARD=Device)
                import re
                card_match = re.search(r'CARD=([^,]+)', device_name)
                if card_match:
                    card_name = card_match.group(1).lower()
                    if card_name in info_name_lower:
                        print(f"🎤 Found device by card name: {info['name']} (index {i})")
                        return i

            print(f"⚠️  Could not find device matching '{device_name}', using default")
            return None

        except Exception as e:
            print(f"⚠️  Error finding device by name: {e}, using default")
            return None

    def _resolve_input_device_index_with_audio(self, audio, context: str) -> Optional[int]:
        """Resolve a valid input device index with safe fallbacks."""
        device_index = None

        if hasattr(self.config, 'capture_device_name') and self.config.capture_device_name:
            requested_name = self.config.capture_device_name
            device_index = self._find_device_index_by_name_with_audio(audio, requested_name)
            if device_index is None:
                print(f"⚠️  [{context}] Não encontrou '{requested_name}', tentando fallback")

        if device_index is None and self.config.capture_device >= 0:
            try:
                info = audio.get_device_info_by_index(self.config.capture_device)
                if info.get('maxInputChannels', 0) > 0:
                    device_index = self.config.capture_device
                else:
                    print(f"⚠️  [{context}] capture_device={self.config.capture_device} não é entrada; ignorando")
            except Exception as e:
                print(f"⚠️  [{context}] capture_device={self.config.capture_device} inválido: {e}")

        if device_index is None:
            try:
                default_info = audio.get_default_input_device_info()
                device_index = int(default_info['index'])
            except Exception as e:
                print(f"⚠️  [{context}] Sem dispositivo de entrada padrão: {e}")

        if device_index is None:
            try:
                for i in range(audio.get_device_count()):
                    info = audio.get_device_info_by_index(i)
                    if info.get('maxInputChannels', 0) > 0:
                        device_index = i
                        break
            except Exception as e:
                print(f"⚠️  [{context}] Falha ao enumerar entradas: {e}")

        return device_index

    def start(self) -> bool:
        """Start the audio recording system"""
        if not pyaudio:
            print("❌ PyAudio not available")
            return False

        try:
            with _suppress_audio_init_noise():
                self.audio = pyaudio.PyAudio()

            # Auto-detect input device if enabled
            device_index = None
            device_source = "auto-detected"  # Track how device was selected
            if self.config.auto_detect_input and self.device_detector:
                # Determine source of device selection
                if self.config.input_device_preference:
                    device_source = "user-specified"
                elif self.config.capture_device_name:
                    device_source = "from config"

                detected = self.device_detector.detect_input_device(
                    user_preference=self.config.input_device_preference,
                    config_preference=self.config.capture_device_name
                )
                if detected:
                    device_index = detected.index
                    if detected.alsa_name:
                        os.environ['AUDIODEV'] = detected.alsa_name
                    print(f"🎤 Input: {detected.name} ({device_source})")
                else:
                    print("⚠️  Auto-detection failed, using fallback")
                    device_source = "fallback"

            # Fallback path used by web/API mode (safe against stale indices)
            if device_index is None:
                if hasattr(self.config, 'capture_device_name') and self.config.capture_device_name:
                    os.environ['AUDIODEV'] = self.config.capture_device_name
                device_index = self._resolve_input_device_index_with_audio(self.audio, context="STT")

            # Check device sample rate and adjust if needed
            actual_sample_rate = self.config.sample_rate
            if device_index is not None:
                device_info = self.audio.get_device_info_by_index(device_index)
                device_rate = int(device_info['defaultSampleRate'])

                # If device doesn't support our configured rate, use device's native rate
                # whisper.cpp can handle various sample rates (will resample internally)
                try:
                    self.audio.is_format_supported(
                        self.config.sample_rate,
                        input_device=device_index,
                        input_channels=1,
                        input_format=pyaudio.paInt16
                    )
                except ValueError:
                    print(f"⚠️  Device doesn't support {self.config.sample_rate} Hz, using native {device_rate} Hz")
                    print(f"   (Whisper will handle resampling)")
                    actual_sample_rate = device_rate

            # Open audio stream
            stream_kwargs = {
                'format': pyaudio.paInt16,
                'channels': 1,
                'rate': actual_sample_rate,
                'input': True,
                'frames_per_buffer': self.config.chunk_size
            }

            # Only add device index if we found one
            if device_index is not None:
                stream_kwargs['input_device_index'] = device_index

            self.stream = self.audio.open(**stream_kwargs)

            # Store actual rate for WAV file creation
            self._actual_sample_rate = actual_sample_rate

            self.is_running = True
            self.is_paused = False  # Ensure not paused on start
            self.is_recording = False  # Reset VAD state from previous session
            self.audio_frames = []  # Clear stale audio data
            self._is_processing = False  # Reopen VAD gate
            self.last_audio_time = 0  # Reset silence timer baseline

            # RMS smoothing window — filters transient noise spikes that defeat
            # silence detection, especially at high native sample rates (44100 Hz)
            # where each chunk is only ~23ms and noise can randomly exceed threshold.
            chunks_per_second = actual_sample_rate / self.config.chunk_size
            self._rms_window_size = max(3, int(0.2 * chunks_per_second))  # ~0.2s window
            self._rms_history = deque(maxlen=self._rms_window_size)

            # Start recording thread
            self.recording_thread = threading.Thread(target=self._recording_loop, daemon=True, name="WhisperRecording")
            self.recording_thread.start()

            # Start processing worker thread (runs Whisper asynchronously)
            self._processing_thread = threading.Thread(target=self._processing_worker, daemon=True, name="WhisperProcessing")
            self._processing_thread.start()

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

        # Stop the stream BEFORE joining — this unblocks any pending
        # stream.read() call that may be stuck in the ALSA driver.
        # The recording loop's OSError handler will catch the interruption,
        # see is_running=False, and exit cleanly.
        if self.stream:
            try:
                self.stream.stop_stream()
            except Exception:
                pass

        # Wait for recording thread to finish gracefully
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=2.0)
            if self.recording_thread.is_alive():
                print("⚠️  Recording thread did not exit cleanly")

        # Wait for processing worker (Whisper can take up to 30s on RPi5)
        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=35.0)
            if self._processing_thread.is_alive():
                print("⚠️  Processing thread did not exit cleanly")

        # Now close the stream and audio resources
        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
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
            self._is_processing = False  # Safety reset — ensure VAD gate is open
            # Clear any accumulated frames during pause
            self.audio_frames = []
            self.is_recording = False
            if hasattr(self, '_rms_history'):
                self._rms_history.clear()  # Fresh smoothing window after pause
            if self.debug_mode:
                print("▶️  Recording resumed")

    def _recording_loop(self):
        """Main recording loop with VAD.

        ALWAYS reads from stream regardless of paused/processing state to prevent
        ALSA buffer overflow. When paused or processing, data is read and discarded.
        Whisper CLI is offloaded to _processing_worker so this loop never blocks.
        """
        print("👂 Listening for speech...")
        if self.debug_mode:
            print(f"🔧 Debug mode enabled - Threshold: {self.silence_threshold}")
            print(f"🔧 Will show RMS levels every {self.debug_interval}s")

        while self.is_running:
            try:
                # ALWAYS read from stream — prevents ALSA buffer overflow
                # regardless of paused/processing state
                audio_data = self.stream.read(self.config.chunk_size, exception_on_overflow=False)

                # Not user's turn — drain buffer and discard
                if self.is_paused or self._is_processing:
                    continue

                # --- VAD logic ---
                audio_array = np.frombuffer(audio_data, dtype=np.int16)

                # Calculate instant RMS (volume level) with NaN protection
                try:
                    rms_squared = np.mean(audio_array.astype(np.float64)**2)
                    if np.isnan(rms_squared) or np.isinf(rms_squared) or rms_squared < 0:
                        rms_instant = 0.0
                    else:
                        rms_instant = np.sqrt(rms_squared)
                except (ValueError, RuntimeWarning):
                    rms_instant = 0.0

                # Smoothed RMS — rolling average filters transient noise spikes
                # that otherwise reset the silence timer every few ms at 44100 Hz.
                self._rms_history.append(rms_instant)
                rms = sum(self._rms_history) / len(self._rms_history)

                # Debug output - show RMS levels periodically
                current_time = time.time()
                if self.debug_mode and (current_time - self.last_debug_time) >= self.debug_interval:
                    status = "🗣️ SPEECH" if rms > self.silence_threshold else "🤫 silence"
                    print(f"🔊 RMS: {rms:6.1f} (raw {rms_instant:5.0f}) | Threshold: {self.silence_threshold} | {status}")
                    self.last_debug_time = current_time

                # Voice Activity Detection
                if rms > self.silence_threshold:
                    # Speech detected
                    if not self.is_recording:
                        print("🗣️  Speech detected, recording...")
                        self.is_recording = True
                        self.audio_frames = []
                        if self.on_speech_detected:
                            try:
                                self.on_speech_detected()
                            except Exception as e:
                                print(f"❌ Error in speech detection callback: {e}")

                    self.audio_frames.append(audio_data)
                    self.last_audio_time = time.time()

                elif self.is_recording:
                    # Silence detected while recording
                    silence_duration = time.time() - self.last_audio_time

                    if silence_duration < self.silence_duration_limit:
                        # Short silence — keep accumulating
                        self.audio_frames.append(audio_data)
                    else:
                        # Long enough silence — hand off to worker immediately
                        print(f"🤐 Silence detected ({silence_duration:.1f}s), processing...")
                        config.tlog("[STT] fim de fala detectado pelo VAD")
                        frames = self.audio_frames
                        self.audio_frames = []      # reset buffer immediately
                        self.is_recording = False   # reset VAD state immediately
                        self._is_processing = True  # close VAD gate before queuing
                        try:
                            self._processing_queue.put_nowait(frames)
                        except queue.Full:
                            # Shouldn't happen since _is_processing gates this
                            print("⚠️  Processing queue full, discarding audio")
                            self._is_processing = False

            except OSError as e:
                # Recoverable ALSA errors (underrun, device busy) — log and continue
                if self.is_running:
                    print(f"⚠️  Audio read error (recovering): {e}")
                time.sleep(0.01)
                continue
            except Exception as e:
                if self.is_running:
                    print(f"❌ Fatal error in recording loop: {e}")
                break

    def _processing_worker(self):
        """Worker thread: runs Whisper CLI without blocking the recording loop."""
        while self.is_running:
            try:
                frames = self._processing_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._process_recorded_audio(frames)
            except Exception as e:
                print(f"❌ Error in processing worker: {e}")
            finally:
                self._is_processing = False  # Always reopen VAD gate, even on error

    def _process_recorded_audio(self, frames: list):
        """Process the recorded audio frames with whisper CLI.

        Called from _processing_worker (not the recording loop) so blocking here
        for 5-15s is safe — the recording loop continues draining the ALSA buffer.
        """
        if not frames:
            return

        # Use actual sample rate (which may differ from config if device doesn't support it)
        actual_rate = getattr(self, '_actual_sample_rate', self.config.sample_rate)

        # Check minimum duration
        duration = len(frames) * self.config.chunk_size / actual_rate
        if duration < self.min_audio_length:
            print(f"⏭️  Audio too short ({duration:.1f}s), skipping...")
            return

        try:
            # Save audio to temp WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_path = temp_audio.name

                with wave.open(temp_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
                    wf.setframerate(actual_rate)
                    wf.writeframes(b''.join(frames))

            print(f"💾 Audio saved ({duration:.1f}s), transcribing...")

            # Run faster-whisper (blocking, but we're in the worker thread)
            t_stt = config.tlog("[STT] faster-whisper iniciado")
            transcription = self._transcribe_audio_file(temp_path)
            config.tlog("[STT] transcrição concluída", t_stt)

            # Cleanup temp file
            Path(temp_path).unlink(missing_ok=True)

            if transcription:
                print(f"✅ Transcription: {transcription}")

                if self.callback:
                    self.callback(transcription)

        except Exception as e:
            print(f"❌ Error processing audio: {e}")

    def record_utterance_to_file(self, output_path: str, max_duration: float = 15.0) -> bool:
        """Record one utterance using VAD and save to a WAV file.

        Opens its own independent PyAudio stream so it works even when the
        background recording loop is not running (e.g. web API usage).

        Returns True if speech was captured, False if silence/timeout/error.
        """
        if not pyaudio:
            print("❌ PyAudio not available")
            return False

        _rec_t0 = time.monotonic()
        def _rlog(phase):
            print(f"⏱️  [TIMING] record_utterance {phase} T+{time.monotonic() - _rec_t0:.3f}s")
        _rlog("entry")

        # Acquire lock — waits if calibration is running (max 3s; calibration is at most 2s)
        if not self._audio_lock.acquire(blocking=True, timeout=3.0):
            print("⚠️  [VAD] Could not acquire audio lock")
            return False
        _rlog("lock_acquired")

        audio = None
        stream = None
        try:
            with _suppress_audio_init_noise():
                audio = pyaudio.PyAudio()
            _rlog("pyaudio_init")

            # Resolve a safe input device index (handles stale capture_device values)
            if hasattr(self.config, 'capture_device_name') and self.config.capture_device_name:
                os.environ['AUDIODEV'] = self.config.capture_device_name
            device_index = self._resolve_input_device_index_with_audio(audio, context="VAD")
            _rlog(f"device_resolved idx={device_index}")

            sample_rate = self.config.sample_rate
            chunk_size = self.config.chunk_size

            # Fall back to device's native rate if 16000 Hz isn't supported
            if device_index is not None:
                try:
                    audio.is_format_supported(
                        sample_rate,
                        input_device=device_index,
                        input_channels=1,
                        input_format=pyaudio.paInt16
                    )
                except ValueError:
                    native_rate = int(audio.get_device_info_by_index(device_index)['defaultSampleRate'])
                    print(f"⚠️  [VAD] Device doesn't support {sample_rate} Hz, using native {native_rate} Hz")
                    sample_rate = native_rate

            stream_kwargs = {
                'format': pyaudio.paInt16,
                'channels': 1,
                'rate': sample_rate,
                'input': True,
                'frames_per_buffer': chunk_size,
            }
            if device_index is not None:
                stream_kwargs['input_device_index'] = device_index

            stream = audio.open(**stream_kwargs)
            _rlog(f"stream_open rate={sample_rate} chunk={chunk_size}")

            chunks_per_second = sample_rate / chunk_size
            rms_window_size = max(3, int(0.2 * chunks_per_second))
            rms_history = deque(maxlen=rms_window_size)

            silence_threshold = self.silence_threshold
            silence_duration_limit = self.silence_duration_limit

            frames = []
            recording = False
            last_speech_time = None
            start_time = time.time()
            last_rms_print = 0.0
            rms_print_interval = 0.5  # Print RMS every 0.5s when debug_mode is on

            # Background reader thread: polls get_read_available() so we never
            # block inside stream.read(). This guarantees max_duration is always
            # honoured even if the USB mic stalls.
            _audio_queue = queue.Queue(maxsize=500)
            _reader_stop = threading.Event()

            def _audio_reader():
                _no_data_since = None
                _stall_warned = False
                _recovery_attempted = False
                while not _reader_stop.is_set():
                    try:
                        try:
                            available = stream.get_read_available()
                        except Exception as e:
                            print(f"⚠️  [VAD] Reader: get_read_available() failed: {e} "
                                  f"(active={stream.is_active()}, stopped={stream.is_stopped()})")
                            break
                        if available < chunk_size:
                            now = time.monotonic()
                            if _no_data_since is None:
                                _no_data_since = now
                            stall_dur = now - _no_data_since
                            if stall_dur >= 2.0 and not _stall_warned:
                                _stall_warned = True
                                print(f"⚠️  [VAD] Reader: mic stall detected ({stall_dur:.1f}s no data) "
                                      f"active={stream.is_active()} stopped={stream.is_stopped()}")
                            if stall_dur >= 3.0 and not _recovery_attempted:
                                _recovery_attempted = True
                                print(f"🔄 [VAD] Reader: attempting ALSA recovery (stop+start)...")
                                try:
                                    stream.stop_stream()
                                    stream.start_stream()
                                    print(f"✅ [VAD] Reader: ALSA recovery succeeded")
                                    _no_data_since = None
                                    _stall_warned = False
                                except Exception as re:
                                    print(f"❌ [VAD] Reader: ALSA recovery failed: {re}")
                                    break
                            time.sleep(0.005)
                            continue
                        _no_data_since = None
                        _stall_warned = False
                        _recovery_attempted = False
                        data = stream.read(chunk_size, exception_on_overflow=False)
                        try:
                            _audio_queue.put_nowait(data)
                        except queue.Full:
                            pass
                    except Exception as e:
                        print(f"⚠️  [VAD] Reader error: {e} "
                              f"(active={stream.is_active()}, stopped={stream.is_stopped()})")
                        break

            _reader_thread = threading.Thread(target=_audio_reader, daemon=True, name="VADAudioReader")
            _reader_thread.start()
            _rlog("reader_thread_started")

            # Discard first ~150ms to flush stale ALSA buffer contents.
            discard_chunks = int(0.15 * sample_rate / chunk_size)
            _rlog(f"discard_start chunks={discard_chunks}")
            for i in range(discard_chunks):
                try:
                    _audio_queue.get(timeout=1.0)
                except queue.Empty:
                    break
                if i == 0:
                    _rlog("first_discard_read_returned")
            _rlog("discard_end")

            print("👂 [VAD] Waiting for speech...")
            if self.debug_mode:
                print(f"🔧 [VAD] Threshold: {silence_threshold} | Silence limit: {silence_duration_limit}s")

            _first_loop_read_logged = False
            while True:
                elapsed = time.time() - start_time
                if elapsed >= max_duration:
                    print(f"⏱️  [VAD] Max duration ({max_duration}s) reached")
                    _rlog(f"max_duration_reached elapsed={elapsed:.2f}")
                    break

                try:
                    audio_data = _audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if not _first_loop_read_logged:
                    _rlog("first_loop_read_returned")
                    _first_loop_read_logged = True
                audio_array = np.frombuffer(audio_data, dtype=np.int16)

                try:
                    rms_squared = np.mean(audio_array.astype(np.float64) ** 2)
                    rms_instant = 0.0 if (np.isnan(rms_squared) or np.isinf(rms_squared) or rms_squared < 0) else np.sqrt(rms_squared)
                except (ValueError, RuntimeWarning):
                    rms_instant = 0.0

                rms_history.append(rms_instant)
                rms = sum(rms_history) / len(rms_history)

                # Periodic RMS debug output
                if self.debug_mode:
                    now = time.time()
                    if now - last_rms_print >= rms_print_interval:
                        state = "🗣️  FALA " if rms > silence_threshold else "🤫 silêncio"
                        print(f"🔊 [VAD] RMS: {rms:6.1f} (raw {rms_instant:5.0f}) | threshold: {silence_threshold} | {state}")
                        last_rms_print = now

                if rms > silence_threshold:
                    if not recording:
                        print("🗣️  [VAD] Speech detected, recording...")
                        _rlog("speech_detected")
                        recording = True
                    frames.append(audio_data)
                    last_speech_time = time.time()
                elif recording:
                    frames.append(audio_data)
                    silence_elapsed = time.time() - last_speech_time
                    if silence_elapsed >= silence_duration_limit:
                        print(f"🤐 [VAD] Silence detected ({silence_elapsed:.1f}s), done")
                        _rlog(f"silence_detected silence_elapsed={silence_elapsed:.2f}")
                        break

            # Shutdown reader: stop_stream() first to unblock any in-progress
            # read(), then join, then close. Wrong order causes heap corruption.
            _reader_stop.set()
            _rlog("loop_exit stream_close_start")
            stream.stop_stream()
            _reader_thread.join(timeout=2.0)
            if _reader_thread.is_alive():
                print("⚠️  [VAD] Reader thread did not exit cleanly after stop_stream()")
            stream.close()
            stream = None
            audio.terminate()
            audio = None
            _rlog("stream_close_end")

            if not frames:
                print("⚠️  [VAD] No speech detected")
                return False

            # Check minimum audio length
            duration = len(frames) * chunk_size / sample_rate
            if duration < self.min_audio_length:
                print(f"⚠️  [VAD] Audio too short ({duration:.2f}s)")
                return False

            # Save to WAV (paInt16 = 2 bytes per sample)
            # whisper.cpp handles resampling internally if rate != 16000
            with wave.open(output_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(b''.join(frames))

            print(f"💾 [VAD] Saved {duration:.1f}s of audio to {output_path}")
            _rlog(f"wav_saved duration={duration:.2f}s")
            return True

        except Exception as e:
            print(f"❌ [VAD] Error during recording: {e}")
            _rlog(f"exception {type(e).__name__}")
            return False
        finally:
            if '_reader_stop' in locals():
                _reader_stop.set()
            if '_reader_thread' in locals() and _reader_thread.is_alive():
                if stream:
                    try:
                        stream.stop_stream()
                    except Exception:
                        pass
                _reader_thread.join(timeout=2.0)
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass
            if audio:
                try:
                    audio.terminate()
                except Exception:
                    pass
            self._audio_lock.release()
            _rlog("finally_done lock_released")

    def calibrate_vad(self, duration: float = 2.0) -> Optional[float]:
        """Sample ambient noise and update silence_threshold adaptively.

        Algorithm:
          1. Sample `duration` seconds of audio (opens own stream, non-blocking lock)
          2. Compute RMS per chunk
          3. Reject outliers above median*3 (removes speech contamination)
          4. new_threshold = max(20, int(mean + 2*std))
          5. Update self.silence_threshold in place

        Returns the new threshold, or None if mic was busy (skipped).
        """
        if not pyaudio:
            return None

        if not self._audio_lock.acquire(blocking=False):
            print("🔧 [VAD] Calibration skipped — mic busy")
            return None

        audio = None
        stream = None
        try:
            with _suppress_audio_init_noise():
                audio = pyaudio.PyAudio()

            if hasattr(self.config, 'capture_device_name') and self.config.capture_device_name:
                os.environ['AUDIODEV'] = self.config.capture_device_name
            device_index = self._resolve_input_device_index_with_audio(audio, context="VAD-Calib")

            sample_rate = self.config.sample_rate
            chunk_size = self.config.chunk_size

            # Fall back to device native rate if configured rate isn't supported
            if device_index is not None:
                try:
                    audio.is_format_supported(sample_rate, input_device=device_index,
                                              input_channels=1, input_format=pyaudio.paInt16)
                except ValueError:
                    sample_rate = int(audio.get_device_info_by_index(device_index)['defaultSampleRate'])
                    print(f"⚠️  [VAD] Device doesn't support {self.config.sample_rate} Hz, using {sample_rate} Hz")

            stream_kwargs = {
                'format': pyaudio.paInt16, 'channels': 1,
                'rate': sample_rate, 'input': True,
                'frames_per_buffer': chunk_size,
            }
            if device_index is not None:
                stream_kwargs['input_device_index'] = device_index

            stream = audio.open(**stream_kwargs)

            n_chunks = int(duration * sample_rate / chunk_size)
            deadline = time.monotonic() + duration + 3.0
            rms_values = []
            for _ in range(n_chunks):
                while True:
                    if time.monotonic() > deadline:
                        print("⚠️  [VAD] Calibration aborted — mic stall during read")
                        break
                    try:
                        available = stream.get_read_available()
                    except Exception:
                        available = 0
                    if available >= chunk_size:
                        break
                    time.sleep(0.005)
                else:
                    data = stream.read(chunk_size, exception_on_overflow=False)
                    arr = np.frombuffer(data, dtype=np.int16).astype(np.float64)
                    rms_sq = np.mean(arr ** 2)
                    if not (np.isnan(rms_sq) or np.isinf(rms_sq) or rms_sq < 0):
                        rms_values.append(np.sqrt(rms_sq))
                    continue
                break

            stream.stop_stream()
            stream.close()
            stream = None
            audio.terminate()
            audio = None

            if len(rms_values) < 3:
                print("⚠️  [VAD] Not enough samples for calibration")
                return None

            rms_arr = np.array(rms_values)
            median = float(np.median(rms_arr))
            clean = rms_arr[rms_arr <= median * 3]
            if len(clean) < 3:
                clean = rms_arr

            mean = float(np.mean(clean))
            std = float(np.std(clean))
            new_threshold = max(20, int(mean + 2 * std))

            old = self.silence_threshold
            self.silence_threshold = new_threshold
            print(f"🎚️  [VAD] Calibrated: ambient={mean:.1f} ±{std:.1f} → threshold {old} → {new_threshold}")
            return float(new_threshold)

        except Exception as e:
            print(f"❌ [VAD] Calibration error: {e}")
            return None
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if audio:
                try:
                    audio.terminate()
                except Exception:
                    pass
            self._audio_lock.release()

    def _find_device_index_by_name_with_audio(self, audio, device_name: str) -> Optional[int]:
        """Same as _find_device_index_by_name but uses a provided PyAudio instance."""
        try:
            import re
            device_name_lower = device_name.lower()
            for i in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    info_name_lower = info['name'].lower()
                    if device_name_lower in info_name_lower:
                        return i
                    if self._matches_hw_address(device_name, info_name_lower):
                        return i
                    if 'usb' in device_name_lower and 'usb' in info_name_lower:
                        return i
                    card_match = re.search(r'CARD=([^,]+)', device_name)
                    if card_match and card_match.group(1).lower() in info_name_lower:
                        return i
            return None
        except Exception:
            return None

    def _transcribe_audio_file(self, audio_path: str) -> Optional[str]:
        """Transcribe audio file using whisper CLI"""
        try:
            cmd = [
                self.config.cli_binary,
                "-m", self.config.model_path,
                "-l", self.config.language,
                "-t", str(self.config.threads),
                "--no-timestamps",
                "-otxt",
                "-f", audio_path
            ]
            if hasattr(self.config, 'audio_ctx') and self.config.audio_ctx:
                cmd.extend(["-ac", str(self.config.audio_ctx)])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                output_file = audio_path + ".txt"
                if Path(output_file).exists():
                    with open(output_file, 'r', encoding='utf-8') as f:
                        text = f.read().strip()
                    Path(output_file).unlink(missing_ok=True)
                    return self._clean_transcription(text)
                else:
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
        """Check if whisper CLI binary and model file exist"""
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
