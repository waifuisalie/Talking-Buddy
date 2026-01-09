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

def create_custom_config(model_name=None, language_mode="native"):
    """Create a custom configuration if needed

    Args:
        model_name: Model name (e.g., "qwen2.5:1.5b", "gemma3:1b", "llama3.2:1b")
        language_mode: "native" for native Portuguese support, "pt-br" for forced Portuguese via Modelfile
    """
    chatbot_config = config.ChatbotConfig.from_env()

    # Apply model selection if provided
    if model_name:
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

    # You can customize the configuration here
    # For example:
    # config.ollama.model = "llama2"
    # config.audio.silence_threshold = 3.0
    # config.conversation.system_prompt = "Your custom system prompt"

    return chatbot_config

def main():
    parser = argparse.ArgumentParser(description="Voice Chatbot System")

    # Model selection arguments
    parser.add_argument(
        "--model",
        type=str,
        default="gemma3-ptbr",
        help="Model to use (default: qwen2.5:1.5b). Options: qwen2.5:1.5b, gemma3:1b, gemma3:1b-it-qat, llama3.2:1b, mistral"
    )
    parser.add_argument(
        "--language",
        type=str,
        choices=["native", "pt-br"],
        default="native",
        help="Language mode (default: native). 'native' uses model's native Portuguese support, 'pt-br' forces Portuguese via Modelfile"
    )

    # Wake word integration arguments
    parser.add_argument(
        "--wake-mode",
        type=str,
        choices=["serial", "keyboard", "disabled"],
        default="keyboard",
        help="Wake word mode (default: keyboard). 'serial' for ESP32, 'keyboard' for testing with 'w' key, 'disabled' for always-on"
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

    # Operation arguments
    parser.add_argument("--test", action="store_true", help="Run system tests")
    parser.add_argument("--clear-history", action="store_true", help="Clear conversation history")
    parser.add_argument("--export", type=str, help="Export conversation to file")
    parser.add_argument("--say", type=str, help="Make the assistant say something (test TTS)")

    args = parser.parse_args()

    # Create configuration with model selection
    chatbot_config = create_custom_config(args.model, args.language)

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
