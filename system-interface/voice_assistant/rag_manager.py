"""
RAG (Retrieval-Augmented Generation) manager.

Indexes PDF documents as named "specializations", stores embeddings as numpy BLOBs
in SQLite, and loads them into RAM for fast cosine similarity search at query time.

Uses paraphrase-multilingual-MiniLM-L12-v2 for cross-lingual retrieval
(pt-BR, en-US, es-ES — all supported in the same embedding space).
"""

import io
import os
import sqlite3
from typing import List, Dict, Tuple, Optional

import numpy as np

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# Chunking parameters
CHUNK_TARGET_CHARS = 1200   # ~400 tokens
CHUNK_OVERLAP_CHARS = 150   # ~50 tokens


class RAGManager:
    """Manages document indexing and semantic search for specializations."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._model = None          # lazy-loaded SentenceTransformer
        self._index: Dict[int, List[Tuple[np.ndarray, str]]] = {}
        self._load_embeddings()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def index_document(self, pdf_path: str, document_id: int) -> int:
        """
        Chunks a PDF, embeds each chunk, and stores them in the DB.
        Returns the number of chunks created.
        """
        text = self._extract_pdf_text(pdf_path)
        if not text.strip():
            raise ValueError("PDF has no extractable text")

        chunks = self._chunk_text(text)
        if not chunks:
            raise ValueError("No chunks produced from PDF")

        # Import here to avoid circular import at module load
        from database import Database
        db = Database(self.db_path)
        try:
            for idx, chunk in enumerate(chunks):
                embedding = self._embed(chunk)
                embedding_bytes = embedding.astype(np.float32).tobytes()
                db.store_rag_chunk(document_id, idx, chunk, embedding_bytes)
            db.update_rag_document_chunk_count(document_id, len(chunks))
        finally:
            db.close()

        self.reload()
        return len(chunks)

    def search(self, query: str, document_id: int,
               threshold: float = 0.6, top_k: int = 3) -> List[str]:
        """
        Returns up to top_k chunk texts whose cosine similarity to the query
        exceeds threshold. Returns [] if the document has no chunks loaded
        or no chunk clears the threshold.
        """
        chunks = self._index.get(document_id)
        if not chunks:
            return []

        q_vec = self._embed(query)
        scored = [
            (self._cosine(q_vec, emb), text)
            for emb, text in chunks
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for score, text in scored[:top_k] if score >= threshold]

    def reload(self) -> None:
        """Re-loads all embeddings from DB into RAM (call after index/delete)."""
        self._load_embeddings()

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _load_embeddings(self) -> None:
        """Loads all stored embeddings into self._index."""
        self._index = {}
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT document_id, chunk_text, embedding FROM rag_chunks ORDER BY document_id, chunk_index"
            ).fetchall()
            conn.close()
            for row in rows:
                doc_id = row['document_id']
                text = row['chunk_text']
                emb = np.frombuffer(row['embedding'], dtype=np.float32).copy()
                self._index.setdefault(doc_id, []).append((emb, text))
            total = sum(len(v) for v in self._index.values())
            if total > 0:
                print(f"✅ [RAG] {total} chunks carregados para {len(self._index)} documento(s)")
        except Exception as e:
            print(f"⚠️  [RAG] Erro ao carregar embeddings: {e}")

    def _get_model(self):
        """Lazy-load the SentenceTransformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                print(f"🔄 [RAG] Carregando modelo {MODEL_NAME}...")
                self._model = SentenceTransformer(MODEL_NAME)
                print(f"✅ [RAG] Modelo carregado")
            except ImportError:
                raise ImportError(
                    "sentence-transformers não instalado. "
                    "Execute: pip install sentence-transformers"
                )
        return self._model

    def _embed(self, text: str) -> np.ndarray:
        """Returns a normalized float32 embedding vector for text."""
        model = self._get_model()
        vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vec.astype(np.float32)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two pre-normalized vectors."""
        return float(np.dot(a, b))

    @staticmethod
    def _extract_pdf_text(pdf_path: str) -> str:
        """Extracts all text from a PDF file using pypdf."""
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("pypdf não instalado. Execute: pip install pypdf")

        reader = PdfReader(pdf_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)

    @staticmethod
    def _chunk_text(text: str) -> List[str]:
        """
        Splits text into overlapping chunks of ~CHUNK_TARGET_CHARS characters.
        Splits preferentially at paragraph boundaries (\n\n), then at sentences,
        then hard-cuts at the target size.
        """
        # Normalize whitespace
        text = text.strip()
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        chunks: List[str] = []
        current = ""

        for para in paragraphs:
            # If adding this paragraph keeps us under target, accumulate
            if len(current) + len(para) + 2 <= CHUNK_TARGET_CHARS:
                current = (current + "\n\n" + para).strip() if current else para
            else:
                # Flush current chunk if non-empty
                if current:
                    chunks.append(current)
                    # Overlap: carry last CHUNK_OVERLAP_CHARS of current into next
                    overlap = current[-CHUNK_OVERLAP_CHARS:].strip()
                    current = (overlap + "\n\n" + para).strip() if overlap else para
                else:
                    # Paragraph itself is larger than target — hard split
                    while len(para) > CHUNK_TARGET_CHARS:
                        cut = para.rfind(' ', 0, CHUNK_TARGET_CHARS)
                        if cut == -1:
                            cut = CHUNK_TARGET_CHARS
                        chunks.append(para[:cut].strip())
                        para = para[cut:].strip()
                    current = para

        if current:
            chunks.append(current)

        return [c for c in chunks if len(c) >= 50]  # discard tiny fragments
