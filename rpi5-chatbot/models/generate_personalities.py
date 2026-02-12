#!/usr/bin/env python3
"""
Generate personality-variant Modelfiles for TalkingBuddy.

This script reads personalities.yaml and generates Modelfile variants
for each base model × personality combination.
"""

import yaml
import subprocess
from pathlib import Path
from typing import Dict, Any


# Known base models (for reference and fallback)
KNOWN_BASE_MODELS = {
    "gemma3:1b": "gemma3",
    "qwen2.5:1.5b": "qwen2.5",
    "llama3.2:1b": "llama3.2",
}


def get_installed_base_models() -> Dict[str, str]:
    """Query Ollama for installed base models and return name -> short_name mapping."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True
        )

        # Parse ollama list output
        installed = {}
        for line in result.stdout.split('\n'):
            for model_name, short_name in KNOWN_BASE_MODELS.items():
                if model_name in line:
                    installed[model_name] = short_name
                    break

        return installed
    except Exception as e:
        print(f"⚠️  Warning: Could not query Ollama: {e}")
        print(f"   Falling back to gemma3:1b only")
        return {"gemma3:1b": "gemma3"}


def load_personalities(yaml_path: Path) -> Dict[str, Any]:
    """Load personality definitions from YAML file."""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data['personalities']


def generate_modelfile(
    base_model: str,
    personality_id: str,
    personality: Dict[str, Any],
    output_path: Path
) -> None:
    """Generate a Modelfile for a specific base model + personality."""

    # Format system prompt for Ollama (single line)
    system_prompt = personality['system_prompt'].strip().replace('\n', ' ')

    content = f"""# TalkingBuddy Personality: {personality['name']}
# Base model: {base_model}
# {personality['description']}
#
# To build this model, run:
#   ollama create {output_path.stem.replace('Modelfile.', '')} -f {output_path.name}

FROM {base_model}

# System instruction with personality
SYSTEM {system_prompt}

# Optimal parameters
PARAMETER temperature 0.7
PARAMETER top_p 0.9
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ Generated: {output_path.name}")


def main():
    """Generate all personality Modelfiles."""
    script_dir = Path(__file__).parent
    yaml_path = script_dir / "personalities.yaml"

    if not yaml_path.exists():
        print(f"❌ Error: {yaml_path} not found")
        return 1

    print("🎭 Generating personality Modelfiles...\n")

    # Dynamically detect installed base models
    print("🔍 Detecting installed base models...")
    base_models = get_installed_base_models()

    if not base_models:
        print("❌ No base models found in Ollama!")
        print("   Install at least one:")
        print("   - ollama pull gemma3:1b")
        print("   - ollama pull qwen2.5:1.5b")
        print("   - ollama pull llama3.2:1b")
        return 1

    print(f"✅ Found {len(base_models)} base model(s):")
    for model_name in base_models.keys():
        print(f"   - {model_name}")
    print()

    personalities = load_personalities(yaml_path)

    # Generate for each installed base model × personality combination
    total = 0
    for base_model, model_short in base_models.items():
        print(f"\n📦 Base model: {base_model}")

        # Create subdirectory if it doesn't exist
        model_dir = script_dir / model_short
        model_dir.mkdir(exist_ok=True)

        for personality_id, personality in personalities.items():
            # Output filename: gemma3/Modelfile.casual
            output_name = f"Modelfile.{personality_id}"
            output_path = model_dir / output_name

            generate_modelfile(base_model, personality_id, personality, output_path)
            total += 1

    print(f"\n✨ Generated {total} Modelfiles successfully!")
    print(f"\n💡 Next steps:")
    print(f"   1. Run: ./create_all_personalities.sh")
    print(f"   2. Or create individual models:")
    print(f"      ollama create gemma3-ptbr-casual -f gemma3/Modelfile.casual")
    print(f"   3. Test with: python src/run_chatbot.py --personality casual")

    return 0


if __name__ == "__main__":
    exit(main())
