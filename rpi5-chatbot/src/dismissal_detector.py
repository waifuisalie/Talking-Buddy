"""
Dismissal Detector - Detects when user wants to end conversation

Recognizes goodbye phrases in Portuguese and English without modifying LLM prompts.
The LLM responds naturally to goodbyes, and this detector just flags the transition
to sleep mode after the response is complete.
"""

import re
from typing import List, Tuple

class DismissalDetector:
    """Detects dismissal phrases that indicate end of conversation"""

    def __init__(self):
        # Brazilian Portuguese dismissal patterns
        self.portuguese_patterns = [
            r'\btchau\b',
            r'\bat[eé]\s+logo\b',
            r'\bat[eé]\s+mais\b',
            r'\badeus\b',
            r'\bpode\s+ir\b',
            r'\bpode\s+desligar\b',
            r'\bvaleu\b',
            r'\bfalou\b',
            r'\bat[eé]\s+depois\b',
            r'\bat[eé]\s+breve\b',
            r'\bat[eé]\s+(a\s+)?pr[oó]xima\b',
            r'\bvai\s+embora\b',
            r'\bpode\s+parar\b',
            r'\bpode\s+dormir\b',
            r'\bvai\s+dormir\b',
            r'\bvou\s+desligar\b',
            r'\best[aá]\s+bom\b',  # "está bom" (that's enough)
            r'\b[eé]\s+isso\s+(a[ií])?$',  # "é isso" or "é isso aí" (that's it)
        ]

        # English dismissal patterns
        self.english_patterns = [
            r'\bgoodbye\b',
            r'\bbye\b',
            r'\bsee\s+you\b',
            r'\bthat\'?s\s+all\b',
            r'\bthanks?\s+bye\b',
            r'\bfarewell\b',
            r'\blater\b',
            r'\bcatch\s+you\s+later\b',
            r'\bgotta\s+go\b',
            r'\bhave\s+to\s+go\b',
            r'\btake\s+care\b',
            r'\bgood\s+night\b',
            r'\bsleep\s+now\b',
            r'\bshut\s+down\b',
            r'\bturn\s+off\b',
            r'\bstop\s+listening\b',
        ]

        # Compile all patterns (case-insensitive)
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in (self.portuguese_patterns + self.english_patterns)
        ]

    def is_dismissal(self, text: str) -> bool:
        """
        Check if text contains dismissal phrase

        Args:
            text: User's transcribed speech

        Returns:
            True if dismissal detected, False otherwise
        """
        if not text:
            return False

        text = text.strip().lower()

        # Check against all patterns
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True

        return False

    def get_matched_patterns(self, text: str) -> List[str]:
        """
        Get all dismissal patterns that matched the text (for debugging)

        Args:
            text: User's transcribed speech

        Returns:
            List of matched pattern strings
        """
        if not text:
            return []

        text = text.strip().lower()
        matched = []

        all_patterns = self.portuguese_patterns + self.english_patterns

        for i, pattern in enumerate(self.compiled_patterns):
            if pattern.search(text):
                matched.append(all_patterns[i])

        return matched

    def add_custom_pattern(self, pattern: str, language: str = "pt"):
        """
        Add a custom dismissal pattern

        Args:
            pattern: Regular expression pattern to add
            language: "pt" for Portuguese or "en" for English
        """
        if language == "pt":
            self.portuguese_patterns.append(pattern)
        else:
            self.english_patterns.append(pattern)

        # Recompile all patterns
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in (self.portuguese_patterns + self.english_patterns)
        ]

def test_dismissal_detector():
    """Test the dismissal detector with various inputs"""
    detector = DismissalDetector()

    test_cases = [
        # Portuguese - should match
        ("tchau", True),
        ("Tchau, obrigado!", True),
        ("até logo", True),
        ("valeu, falou", True),
        ("pode ir", True),
        ("pode desligar agora", True),
        ("está bom, tchau", True),
        ("é isso", True),
        ("é isso aí", True),

        # English - should match
        ("goodbye", True),
        ("bye bye", True),
        ("see you later", True),
        ("that's all, thanks", True),
        ("gotta go", True),
        ("good night", True),
        ("turn off", True),

        # Should NOT match
        ("olá, como vai?", False),
        ("tchau ou não?", True),  # Still contains "tchau"
        ("o que é isso?", False),  # "é isso" needs end anchor or isolation
        ("obrigado pela ajuda", False),
        ("hello there", False),
        ("tell me more", False),
    ]

    print("Testing Dismissal Detector:")
    print("=" * 60)

    passed = 0
    failed = 0

    for text, expected in test_cases:
        result = detector.is_dismissal(text)
        status = "✅" if result == expected else "❌"

        if result == expected:
            passed += 1
        else:
            failed += 1

        matched = detector.get_matched_patterns(text) if result else []
        matched_str = f" (matched: {matched[0]})" if matched else ""

        print(f"{status} '{text}' -> {result}{matched_str}")

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")

    return failed == 0

if __name__ == "__main__":
    test_dismissal_detector()
