"""
Main Voice Chatbot Controller

Orchestrates the entire voice-to-voice conversation pipeline:
Microphone → Whisper (CLI mode with VAD) → LLM → Piper → Speaker

Architecture Notes:
- whisper_stt.py now handles audio recording, VAD, and transcription internally
- When user stops speaking (silence detected), whisper_stt calls _on_transcription_received()
- No need for external SilenceDetector or queue accumulation logic
- Simple, clean flow: Record → Transcribe → Callback → Process

Sleep/Wake Integration:
- LIGHT_SLEEP: Ollama loaded, Whisper OFF, waiting for ESP32 wake word
- DEEP_SLEEP: Ollama OFF, minimal power, waiting for ESP32 wake word
- 30-second conversation timeout: Auto-sleep after user stops talking
- 5-minute idle timeout: Deep sleep after extended idle in light sleep
- Dismissal detection: Detect "tchau" etc. → Natural LLM goodbye → Light sleep
"""

import time
import threading
import queue
from pathlib import Path
from typing import Optional, Callable

import config
import whisper_stt
import ollama_llm
import piper_tts
import audio_utils
import conversation
import esp32_wake_listener
import dismissal_detector
import timeout_manager
import sleep_manager
import gpio_controller

class SentenceDetector:
    """Detects sentence boundaries from streaming text chunks"""

    def __init__(self, min_length: int = 30):
        """
        Initialize sentence detector

        Args:
            min_length: Minimum characters for a valid sentence (default: 30)
        """
        self.buffer = ""
        self.sentence_endings = ('.', '!', '?', ':', ';')
        self.min_sentence_length = min_length
        self.paragraph_break = '\n\n'  # Double newline indicates paragraph break

    def add_chunk(self, chunk: str):
        """
        Add a text chunk and return completed sentences

        Args:
            chunk: Text chunk from streaming LLM

        Returns:
            List of complete sentences (may be empty)
        """
        # Accumulate to buffer
        self.buffer += chunk
        sentences = []

        # Debug: Show buffer size periodically
        if len(self.buffer) > 500 and len(self.buffer) % 100 < 10:
            print(f"⚠️  Sentence buffer growing: {len(self.buffer)} chars, preview: {self.buffer[:100]}...")

        # Find sentence boundaries
        while True:
            # Look for sentence ending characters
            earliest_pos = -1
            for ending in self.sentence_endings:
                pos = self.buffer.find(ending)
                if pos != -1:
                    if earliest_pos == -1 or pos < earliest_pos:
                        earliest_pos = pos

            # No sentence ending found
            if earliest_pos == -1:
                break

            # Extract potential sentence (include the ending character)
            potential_sentence = self.buffer[:earliest_pos + 1].strip()

            # Check if it meets minimum length
            if len(potential_sentence) >= self.min_sentence_length:
                sentences.append(potential_sentence)
                # Remove sentence from buffer
                self.buffer = self.buffer[earliest_pos + 1:].strip()
            else:
                # Too short, look for next ending after this one
                # Keep this ending in buffer and look for the next one
                if earliest_pos + 1 < len(self.buffer):
                    # Look for next ending
                    next_earliest = -1
                    for ending in self.sentence_endings:
                        pos = self.buffer.find(ending, earliest_pos + 1)
                        if pos != -1:
                            if next_earliest == -1 or pos < next_earliest:
                                next_earliest = pos

                    if next_earliest != -1:
                        # Found another ending, try combining
                        potential_sentence = self.buffer[:next_earliest + 1].strip()
                        if len(potential_sentence) >= self.min_sentence_length:
                            sentences.append(potential_sentence)
                            self.buffer = self.buffer[next_earliest + 1:].strip()
                        else:
                            # Still too short, break and wait for more chunks
                            break
                    else:
                        # No more endings, break and wait for more chunks
                        break
                else:
                    # At end of buffer, break and wait for more chunks
                    break

        return sentences

    def flush(self):
        """
        Return remaining buffer as final sentence

        Returns:
            Remaining text as final sentence, or None if buffer is empty
        """
        if self.buffer.strip():
            final_sentence = self.buffer.strip()
            self.buffer = ""
            return final_sentence
        return None

