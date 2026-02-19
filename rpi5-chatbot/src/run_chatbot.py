#!/usr/bin/env python3
"""
Voice Chatbot Runner

Simple script to run the voice chatbot with optional customizations
"""

import sys
import argparse
import re
from pathlib import Path

# Add the chatbot module to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Import with absolute imports
import config
import voice_chatbot
import audio_utils
import ollama_llm
import piper_tts
import esp32_wake_listener
import audio_device_detector
import personality_manager

def create_custom_config(model_name=None, language="pt", interaction_mode="conversation",
                        input_device=None, output_device=None, personality=None, base_model=None,
                        tts_engine="piper"):
    """Create a custom configuration if needed

    Args:
        model_name: Model name (e.g., "qwen2.5:1.5b", "gemma3:1b", "llama3.2:1b")
        language: Response language: "pt", "en", or "es" (default: "pt")
        interaction_mode: "single-shot" or "conversation" (default)
        input_device: Override input device (name pattern or index)
        output_device: Override output device (name pattern or index)
        personality: Personality ID (e.g., "casual", "formal", "humorous")
        base_model: Base model for personality (e.g., "gemma3", "qwen2.5", "llama3.2")
        tts_engine: TTS engine to use: "piper" or "supertonic" (default: "piper")
    """
    chatbot_config = config.ChatbotConfig.from_env()

    # Initialize personality manager
    pm = personality_manager.get_personality_manager()

    # Configure language and TTS engine
    chatbot_config.supertonic.language = language
    chatbot_config.whisper.language = language  # Sync STT with TTS language
    chatbot_config.tts_engine = tts_engine
    print(f"🌐 Language: {language.upper()}")
    print(f"🔊 TTS Engine: {tts_engine.title()}")

    # Apply device overrides
    if input_device:
        chatbot_config.whisper.input_device_preference = input_device
    if output_device:
        chatbot_config.audio.output_device_preference = output_device

    # Apply personality + model selection
    if personality:
        # Personality mode: use personality manager to resolve model name
        if not pm.personality_exists(personality):
            print(f"❌ Error: Unknown personality '{personality}'")
            print("\n🎭 Available personalities:")
            pm.print_personalities()
            sys.exit(1)

        # Determine base model (CLI > config > default)
        base = base_model or chatbot_config.ollama.base_model_preference

        # Resolve full model name: {base}-ptbr-{personality}
        final_model = pm.resolve_model_name(base, personality, explicit_model=model_name)

        chatbot_config.ollama.model = final_model
        chatbot_config.ollama.personality = personality
        chatbot_config.ollama.base_model_preference = base
        chatbot_config.supertonic.personality = personality  # Sync personality to TTS

        personality_info = pm.get_personality(personality)
        print(f"🎭 Personality: {personality_info['name']} - {personality_info['description']}")
        print(f"📦 Model: {final_model}")

    elif model_name:
        # Explicit model name without personality
        chatbot_config.ollama.model = model_name
        print(f"📦 Model: {model_name}")

    # Apply interaction mode
    chatbot_config.conversation.interaction_mode = interaction_mode
    mode_descriptions = {
        "single-shot": "Single-shot (Alexa-style, best battery)",
        "conversation": "Continuous conversation (wake word → chat until timeout/goodbye)"
    }
    print(f"💬 Interaction Mode: {mode_descriptions.get(interaction_mode, interaction_mode)}")

    # You can customize the configuration here
    # For example:
    # config.ollama.model = "llama2"
    # config.audio.silence_threshold = 3.0
    # config.conversation.system_prompt = "Your custom system prompt"

    return chatbot_config

def list_personalities():
    """List all available personality profiles"""
    pm = personality_manager.get_personality_manager()
    pm.print_personalities()

