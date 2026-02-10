"""
Personality Manager for TalkingBuddy.

Handles loading personality definitions and resolving model names
based on personality + base model combinations.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional


class PersonalityManager:
    """Manages personality definitions and model name resolution."""

    def __init__(self, yaml_path: Optional[Path] = None):
        """
        Initialize personality manager.

        Args:
            yaml_path: Path to personalities.yaml (defaults to models/personalities.yaml)
        """
        if yaml_path is None:
            # Default to models/personalities.yaml relative to this script
            script_dir = Path(__file__).parent
            yaml_path = script_dir.parent / "models" / "personalities.yaml"

        self.yaml_path = yaml_path
        self.personalities = self._load_personalities()

    def _load_personalities(self) -> Dict[str, Any]:
        """Load personality definitions from YAML."""
        if not self.yaml_path.exists():
            print(f"⚠️  Warning: {self.yaml_path} not found. Using neutral personality only.")
            return {
                "neutral": {
                    "name": "Neutro",
                    "description": "Abordagem equilibrada. Comportamento padrão.",
                    "system_prompt": "Você é um assistente útil."
                }
            }

        try:
            with open(self.yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            return data.get('personalities', {})
        except Exception as e:
            print(f"❌ Error loading personalities.yaml: {e}")
            return {}

    def list_personalities(self) -> List[Tuple[str, str, str]]:
        """
        Get list of available personalities.

        Returns:
            List of (id, name, description) tuples
        """
        result = []
        for personality_id, data in self.personalities.items():
            name = data.get('name', personality_id)
            description = data.get('description', '')
            result.append((personality_id, name, description))
        return sorted(result)

    def get_personality(self, personality_id: str) -> Optional[Dict[str, Any]]:
        """
        Get personality definition by ID.

        Args:
            personality_id: Personality ID (e.g., "casual", "formal")

        Returns:
            Personality dict or None if not found
        """
        return self.personalities.get(personality_id)

    def personality_exists(self, personality_id: str) -> bool:
        """Check if a personality exists."""
        return personality_id in self.personalities

    def resolve_model_name(
        self,
        base_model: str,
        personality: str,
        explicit_model: Optional[str] = None
    ) -> str:
        """
        Resolve the full Ollama model name.

        Priority:
        1. If explicit_model is provided, use it as-is
        2. Otherwise, construct: {base_model}-ptbr-{personality}

        Args:
            base_model: Base model name (e.g., "gemma3", "qwen2.5")
            personality: Personality ID (e.g., "casual", "formal")
            explicit_model: Optional explicit model name override

        Returns:
            Full model name for Ollama (e.g., "gemma3-ptbr-casual")
        """
        # If explicit model provided, use it
        if explicit_model:
            return explicit_model

        # Construct personality model name
        # Format: {base}-ptbr-{personality}
        # Remove any :version suffix from base model
        base_clean = base_model.split(':')[0]

        return f"{base_clean}-ptbr-{personality}"

    def print_personalities(self):
        """Print formatted list of available personalities."""
        print("🎭 Available Personalities:")
        print()

        if not self.personalities:
            print("   (none - check models/personalities.yaml)")
            return

        for personality_id, name, description in self.list_personalities():
            print(f"   {personality_id:15s} - {name:20s} | {description}")

        print()
        print("💡 Usage:")
        print("   python src/run_chatbot.py --personality casual")
        print("   python src/run_chatbot.py --personality humorous --base-model qwen2.5")


# Singleton instance for easy access
_manager_instance = None


def get_personality_manager() -> PersonalityManager:
    """Get singleton personality manager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PersonalityManager()
    return _manager_instance


def main():
    """Test personality manager."""
    manager = PersonalityManager()
    manager.print_personalities()

    print("\nTest model name resolution:")
    print(f"   gemma3 + casual = {manager.resolve_model_name('gemma3', 'casual')}")
    print(f"   qwen2.5:1.5b + formal = {manager.resolve_model_name('qwen2.5:1.5b', 'formal')}")
    print(f"   explicit override = {manager.resolve_model_name('gemma3', 'casual', 'custom-model')}")


if __name__ == "__main__":
    main()