class StreamingTTSProcessor:
    """Processes streaming LLM chunks into TTS audio queue"""

    def __init__(self, piper_tts, audio_player, min_sentence_length: int = 30):
        """
        Initialize streaming TTS processor

        Args:
            piper_tts: PiperTTS instance for synthesis
            audio_player: AudioPlayer instance with queue support
            min_sentence_length: Minimum characters for sentence detection
        """
        self.piper_tts = piper_tts
        self.audio_player = audio_player
        self.sentence_detector = SentenceDetector(min_sentence_length)
        self.full_response = ""

    def process_chunk(self, chunk: str):
        """
        Process a text chunk and synthesize completed sentences

        Args:
            chunk: Text chunk from streaming LLM
        """
        # Add chunk to full response for history tracking
        self.full_response += chunk

        # Detect completed sentences
        sentences = self.sentence_detector.add_chunk(chunk)

        # Synthesize each completed sentence
        for sentence in sentences:
            print(f"🎙️ Synthesizing sentence ({len(sentence)} chars): {sentence[:80]}...")
            try:
                audio_file = self.piper_tts.synthesize_to_temp(sentence)
                if audio_file:
                    metadata = {
                        "text": sentence,
                        "cleanup": True
                    }
                    self.audio_player.enqueue_audio(audio_file, metadata)
                    print(f"✅ Enqueued audio for sentence")
                else:
                    print(f"⚠️  Failed to synthesize sentence: {sentence[:50]}...")
            except Exception as e:
                print(f"❌ Error synthesizing sentence: {e}")

    def finalize(self):
        """Synthesize any remaining text in buffer"""
        final_sentence = self.sentence_detector.flush()
        if final_sentence:
            print(f"🎙️ Finalizing: synthesizing remaining buffer ({len(final_sentence)} chars): {final_sentence[:80]}...")
            try:
                audio_file = self.piper_tts.synthesize_to_temp(final_sentence)
                if audio_file:
                    metadata = {
                        "text": final_sentence,
                        "cleanup": True
                    }
                    self.audio_player.enqueue_audio(audio_file, metadata)
                    print(f"✅ Enqueued final audio")
                else:
                    print(f"⚠️  Failed to synthesize final sentence: {final_sentence[:50]}...")
            except Exception as e:
                print(f"❌ Error synthesizing final sentence: {e}")
        else:
            print("ℹ️  No remaining text in buffer to finalize")

    def get_full_response(self) -> str:
        """Get the complete accumulated response text"""
        return self.full_response