def list_audio_devices():
    """List all available audio devices"""
    detector = audio_device_detector.AudioDeviceDetector(debug_mode=True)
    if not detector.initialize():
        print("❌ Failed to initialize audio system")
        return

    devices = detector.list_all_devices()

    print("\n🎤 Available Audio Devices")
    print("=" * 80)

    # Print input devices
    print("\nINPUT DEVICES (Microphones):")
    input_devices = [d for d in devices if d.max_input_channels > 0]
    if not input_devices:
        print("  ❌ No input devices found")
    else:
        for device in input_devices:
            print(f"\n  [{device.index}] {device.name}")
            print(f"      Channels: {device.max_input_channels} input")
            print(f"      Sample Rate: {device.default_sample_rate} Hz")
            alsa_name = detector._extract_alsa_name(device, is_input=True)
            if alsa_name:
                print(f"      ALSA: {alsa_name}")

    # Print output devices
    print("\nOUTPUT DEVICES (Speakers):")
    output_devices = [d for d in devices if d.max_output_channels > 0]
    if not output_devices:
        print("  ❌ No output devices found")
    else:
        for device in output_devices:
            print(f"\n  [{device.index}] {device.name}")
            print(f"      Channels: {device.max_output_channels} output")
            print(f"      Sample Rate: {device.default_sample_rate} Hz")
            alsa_name = detector._extract_alsa_name(device, is_input=False)
            if alsa_name:
                print(f"      ALSA: {alsa_name}")

    detector.cleanup()
    print("\n💡 Usage Examples:")
    print("  python src/run_chatbot.py --input-device 'USB' --output-device 'Headphones'")
    print("  python src/run_chatbot.py --input-device 2 --output-device 5")

