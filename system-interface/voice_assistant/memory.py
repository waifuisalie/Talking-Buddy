"""
Ordered memory helpers for the chat path.

recall            — FTS5 search for personal facts (FACT_RECALL intent)
extract_and_store — post-stream LLM extraction + insert (FACT_STORE intent)

Both are non-raising; failures are logged and silently skipped.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional


_VALID_TYPES = {"medication", "mood", "symptom", "activity", "appointment", "other"}

_EXTRACT_SYSTEM = """Você é um extrator de fatos pessoais de saúde e rotina. \
Dado um trecho de fala do usuário, extraia:

1. event_type: um de: medication | mood | symptom | activity | appointment | other
2. extracted_value: JSON com campos relevantes (ex: {"medication":"losartana","dose":"50mg"}) \
ou null se não aplicável
3. occurred_at: horário ISO 8601 do evento SE mencionado (ex: "2026-05-09T08:00:00"), caso \
contrário null

Responda APENAS com JSON válido, nenhum texto extra:
{"event_type":"...", "extracted_value":..., "occurred_at":...}"""


def recall(db, user_id: int, query: str, limit: int = 5) -> Optional[str]:
    """FTS5 search across user_memories. Returns formatted bullet list or None."""
    try:
        # FTS5 requires all tokens present; strip stop-words-only queries gracefully
        fts_query = _to_fts_query(query)
        if not fts_query:
            return None
        rows = db.recall_memory_fts(user_id, fts_query, limit=limit)
        if not rows:
            return None
        lines = []
        for row in rows:
            when = row["occurred_at"] or row["created_at"] or ""
            when_str = f" [{when[:16]}]" if when else ""
            lines.append(f"- {row['content']}{when_str}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[MEMORY] recall error: {e}")
        return None


def extract_and_store(db, user_id: int, user_message: str, ollama_client) -> Optional[int]:
    """Run extraction LLM call and insert a user_memories row.

    Returns the new row id or None on failure. Never raises.
    """
    try:
        raw = ollama_client.generate_response(
            prompt=user_message,
            system_prompt=_EXTRACT_SYSTEM,
        )
        if not raw:
            return _store_fallback(db, user_id, user_message)

        parsed = _parse_extraction(raw)
        event_type = parsed.get("event_type", "other")
        if event_type not in _VALID_TYPES:
            event_type = "other"
        extracted_value = parsed.get("extracted_value")
        occurred_at = parsed.get("occurred_at")

        ev_str = json.dumps(extracted_value, ensure_ascii=False) if extracted_value else None

        row_id = db.add_memory(
            user_id=user_id,
            event_type=event_type,
            content=user_message,
            extracted_value=ev_str,
            occurred_at=occurred_at,
            source="voice",
        )
        print(f"[MEMORY] stored id={row_id} type={event_type} occurred_at={occurred_at}")
        return row_id
    except Exception as e:
        print(f"[MEMORY] extract_and_store error: {e}")
        return _store_fallback(db, user_id, user_message)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _store_fallback(db, user_id: int, content: str) -> Optional[int]:
    """Store raw utterance as event_type='other' when extraction fails."""
    try:
        return db.add_memory(user_id=user_id, event_type="other", content=content)
    except Exception as e:
        print(f"[MEMORY] fallback store error: {e}")
        return None


def _parse_extraction(raw: str) -> dict:
    """Lenient JSON parse: json.loads, then regex fallback."""
    raw = raw.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Regex fallback: grab first {...} block
    m = re.search(r"\{.*?\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


def _to_fts_query(text: str) -> str:
    """Convert free-form text to a FTS5 query: keep alpha tokens ≥3 chars."""
    tokens = re.findall(r"[a-záéíóúâêîôûãõàèìòùç]{3,}", text.lower())
    # Drop very common Portuguese stopwords that break FTS precision
    _STOPWORDS = {"que", "para", "com", "uma", "por", "mas", "foi", "ele",
                  "ela", "dos", "das", "nos", "nas", "seu", "sua", "esse",
                  "essa", "isto", "aqui", "ali", "como", "mais", "quando"}
    tokens = [t for t in tokens if t not in _STOPWORDS]
    return " ".join(tokens)