class VoiceChatbot:
    """Main voice chatbot system controller"""

    def __init__(self, chatbot_config: Optional[config.ChatbotConfig] = None,
                 wake_listener_mode: esp32_wake_listener.WakeListenerMode = esp32_wake_listener.WakeListenerMode.KEYBOARD,
                 serial_port: str = "/dev/ttyACM0"):
        # Configuration
        self.config = chatbot_config or config.ChatbotConfig()

        # Core components
        self.whisper_stt = None
        self.ollama_llm = None
        self.piper_tts = None
        self.audio_player = None
        self.conversation_manager = None

        # GPIO/LED controller
        self.led_controller = None

        # State management
        self.state_manager = audio_utils.StateManager()
        # NOTE: SilenceDetector is no longer used - whisper_stt.py handles VAD internally
        # self.silence_detector = audio_utils.SilenceDetector(threshold=self.config.audio.silence_threshold)

        # Sleep/wake management
        self.esp32_listener = esp32_wake_listener.ESP32WakeListener(
            serial_port=serial_port,
            mode=wake_listener_mode
        )
        self.dismissal_detector = dismissal_detector.DismissalDetector()
        self.timeout_manager = timeout_manager.TimeoutManager(
            conversation_timeout=30.0,  # 30 seconds
            idle_timeout=300.0          # 5 minutes
        )
        self.sleep_manager = sleep_manager.SleepManager(ollama_url=self.config.ollama.url)

        # Processing queues
        self.transcription_queue = queue.Queue()
        self.response_queue = queue.Queue()

        # Control flags
        self.is_running = False
        self.is_processing = False
        self.is_dismissal_pending = False  # Flag for goodbye detection

        # Callbacks
        self.on_state_change: Optional[Callable] = None
        self.on_user_speech: Optional[Callable] = None
        self.on_ai_response: Optional[Callable] = None

    def initialize(self) -> bool:
        """Initialize all components"""
        print("🚀 Initializing Voice Chatbot...")

        # Validate configuration
        errors = self.config.validate()
        if errors:
            print("❌ Configuration errors:")
            for error in errors:
                print(f"   • {error}")
            return False

        try:
            # Initialize conversation manager
            save_path = Path.home() / ".voice_chatbot" / "conversation.json"
            self.conversation_manager = conversation.ConversationManager(
                max_entries=self.config.conversation.max_history * 2,  # user + assistant
                save_file=str(save_path)
            )

            # Initialize LLM
            self.ollama_llm = ollama_llm.OllamaLLM(self.config.ollama)
            if not self.ollama_llm.is_available():
                print("❌ Ollama service is not available. Please start Ollama first.")
                return False

            # Initialize TTS
            self.piper_tts = piper_tts.PiperTTS(self.config.piper)
            if not self.piper_tts.is_available():
                print("❌ Piper TTS is not available.")
                return False

            # Initialize audio player
            self.audio_player = audio_utils.AudioPlayer()

            # Initialize LED controller
            if self.config.gpio.enabled:
                try:
                    self.led_controller = gpio_controller.LEDController(
                        red_pin=self.config.gpio.red_pin,
                        green_pin=self.config.gpio.green_pin,
                        blue_pin=self.config.gpio.blue_pin,
                        yellow_pin=self.config.gpio.yellow_pin
                    )
                except Exception as e:
                    print(f"⚠️  Failed to initialize LED controller: {e}")
                    print("   (Continuing without LED feedback)")
                    self.led_controller = None

            # Initialize STT with callbacks
            self.whisper_stt = whisper_stt.WhisperSTT(
                self.config.whisper,
                callback=self._on_transcription_received,
                on_speech_detected=self._on_speech_activity_detected
            )

            # NOTE: SilenceDetector registration removed - whisper_stt.py handles VAD internally
            # self.silence_detector.register_callback(self._on_silence_detected)

            # Register state callbacks
            self.state_manager.register_callback("listening", self._on_listening_state)
            self.state_manager.register_callback("processing", self._on_processing_state)
            self.state_manager.register_callback("speaking", self._on_speaking_state)
            self.state_manager.register_callback("light_sleep", self._on_light_sleep_state)
            self.state_manager.register_callback("deep_sleep", self._on_deep_sleep_state)

            # Register wake word callback
            self.esp32_listener.register_wake_callback(self._on_wake_word_detected)

            # Register timeout callbacks
            self.timeout_manager.register_conversation_callback(self._on_conversation_timeout)
            self.timeout_manager.register_idle_callback(self._on_idle_timeout)

            print("✅ All components initialized successfully")
            return True

        except Exception as e:
            print(f"❌ Error initializing components: {e}")
            return False

    def start(self, start_mode: str = "light_sleep") -> bool:
        """
        Start the voice chatbot system

        Args:
            start_mode: Initial mode - "light_sleep", "listening", or "deep_sleep"
        """
        if not self.initialize():
            return False

        print("🎤 Starting Voice Chatbot System...")
        print("=" * 60)

        self.is_running = True

        # Start processing threads
        self._start_processing_threads()

        # Start ESP32 wake listener
        if not self.esp32_listener.start():
            print("⚠️  Failed to start ESP32 wake listener (continuing anyway)")

        # Set initial state based on start_mode
        if start_mode == "listening":
            # Start in active listening mode (for testing)
            if not self.whisper_stt.start():
                print("❌ Failed to start speech recognition")
                return False
            self.state_manager.set_state("listening")
            print("🎤 Voice chatbot is ready! Start speaking...")
        elif start_mode == "deep_sleep":
            # Start in deep sleep (Ollama OFF)
            self._enter_deep_sleep()
        else:
            # Default: Start in light sleep (waiting for wake word)
            self._enter_light_sleep()

        print("⌨️  Press Ctrl+C to stop")
        print("=" * 60)

        try:
            while self.is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

        return True

    def stop(self):
        """Stop the voice chatbot system"""
        print("\n🛑 Stopping Voice Chatbot...")

        # Play shutdown tone (blocking)
        self._play_feedback_audio("shutdown", blocking=True)

        self.is_running = False

        # Stop all timers
        self.timeout_manager.stop_all_timers()

        # Stop ESP32 listener
        if self.esp32_listener:
            self.esp32_listener.stop()

        # Stop components
        if self.whisper_stt:
            self.whisper_stt.stop()

        if self.audio_player:
            self.audio_player.stop()

        # Cleanup LED controller
        if self.led_controller:
            self.led_controller.cleanup()

        # Wake from deep sleep if needed (so Ollama is available for next run)
        if self.state_manager.is_state("deep_sleep"):
            self.sleep_manager.wake_from_deep_sleep(self.config.ollama.model)

        # NOTE: SilenceDetector.stop_monitoring() removed - no longer using external silence detection
        # if self.silence_detector:
        #     self.silence_detector.stop_monitoring()

        # Cleanup
        if self.piper_tts:
            self.piper_tts.cleanup_temp_files()

        audio_utils.cleanup_temp_files()

        # Save conversation
        if self.conversation_manager:
            self.conversation_manager.save_conversation()

        print("✅ Voice Chatbot stopped")

    def _start_processing_threads(self):
        """Start background processing threads"""
        # Response processor thread
        response_thread = threading.Thread(
            target=self._process_responses,
            daemon=True,
            name="ResponseProcessor"
        )
        response_thread.start()

    def _on_transcription_received(self, text: str):
        """Callback when transcription is received from whisper_stt"""
        if self.state_manager.is_state("listening") and not self.is_processing:
            print(f"🗣️  User: {text}")

            # Play processing beep (non-blocking)
            self._play_feedback_audio("processing", blocking=False)

            # IMPORTANT: Pause recording immediately to prevent queuing
            # This prevents the mic from picking up speech during LLM processing
            if self.whisper_stt:
                self.whisper_stt.pause_recording()

            # Check for dismissal patterns
            if self.dismissal_detector.is_dismissal(text):
                print("👋 Dismissal detected - will enter sleep after response")
                self.is_dismissal_pending = True
                matched = self.dismissal_detector.get_matched_patterns(text)
                if matched:
                    print(f"   (Matched pattern: {matched[0]})")

            # Trigger callback
            if self.on_user_speech:
                self.on_user_speech(text)

            # Process the transcription immediately
            # No need for silence detection - whisper_stt already handled that
            if text.strip():
                # Reset conversation timer since user is talking
                self.timeout_manager.reset_conversation_timer()
                self.response_queue.put(text.strip())

    def _on_speech_activity_detected(self):
        """
        Callback when speech is detected (user started talking)

        This is called as soon as speech is detected, before transcription.
        It resets the conversation timer to prevent timeout while user is actively speaking.
        """
        # Only reset timer if we're in listening state with an active conversation timer
        if self.state_manager.is_state("listening") and self.timeout_manager.is_conversation_timer_active():
            self.timeout_manager.reset_conversation_timer()
            # Restart the timer to give user full 30s from when they started speaking
            self.timeout_manager.start_conversation_timer()

    def _on_silence_detected(self, silence_duration: float):
        """Callback when silence is detected - NO LONGER USED with new whisper_stt"""
        # This method is kept for compatibility with audio_utils.SilenceDetector
        # but is not used since whisper_stt.py now handles silence detection internally
        pass

    def _process_responses(self):
        """Process user inputs and generate responses"""
        while self.is_running:
            try:
                # Wait for user input
                user_input = self.response_queue.get(timeout=1)

                if user_input.strip() and not self.is_processing:
                    self._handle_user_input(user_input.strip())

            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Error in response processor: {e}")

    def _handle_user_input(self, user_input: str):
        """Handle user input - routes to streaming or blocking mode"""
        if self.config.conversation.use_streaming:
            self._handle_user_input_streaming(user_input)
        else:
            self._handle_user_input_blocking(user_input)

    def _handle_user_input_blocking(self, user_input: str):
        """Handle user input with blocking LLM and TTS (original implementation)"""
        try:
            self.is_processing = True
            self.state_manager.set_state("processing")

            # Add to conversation history
            self.conversation_manager.add_user_message(user_input)

            # Generate AI response
            print("🤖 Generating response...")
            ai_response = self.ollama_llm.generate_response(
                user_input,
                self.config.conversation.system_prompt
            )

            if ai_response:
                # Add to conversation history
                self.conversation_manager.add_assistant_message(ai_response)

                # Convert to speech
                audio_file = self.piper_tts.synthesize_to_temp(ai_response)

                if audio_file:
                    # Play response
                    self._play_response(audio_file, ai_response)
                else:
                    print("❌ Failed to generate speech")
                    self.state_manager.set_state("listening")
            else:
                print("❌ No response generated")
                self.state_manager.set_state("listening")

        except Exception as e:
            print(f"❌ Error handling user input: {e}")
            self.state_manager.set_state("listening")
        finally:
            self.is_processing = False

    def _handle_user_input_streaming(self, user_input: str):
        """Handle user input with streaming LLM and incremental TTS"""
        try:
            self.is_processing = True
            self.state_manager.set_state("processing")

            # Add user message to history
            self.conversation_manager.add_user_message(user_input)

            # Initialize streaming components
            tts_processor = StreamingTTSProcessor(
                self.piper_tts,
                self.audio_player,
                min_sentence_length=self.config.conversation.min_sentence_length
            )

            first_audio_played = False
            queue_finished = False  # Flag to track when queue completes

            # Setup audio queue callbacks
            def on_first_chunk_start(metadata):
                nonlocal first_audio_played
                if not first_audio_played:
                    first_audio_played = True
                    self.state_manager.set_state("speaking")
                    if self.whisper_stt:
                        self.whisper_stt.pause_recording()
                    print(f"🔊 Playing response (streaming)...")

            def on_queue_complete():
                # Just set a flag - don't do state transitions in callback thread
                nonlocal queue_finished
                queue_finished = True
                print("✅ Audio queue playback finished")

            # Start audio queue playback (this resets counters)
            self.audio_player.start_queue_playback()

            # Set callbacks AFTER starting queue to ensure clean state
            self.audio_player.on_chunk_start = on_first_chunk_start
            self.audio_player.on_queue_complete = on_queue_complete

            # Stream LLM response
            print("🤖 Generating response (streaming)...")
            chunks_received = 0
            for chunk in self.ollama_llm.generate_streaming_response(
                user_input,
                self.config.conversation.system_prompt
            ):
                tts_processor.process_chunk(chunk)
                chunks_received += 1

            # Finalize any remaining text
            tts_processor.finalize()

            # Get full response for display
            full_response = tts_processor.get_full_response()
            print(f"📊 Streaming stats: {chunks_received} chunks, {len(full_response)} characters")
            print(f"🤖 Assistant: {full_response}")

            # Only signal generation complete if we actually received chunks
            if chunks_received > 0:
                self.audio_player.signal_generation_complete()

                # Wait for queue to finish playing (callback sets queue_finished flag)
                # Timeout after 60 seconds to prevent infinite waiting
                wait_start = time.time()
                while not queue_finished and time.time() - wait_start < 60:
                    time.sleep(0.1)

                if not queue_finished:
                    print("⚠️  Timeout waiting for audio queue to finish")

                # Add complete response to history
                if full_response.strip():
                    self.conversation_manager.add_assistant_message(full_response)

                # Handle interaction mode logic (in main thread context)
                self._handle_streaming_complete(full_response)

            else:
                # No chunks received - likely an error
                print("⚠️  No response chunks received from LLM")
                self.audio_player.stop_queue_playback(clear_queue=True)
                self.state_manager.set_state("listening")
                if self.whisper_stt:
                    self.whisper_stt.resume_recording()
                return

            # Trigger callback
            if self.on_ai_response:
                self.on_ai_response(full_response)

        except Exception as e:
            print(f"❌ Error in streaming handler: {e}")
            self.audio_player.stop_queue_playback()
            self.state_manager.set_state("listening")
        finally:
            self.is_processing = False

    def _handle_streaming_complete(self, response_text: str):
        """Handle post-streaming logic (interaction modes)"""
        # Check if dismissal was detected
        if self.is_dismissal_pending:
            print("💤 Entering light sleep after goodbye")
            self.is_dismissal_pending = False
            self._enter_light_sleep()
            return

        # Handle different interaction modes
        interaction_mode = self.config.conversation.interaction_mode

        if interaction_mode == "single-shot":
            # Always sleep after response (Alexa-style)
            print("💤 Single-shot mode: Entering light sleep")
            self._enter_light_sleep()

        elif interaction_mode == "conversation":
            # Always continue listening (original behavior)
            if self.whisper_stt:
                self.whisper_stt.resume_recording()
            self.state_manager.set_state("listening")
            # Start conversation timeout (30s)
            self.timeout_manager.start_conversation_timer()

        elif interaction_mode == "smart":
            # Continue only if AI asks a question
            if self._response_invites_continuation(response_text):
                print(f"💡 Smart mode: AI asked question, waiting {self.config.conversation.smart_mode_followup_timeout}s for follow-up")
                if self.whisper_stt:
                    self.whisper_stt.resume_recording()
                self.state_manager.set_state("listening")
                # Use shorter timeout for follow-ups
                self.timeout_manager.start_conversation_timer(
                    timeout=self.config.conversation.smart_mode_followup_timeout
                )
            else:
                print("💤 Smart mode: Response complete, entering light sleep")
                self._enter_light_sleep()

        else:
            # Unknown mode, default to conversation mode
            print(f"⚠️  Unknown interaction mode '{interaction_mode}', defaulting to conversation")
            if self.whisper_stt:
                self.whisper_stt.resume_recording()
            self.state_manager.set_state("listening")
            self.timeout_manager.start_conversation_timer()

    def _response_invites_continuation(self, response_text: str) -> bool:
        """
        Check if the AI response invites continuation (asks a question)
        Used for "smart" interaction mode

        Simply checks if the response ends with a question mark
        """
        return response_text.strip().endswith('?')

    def _play_response(self, audio_file: str, response_text: str):
        """Play the AI response"""
        def on_start():
            self.state_manager.set_state("speaking")
            # Note: Recording already paused in _on_transcription_received
            # Double-pause is safe (idempotent)
            if self.whisper_stt:
                self.whisper_stt.pause_recording()

        def on_finish():
            # Cleanup temp file
            Path(audio_file).unlink(missing_ok=True)

            # Check if dismissal was detected
            if self.is_dismissal_pending:
                print("💤 Entering light sleep after goodbye")
                self.is_dismissal_pending = False
                self._enter_light_sleep()
                return

            # Handle different interaction modes
            interaction_mode = self.config.conversation.interaction_mode

            if interaction_mode == "single-shot":
                # Always sleep after response (Alexa-style)
                print("💤 Single-shot mode: Entering light sleep")
                self._enter_light_sleep()

            elif interaction_mode == "conversation":
                # Always continue listening (original behavior)
                if self.whisper_stt:
                    self.whisper_stt.resume_recording()
                self.state_manager.set_state("listening")
                # Start conversation timeout (30s)
                self.timeout_manager.start_conversation_timer()

            elif interaction_mode == "smart":
                # Continue only if AI asks a question
                if self._response_invites_continuation(response_text):
                    print(f"💡 Smart mode: AI asked question, waiting {self.config.conversation.smart_mode_followup_timeout}s for follow-up")
                    if self.whisper_stt:
                        self.whisper_stt.resume_recording()
                    self.state_manager.set_state("listening")
                    # Use shorter timeout for follow-ups
                    self.timeout_manager.start_conversation_timer(
                        timeout=self.config.conversation.smart_mode_followup_timeout
                    )
                else:
                    print("💤 Smart mode: Response complete, entering light sleep")
                    self._enter_light_sleep()

            else:
                # Unknown mode, default to conversation mode
                print(f"⚠️  Unknown interaction mode '{interaction_mode}', defaulting to conversation")
                if self.whisper_stt:
                    self.whisper_stt.resume_recording()
                self.state_manager.set_state("listening")
                self.timeout_manager.start_conversation_timer()

        print(f"🤖 Assistant: {response_text}")

        # Trigger callback
        if self.on_ai_response:
            self.on_ai_response(response_text)

        # Play audio
        self.audio_player.play(
            audio_file,
            blocking=False,
            on_start=on_start,
            on_finish=on_finish
        )

    def _on_listening_state(self, old_state: str, new_state: str, data: dict):
        """Handler for listening state"""
        if self.led_controller:
            self.led_controller.set_state("listening")
        # Note: "Listening for speech..." is printed by whisper_stt, not here

    def _on_processing_state(self, old_state: str, new_state: str, data: dict):
        """Handler for processing state"""
        if self.led_controller:
            self.led_controller.set_state("processing")
        print("💭 Processing your request...")

    def _on_speaking_state(self, old_state: str, new_state: str, data: dict):
        """Handler for speaking state"""
        if self.led_controller:
            self.led_controller.set_state("speaking")
        print("🔊 Playing response...")

    def _on_light_sleep_state(self, old_state: str, new_state: str, data: dict):
        """Handler for light sleep state"""
        if self.led_controller:
            self.led_controller.set_state("light_sleep")
        # Only play ready beep when transitioning from active states
        if old_state in ["listening", "processing", "speaking"]:
            self._play_feedback_audio("ready", blocking=False)
        print("💤 Light sleep - Waiting for wake word...")

    def _on_deep_sleep_state(self, old_state: str, new_state: str, data: dict):
        """Handler for deep sleep state"""
        if self.led_controller:
            self.led_controller.set_state("deep_sleep")
        self._play_feedback_audio("deep_sleep", blocking=False)
        print("😴 Deep sleep - Ollama stopped, minimal power...")

    def _on_wake_word_detected(self):
        """Callback when ESP32 detects wake word"""
        current_state = self.state_manager.get_state()

        # Ignore wake word if already in active conversation
        if current_state in ["listening", "processing", "speaking"]:
            # Silently ignore - no need to wake up, already active
            return

        print("🌅 Wake word detected!")

        # Play wake beep
        self._play_feedback_audio("wake", blocking=False)

        # Stop idle timer (if in light sleep)
        self.timeout_manager.reset_idle_timer()

        # Wake from deep sleep if needed
        if self.state_manager.is_state("deep_sleep"):
            print("🔄 Waking from deep sleep...")
            time.sleep(0.3)  # Brief pause after wake beep
            # Start loading tone loop
            self._start_loading_audio()
            # Wake Ollama
            if not self.sleep_manager.wake_from_deep_sleep(self.config.ollama.model):
                self._stop_loading_audio()
                print("❌ Failed to wake from deep sleep")
                return
            # Stop loading tone and play ready beep
            self._stop_loading_audio()
            self._play_feedback_audio("ready", blocking=False)

        # Start whisper STT only if not already running
        if not self.whisper_stt.is_running:
            if not self.whisper_stt.start():
                print("❌ Failed to start speech recognition")
                return

        # Transition to listening
        self.state_manager.set_state("listening")

    def _on_conversation_timeout(self):
        """Callback when conversation times out (30s silence)"""
        print("⏰ Conversation timeout - Entering light sleep")
        self._enter_light_sleep()

    def _on_idle_timeout(self):
        """Callback when idle times out (5 min in light sleep)"""
        print("⏰ Idle timeout - Entering deep sleep")
        self._enter_deep_sleep()

    def _enter_light_sleep(self):
        """Enter light sleep mode (Ollama loaded, Whisper OFF)"""
        # Stop whisper STT
        if self.whisper_stt:
            self.whisper_stt.stop()

        # Stop conversation timer
        self.timeout_manager.stop_conversation_timer()

        # Start idle timer (5 minutes)
        self.timeout_manager.start_idle_timer()

        # Send sleep signal to ESP32
        if self.esp32_listener:
            self.esp32_listener.send_sleep_signal()

        # Transition to light sleep state
        self.state_manager.set_state("light_sleep")

    def _enter_deep_sleep(self):
        """Enter deep sleep mode (Ollama OFF, minimal power)"""
        # Stop whisper STT (if not already stopped)
        if self.whisper_stt:
            self.whisper_stt.stop()

        # Stop all timers
        self.timeout_manager.stop_all_timers()

        # Stop Ollama service
        if not self.sleep_manager.enter_deep_sleep():
            print("⚠️  Failed to stop Ollama, staying in light sleep")
            self.timeout_manager.start_idle_timer()  # Restart idle timer
            return

        # Transition to deep sleep state
        self.state_manager.set_state("deep_sleep")

    def get_conversation_stats(self) -> dict:
        """Get conversation statistics"""
        if self.conversation_manager:
            return self.conversation_manager.get_stats()
        return {}

    def clear_conversation(self):
        """Clear conversation history"""
        if self.conversation_manager:
            self.conversation_manager.clear_history()
        if self.ollama_llm:
            self.ollama_llm.clear_history()

    def export_conversation(self, format: str = "markdown", output_file: Optional[str] = None) -> str:
        """Export conversation history"""
        if not self.conversation_manager:
            return ""

        conversation_data = self.conversation_manager.export_conversation(format)

        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(conversation_data)
            print(f"📄 Conversation exported to {output_file}")

        return conversation_data

    def say(self, text: str):
        """Make the assistant say something (for testing)"""
        if self.piper_tts and self.audio_player:
            audio_file = self.piper_tts.synthesize_to_temp(text)
            if audio_file:
                self.audio_player.play(audio_file, blocking=True)
                Path(audio_file).unlink(missing_ok=True)

    def _play_feedback_audio(self, audio_type: str, blocking: bool = False):
        """
        Play audio feedback for state transitions

        Args:
            audio_type: 'wake', 'processing', 'ready', 'deep_sleep', 'shutdown'
            blocking: If True, wait for audio to finish playing
        """
        if not self.audio_player:
            return

        sounds_dir = Path(__file__).parent.parent / "sounds"

        audio_map = {
            "wake": "wake_beep.wav",
            "processing": "processing_beep.wav",
            "ready": "ready_beep.wav",
            "deep_sleep": "deep_sleep_tone.wav",
            "shutdown": "shutdown_tone.wav"
        }

        if audio_type in audio_map:
            audio_file = sounds_dir / audio_map[audio_type]
            if audio_file.exists():
                # Shutdown always blocks
                is_blocking = blocking or (audio_type == "shutdown")
                self.audio_player.play(str(audio_file), blocking=is_blocking)

    def _start_loading_audio(self):
        """Start playing loading tone in a loop"""
        if not self.audio_player:
            return
        sounds_dir = Path(__file__).parent.parent / "sounds"
        loading_file = sounds_dir / "loading_tone.wav"
        if loading_file.exists():
            self.audio_player.play_loop(str(loading_file))

    def _stop_loading_audio(self):
        """Stop playing loading tone"""
        if self.audio_player:
            self.audio_player.stop_loop()

def main():
    """Main entry point"""
    # Create and configure chatbot
    chatbot_config = config.ChatbotConfig.from_env()
    chatbot = VoiceChatbot(chatbot_config)

    # Optional: Add custom callbacks
    def on_user_speech(text):
        """Custom callback for user speech"""
        pass

    def on_ai_response(text):
        """Custom callback for AI responses"""
        pass

    chatbot.on_user_speech = on_user_speech
    chatbot.on_ai_response = on_ai_response

    # Start the chatbot
    try:
        chatbot.start()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        chatbot.stop()

if __name__ == "__main__":
    main()