def main():
    parser = argparse.ArgumentParser(description="Voice Chatbot System")

    # Model selection arguments
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model to use (default: gemma3-ptbr). Options: qwen2.5:1.5b, gemma3:1b, gemma3:1b-it-qat, llama3.2:1b, mistral. If --personality is used, this overrides auto-generated model name."
    )
    parser.add_argument(
        "--language",
        type=str,
        choices=["pt", "en", "es"],
        default="pt",
        help="Response language (default: pt). 'pt'=Portuguese, 'en'=English, 'es'=Spanish. Works with both TTS and LLM."
    )
    parser.add_argument(
        "--tts-engine",
        type=str,
        choices=["piper", "supertonic"],
        default="piper",
        help="TTS engine (default: piper during migration). 'supertonic' provides 9x faster synthesis and multilingual support."
    )

    # Personality arguments (NEW)
    parser.add_argument(
        "--personality",
        type=str,
        help="Personality profile (e.g., casual, formal, humorous). Use --list-personalities to see all options."
    )
    parser.add_argument(
        "--base-model",
        type=str,
        choices=["gemma3", "qwen2.5", "llama3.2"],
        default="gemma3",
        help="Base model for personality (default: gemma3). Only used with --personality."
    )
    parser.add_argument(
        "--list-personalities",
        action="store_true",
        help="List all available personality profiles and exit"
    )

    # Wake word integration arguments
    parser.add_argument(
        "--wake-mode",
        type=str,
        choices=["serial", "keyboard", "disabled"],
        default="serial",
        help="Wake word mode (default: serial). 'serial' for ESP32, 'keyboard' for testing with 'w' key, 'disabled' for always-on"
    )
    parser.add_argument(
        "--serial-port",
        type=str,
        default="/dev/ttyACM0",
        help="Serial port for ESP32 wake word (default: /dev/ttyACM0)"
    )
    parser.add_argument(
        "--start-mode",
        type=str,
        choices=["light_sleep", "listening", "deep_sleep"],
        default="light_sleep",
        help="Initial chatbot state (default: light_sleep). Use 'listening' for always-on, 'deep_sleep' for minimal power"
    )

    # Interaction mode arguments
    parser.add_argument(
        "--interaction-mode",
        type=str,
        choices=["single-shot", "conversation"],
        default="conversation",
        help="Interaction mode (default: conversation). 'single-shot' for Alexa-style (best battery), 'conversation' for continuous chat until timeout/goodbye"
    )

    # Audio device arguments
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List all available audio devices and exit"
    )
    parser.add_argument(
        "--input-device",
        type=str,
        help="Override input device (name pattern or index)"
    )
    parser.add_argument(
        "--output-device",
        type=str,
        help="Override output device (name pattern or index)"
    )

    # Operation arguments
    parser.add_argument("--test", action="store_true", help="Run system tests")
    parser.add_argument("--clear-history", action="store_true", help="Clear conversation history")
    parser.add_argument("--export", type=str, help="Export conversation to file")
    parser.add_argument("--say", type=str, help="Make the assistant say something (test TTS)")

    args = parser.parse_args()

    # Handle special listing commands first
    if args.list_devices:
        list_audio_devices()
        return

    if args.list_personalities:
        list_personalities()
        return

    # Create configuration with model selection, personality, and interaction mode
    chatbot_config = create_custom_config(
        model_name=args.model,
        language=args.language,
        interaction_mode=args.interaction_mode,
        input_device=args.input_device,
        output_device=args.output_device,
        personality=args.personality,
        base_model=args.base_model,
        tts_engine=args.tts_engine
    )

    if args.test:
        print("🧪 Running system tests...")
        run_tests(chatbot_config)
        return

    # Map wake mode string to enum
    mode_map = {
        "serial": esp32_wake_listener.WakeListenerMode.SERIAL,
        "keyboard": esp32_wake_listener.WakeListenerMode.KEYBOARD,
        "disabled": esp32_wake_listener.WakeListenerMode.DISABLED
    }
    wake_listener_mode = mode_map[args.wake_mode]

    # Print wake mode configuration
    if args.wake_mode == "serial":
        print(f"📡 Wake mode: ESP32 Serial ({args.serial_port})")
    elif args.wake_mode == "keyboard":
        print("⌨️  Wake mode: Keyboard (press 'w' to wake)")
    else:
        print("🔓 Wake mode: Disabled (always listening)")

    # Create chatbot with wake mode
    chatbot = voice_chatbot.VoiceChatbot(
        chatbot_config,
        wake_listener_mode,
        serial_port=args.serial_port
    )

    if args.clear_history:
        print("🧹 Clearing conversation history...")
        chatbot.clear_conversation()
        return

    if args.say:
        print(f"🔊 Testing TTS: '{args.say}'")
        if chatbot.initialize():
            chatbot.say(args.say)
        return

    if args.export:
        print(f"📄 Exporting conversation to {args.export}...")
        if chatbot.initialize():
            chatbot.export_conversation("markdown", args.export)
        return

    # Normal operation - start the voice chatbot
    print("🚀 Starting Voice Chatbot System...")
    print("💡 Make sure Ollama is running!")
    print(f"🌙 Starting in {args.start_mode} mode")
    print()

    chatbot.start(start_mode=args.start_mode)

def run_tests(chatbot_config):
    """Run system tests"""
    from audio_utils import test_audio_system

    print("Testing configuration...")
    errors = chatbot_config.validate()
    if errors:
        print("❌ Configuration errors found:")
        for error in errors:
            print(f"   • {error}")
        return False

    print("✅ Configuration valid")

    print("Testing audio system...")
    if test_audio_system():
        print("✅ Audio system working")
    else:
        print("❌ Audio system issues")

    print("Testing Ollama connection...")
    llm = ollama_llm.OllamaLLM(chatbot_config.ollama)
    if llm.is_available():
        print("✅ Ollama available")
        print(f"   Model: {chatbot_config.ollama.model}")
    else:
        print("❌ Ollama not available")
        print("   Make sure Ollama is running and the model is available")

    print("Testing Piper TTS...")
    tts = piper_tts.PiperTTS(chatbot_config.piper)
    if tts.is_available():
        print("✅ Piper TTS available")
        voice_info = tts.get_voice_info()
        print(f"   Model: {voice_info['model']}")
        print(f"   Language: {voice_info.get('language', 'unknown')}")
    else:
        print("❌ Piper TTS not available")

    print("\n🎉 System test complete!")
    return True

if __name__ == "__main__":
    main()
