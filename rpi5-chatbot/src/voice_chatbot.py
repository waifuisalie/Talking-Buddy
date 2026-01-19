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

            # Initialize STT with callback
            self.whisper_stt = whisper_stt.WhisperSTT(
                self.config.whisper,
                callback=self._on_transcription_received
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
        """Handle a complete user input"""
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

    def _play_response(self, audio_file: str, response_text: str):
        """Play the AI response"""
        def on_start():
            self.state_manager.set_state("speaking")
            # Pause recording to prevent acoustic feedback
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
            else:
                # Resume recording after speaking
                if self.whisper_stt:
                    self.whisper_stt.resume_recording()
                self.state_manager.set_state("listening")

                # Start conversation timeout (30s)
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
        # Note: "Listening for speech..." is printed by whisper_stt, not here
        pass

    def _on_processing_state(self, old_state: str, new_state: str, data: dict):
        """Handler for processing state"""
        print("💭 Processing your request...")

    def _on_speaking_state(self, old_state: str, new_state: str, data: dict):
        """Handler for speaking state"""
        print("🔊 Playing response...")

    def _on_light_sleep_state(self, old_state: str, new_state: str, data: dict):
        """Handler for light sleep state"""
        print("💤 Light sleep - Waiting for wake word...")

    def _on_deep_sleep_state(self, old_state: str, new_state: str, data: dict):
        """Handler for deep sleep state"""
        print("😴 Deep sleep - Ollama stopped, minimal power...")

    def _on_wake_word_detected(self):
        """Callback when ESP32 detects wake word"""
        current_state = self.state_manager.get_state()

        # Ignore wake word if already in active conversation
        if current_state in ["listening", "processing", "speaking"]:
            # Silently ignore - no need to wake up, already active
            return

        print("🌅 Wake word detected!")

        # Stop idle timer (if in light sleep)
        self.timeout_manager.reset_idle_timer()

        # Wake from deep sleep if needed
        if self.state_manager.is_state("deep_sleep"):
            print("🔄 Waking from deep sleep...")
            if not self.sleep_manager.wake_from_deep_sleep(self.config.ollama.model):
                print("❌ Failed to wake from deep sleep")
                return

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