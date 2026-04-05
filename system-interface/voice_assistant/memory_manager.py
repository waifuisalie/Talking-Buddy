"""
Personal fact memory manager.

Extracts personal facts from user messages via regex and stores them asynchronously
in user_data (key='fato'). Retrieves relevant facts via SQLite FTS5 before LLM calls.
"""

import re
import threading
from typing import List

# Patterns covering pt-BR, en-US, es-ES personal fact statements
FACT_PATTERNS = [
    # Portuguese (pt-BR)
    re.compile(r'\b(eu\s+)(tomei|comi|bebi|fiz|fui|vi|ouvi|li|comprei|recebi|terminei|comecei)\b', re.IGNORECASE),
    re.compile(r'\b(estou\s+com|tenho\s+dor|meu\s+médico|minha\s+médica|meu\s+nome\s+é|me\s+chamo)\b', re.IGNORECASE),
    re.compile(r'\b(moro\s+em|trabalho\s+(em|no|na)|nasci\s+em|tenho\s+\d+\s+anos)\b', re.IGNORECASE),
    re.compile(r'\b(sou\s+alérgico|sou\s+diabético|sou\s+hipertenso|tenho\s+diabetes)\b', re.IGNORECASE),
    re.compile(r'\b(hoje\s+eu|ontem\s+eu|essa\s+semana\s+eu)\b', re.IGNORECASE),
    # English (en-US)
    re.compile(r'\b(i\s+)(took|ate|drank|did|went|saw|heard|read|bought|received|finished|started)\b', re.IGNORECASE),
    re.compile(r'\b(i\s+have\s+a|my\s+doctor\s+is|my\s+name\s+is|i\s+am\s+\d+\s+years)\b', re.IGNORECASE),
    re.compile(r'\b(i\s+live\s+in|i\s+work\s+at|i\s+was\s+born\s+in)\b', re.IGNORECASE),
    re.compile(r'\b(i\s+am\s+allergic|i\s+am\s+diabetic|i\s+have\s+high\s+blood\s+pressure)\b', re.IGNORECASE),
    re.compile(r'\b(today\s+i|yesterday\s+i|this\s+week\s+i)\b', re.IGNORECASE),
    # Spanish (es-ES)
    re.compile(r'\b(yo\s+|)(tomé|comí|bebí|hice|fui|vi|escuché|leí|compré|recibí|terminé|empecé)\b', re.IGNORECASE),
    re.compile(r'\b(estoy\s+con|tengo\s+dolor|mi\s+médico\s+es|mi\s+nombre\s+es|tengo\s+\d+\s+años)\b', re.IGNORECASE),
    re.compile(r'\b(vivo\s+en|trabajo\s+en|nací\s+en)\b', re.IGNORECASE),
    re.compile(r'\b(soy\s+alérgico|soy\s+diabético|tengo\s+hipertensión)\b', re.IGNORECASE),
    re.compile(r'\b(hoy\s+yo|ayer\s+yo|esta\s+semana\s+yo|hoy\s+me)\b', re.IGNORECASE),
]


def extract_facts(message: str) -> List[str]:
    """
    Returns list of sentences from message that match personal fact patterns.
    Each returned string is a sentence containing a detected fact.
    """
    if not message or not message.strip():
        return []

    # Split into sentences and test each one
    sentences = re.split(r'(?<=[.!?])\s+', message.strip())
    facts = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        for pattern in FACT_PATTERNS:
            if pattern.search(sentence):
                facts.append(sentence)
                break  # one match per sentence is enough

    return facts


def store_facts_async(user_id: int, user_message: str, db_path: str) -> None:
    """
    Background thread target: extracts facts from user_message and stores
    them in user_data with key='fato'. Opens its own DB connection.
    """
    def _run():
        facts = extract_facts(user_message)
        if not facts:
            return
        try:
            from database import Database
            db = Database(db_path)
            for fact in facts:
                db.store_fact(user_id, 'fato', fact)
            db.close()
        except Exception as e:
            print(f"⚠️  [Memory] Erro ao salvar fatos: {e}")

    threading.Thread(target=_run, daemon=True, name="FactExtraction").start()


def search_facts(user_id: int, query: str, db) -> List[str]:
    """
    Searches stored personal facts for the user using FTS5.
    Returns list of fact strings ready for prompt injection.
    """
    try:
        results = db.search_facts(user_id, query, limit=5)
        return [r['value'] for r in results if r.get('value')]
    except Exception as e:
        print(f"⚠️  [Memory] Erro ao buscar fatos: {e}")
        return []
