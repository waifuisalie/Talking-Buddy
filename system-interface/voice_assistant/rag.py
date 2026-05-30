"""
RAG retrieval helpers for the chat path.

embed_query    — embed user text via Ollama granite-embedding:278m
retrieve_context — vec search scoped to a corpus, returns formatted snippet block

Both functions are safe to call from within streaming_pipeline; they never raise.
"""

import os
import struct
import requests
from typing import Optional

_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")
_EMBED_MODEL = os.getenv("EMBED_MODEL", "granite-embedding:278m")
_EMBED_TIMEOUT = float(os.getenv("EMBED_TIMEOUT", "30"))
_EMBED_DIM = 768


def embed_query(text: str) -> Optional[bytes]:
    """Return 768-float packed bytes for text, or None on failure."""
    try:
        resp = requests.post(
            _EMBED_URL,
            json={"model": _EMBED_MODEL, "input": text, "keep_alive": -1},
            timeout=_EMBED_TIMEOUT,
        )
        if resp.status_code != 200:
            print(f"[RAG] embed HTTP {resp.status_code}: {resp.text[:80]}")
            return None
        data = resp.json()
        # Ollama /api/embed returns {"embeddings": [[float, ...]]}
        vecs = data.get("embeddings") or data.get("embedding")
        if not vecs:
            print("[RAG] embed: no embeddings in response")
            return None
        vec = vecs[0] if isinstance(vecs[0], list) else vecs
        if len(vec) != _EMBED_DIM:
            print(f"[RAG] embed: expected {_EMBED_DIM} floats, got {len(vec)}")
            return None
        return struct.pack(f"{_EMBED_DIM}f", *vec)
    except requests.exceptions.Timeout:
        print(f"[RAG] embed timeout after {_EMBED_TIMEOUT}s")
        return None
    except Exception as e:
        print(f"[RAG] embed error: {e}")
        return None


def retrieve_context(db, corpus_id: int, query: str,
                     k: int = 3, max_chars: int = 1500,
                     embedding: Optional[bytes] = None) -> Optional[str]:
    """Return a formatted snippet block, or None if unavailable / no hits.

    Never injects an empty block — if there are no results, returns None so
    the caller adds nothing to the system prompt.

    Pass a pre-computed embedding to avoid a second Ollama call when the
    caller already has one (e.g. from a parallel dispatcher + embed run).
    """
    try:
        if not getattr(db, "vec_available", False):
            return None

        if embedding is None:
            embedding = embed_query(query)
        if embedding is None:
            return None

        rows = db.vector_search(corpus_id, embedding, k=k)
        if not rows:
            return None

        parts = []
        total = 0
        for i, row in enumerate(rows, 1):
            text = row["text"]
            page = row["page_start"]
            label = f"Trecho {i}" + (f" (página {page})" if page else "")
            snippet = f"{label}: {text}"
            if total + len(snippet) > max_chars:
                snippet = snippet[: max_chars - total]
                parts.append(snippet)
                break
            parts.append(snippet)
            total += len(snippet)

        if not parts:
            return None
        return "\n\n".join(parts)
    except Exception as e:
        print(f"[RAG] retrieve_context error: {e}")
        return None
