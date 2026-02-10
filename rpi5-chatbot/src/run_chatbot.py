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

def create_custom_config(model_name=None, language_mode="native", interaction_mode="smart",
                        input_device=None, output_device=None, personality=None, base_model=None):
    """Create a custom configuration if needed

    Args:
        model_name: Model name (e.g., "qwen2.5:1.5b", "gemma3:1b", "llama3.2:1b")
        language_mode: "native" for native Portuguese support, "pt-br" for forced Portuguese via Modelfile
        interaction_mode: "single-shot", "conversation", or "smart" (default)
        input_device: Override input device (name pattern or index)
        output_device: Override output device (name pattern or index)
        personality: Personality ID (e.g., "casual", "formal", "humorous")
        base_model: Base model for personality (e.g., "gemma3", "qwen2.5", "llama3.2")
    """
    chatbot_config = config.ChatbotConfig.from_env()

    # Initialize personality manager
    pm = personality_manager.get_personality_manager()

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

        personality_info = pm.get_personality(personality)
        print(f"🎭 Personality: {personality_info['name']} - {personality_info['description']}")
        print(f"📦 Model: {final_model}")

    elif model_name:
        # Legacy mode: explicit model name without personality
        if language_mode == "pt-br":
            # Use the -ptbr variant (created from Modelfile)
            # Convert model names to their pt-br equivalents
            # Pattern: extract base name, keep any suffixes after version, append -ptbr
            # e.g., "qwen2.5:1.5b" -> "qwen2.5-ptbr"
            # e.g., "gemma3:1b-it-qat" -> "gemma3-it-qat-ptbr"
            # e.g., "gemma3:1b" -> "gemma3-ptbr"
            # e.g., "mistral" -> "mistral-ptbr"

            if ':' in model_name:
                # Has version info: "gemma3:1b-it-qat" or "qwen2.5:1.5b"
                base, version_part = model_name.split(':', 1)

                # Extract version number (e.g., "1.5b", "1b") and any suffixes
                # Version ends with 'b' or 'b-' followed by suffix
                match = re.match(r'(\d+(?:\.\d+)?b)(.*)', version_part)
                if match:
                    # Has suffixes like "-it-qat"
                    suffixes = match.group(2)
                    final_model = f"{base}{suffixes}-ptbr"
                else:
                    # Just the version, no suffixes
                    final_model = f"{base}-ptbr"
            else:
                # No version info: "mistral"
                final_model = f"{model_name}-ptbr"
        else:
            # Use native model (relies on native Portuguese support)
            final_model = model_name

        chatbot_config.ollama.model = final_model
        print(f"📦 Model: {final_model}")
        print(f"🌐 Language Mode: {'Forced Portuguese (via Modelfile)' if language_mode == 'pt-br' else 'Native Portuguese'}")

    # Apply interaction mode
    chatbot_config.conversation.interaction_mode = interaction_mode
    mode_descriptions = {
        "single-shot": "Single-shot (Alexa-style, best battery)",
        "conversation": "Continuous conversation (original behavior)",
        "smart": "Smart hybrid (continues on questions)"
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
        choices=["native", "pt-br"],
        default="native",
        help="Language mode (default: native). 'native' uses model's native Portuguese support, 'pt-br' forces Portuguese via Modelfile"
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
        choices=["single-shot", "conversation", "smart"],
        default="smart",
        help="Interaction mode (default: smart). 'single-shot' for Alexa-style (best battery), 'conversation' for continuous chat, 'smart' for hybrid (continues if AI asks question)"
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
        args.model, args.language, args.interaction_mode,
        args.input_device, args.output_device,
        args.personality, args.base_model
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
