"""
Ordered memory helpers for the chat path.

recall            — semantic vec search for personal facts (FACT_RECALL intent)
extract_and_store — post-stream LLM extraction + Python timestamp + embed + insert

Both are non-raising; failures are logged and silently skipped.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional

from . import rag

try:
    from dateparser.search import search_dates
    _DATEPARSER_OK = True
except Exception:
    _DATEPARSER_OK = False


_VALID_TYPES = {"medication", "mood", "symptom", "activity", "appointment", "other"}

_EXTRACT_SYSTEM = """Você é um extrator de fatos pessoais de saúde e rotina. \
Dado um trecho de fala do usuário, extraia:

1. event_type: um de: medication | mood | symptom | activity | appointment | other
2. extracted_value: JSON com campos relevantes (ex: {"medication":"losartana","dose":"50mg"}) \
ou null se não aplicável

Responda APENAS com JSON válido, nenhum texto extra:
{"event_type":"...", "extracted_value":...}"""


def recall(db, user_id: int, query: str, limit: int = 5,
           embedding: Optional[bytes] = None) -> Optional[str]:
    """Semantic vec search across user_memories. Returns formatted bullet list or None.

    Pass a pre-computed embedding to avoid a second Ollama call when the
    caller already has one (e.g. from a parallel dispatcher + embed run).
    """
    try:
        if not getattr(db, "vec_available", False):
            return None
        if embedding is None:
            embedding = rag.embed_query(query)
        if embedding is None:
            return None
        rows = db.vector_search_memory(user_id, embedding, k=limit)
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
    """Run extraction LLM call, parse timestamp in Python, embed, and insert.

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

        ev_str = json.dumps(extracted_value, ensure_ascii=False) if extracted_value else None

        occurred_at = _parse_time(user_message)

        embedding = rag.embed_query(user_message)
        if embedding is None:
            print("[MEMORY] embed failed — storing row without vec entry")

        row_id = db.add_memory(
            user_id=user_id,
            event_type=event_type,
            content=user_message,
            extracted_value=ev_str,
            occurred_at=occurred_at,
            source="voice",
            embedding=embedding,
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
    raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*?\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


def _parse_time(text: str) -> str:
    """Parse PT-BR time expressions; always returns an ISO 8601 string.

    Falls back to now() when dateparser is unavailable or no date is found
    in the utterance — which is correct for the common "agora" / "acabei de"
    case where the user is talking about something they just did.
    """
    now = datetime.now(timezone.utc)
    if not _DATEPARSER_OK:
        return now.isoformat()
    try:
        hits = search_dates(
            text,
            languages=["pt"],
            settings={
                "RELATIVE_BASE": now,
                "PREFER_DATES_FROM": "past",
                "RETURN_AS_TIMEZONE_AWARE": True,
            },
        )
        if hits:
            return hits[0][1].isoformat()
    except Exception as e:
        print(f"[MEMORY] _parse_time error: {e}")
    return now.isoformat()
