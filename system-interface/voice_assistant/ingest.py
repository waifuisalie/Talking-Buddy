"""
RAG Ingest CLI

Pre-load specializations (corpora) and ingest PDFs into them. Each corpus
is a shared knowledge base that users select at account-creation time.

Usage (run from system-interface/):
    python -m voice_assistant.ingest corpus create --slug NAME --name "Display"
    python -m voice_assistant.ingest corpus list
    python -m voice_assistant.ingest corpus delete --slug NAME
    python -m voice_assistant.ingest doc add --corpus SLUG --pdf path/to/file.pdf
    python -m voice_assistant.ingest doc list --corpus SLUG
    python -m voice_assistant.ingest doc delete --doc-id ID
"""

import argparse
import hashlib
import os
import re
import shutil
import struct
import sys
from typing import List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_SI_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_SI_ROOT, "src"))

import requests  # noqa: E402

from database import (  # noqa: E402
    Database,
    EMBEDDING_DIM,
    EMBEDDING_MODEL_DEFAULT,
)

DB_PATH = os.path.join(_SI_ROOT, "assistant.db")
RAG_PDF_DIR = os.path.join(_SI_ROOT, "data", "rag", "corpora")
OLLAMA_EMBED_URL = os.environ.get(
    "OLLAMA_EMBED_URL", "http://localhost:11434/api/embed"
)

CHUNK_TARGET_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 80
MIN_CHUNK_TOKENS = 100


# ---------- text utilities ----------

def _slugify_filename(name: str) -> str:
    name = re.sub(r"[^\w\s.-]", "", name, flags=re.UNICODE)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name or "file.pdf"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _approx_tokens(text: str) -> int:
    # PT-BR rough proxy: ~1.3 tokens per whitespace-delimited word for granite tokenizer
    return int(len(text.split()) * 1.3)


def _extract_text(pdf_path: str) -> List[Tuple[int, str]]:
    """Return [(page_num, page_text), ...] starting from page 1."""
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    out: List[Tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        txt = re.sub(r"[ \t]+", " ", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt)
        out.append((i, txt.strip()))
    return out


_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9])")


def _split_sentences(text: str) -> List[str]:
    if not text.strip():
        return []
    parts = _SENT_BOUNDARY.split(text)
    return [p.strip() for p in parts if p.strip()]


def _chunk_pages(pages: List[Tuple[int, str]],
                 target: int = CHUNK_TARGET_TOKENS,
                 overlap: int = CHUNK_OVERLAP_TOKENS) -> List[dict]:
    """Group sentences into ~target-token chunks with overlap, tracking source pages."""
    chunks: List[dict] = []
    buf: List[Tuple[int, str]] = []   # [(page_num, sentence)]
    buf_tokens = 0

    def flush_with_overlap():
        nonlocal buf, buf_tokens
        if not buf:
            return
        text = " ".join(s for _, s in buf).strip()
        if _approx_tokens(text) >= MIN_CHUNK_TOKENS:
            chunks.append({
                "text": text,
                "page_start": buf[0][0],
                "page_end": buf[-1][0],
            })
        # Carry trailing overlap into the next chunk
        carry: List[Tuple[int, str]] = []
        carry_tokens = 0
        for ps in reversed(buf):
            carry.insert(0, ps)
            carry_tokens += _approx_tokens(ps[1])
            if carry_tokens >= overlap:
                break
        buf = carry
        buf_tokens = carry_tokens

    for page_num, page_text in pages:
        for sent in _split_sentences(page_text):
            tk = _approx_tokens(sent)
            if buf_tokens + tk > target and buf_tokens > 0:
                flush_with_overlap()
            buf.append((page_num, sent))
            buf_tokens += tk

    # Final flush (no overlap needed at end). Keep even if below MIN_CHUNK_TOKENS
    # only when nothing else was emitted, to avoid losing very-short documents entirely.
    if buf:
        text = " ".join(s for _, s in buf).strip()
        if _approx_tokens(text) >= MIN_CHUNK_TOKENS or not chunks:
            chunks.append({
                "text": text,
                "page_start": buf[0][0],
                "page_end": buf[-1][0],
            })
    return chunks


# ---------- embedding ----------

def _embed_text(text: str, model: str = EMBEDDING_MODEL_DEFAULT) -> Optional[List[float]]:
    """POST /api/embed; return list of floats or None on failure."""
    try:
        resp = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": model, "input": text},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        if "embeddings" in data and data["embeddings"]:
            return data["embeddings"][0]
        if "embedding" in data:
            return data["embedding"]
        return None
    except Exception as e:
        print(f"  [embed] error: {e}")
        return None


def _pack_floats(floats: List[float]) -> bytes:
    if len(floats) != EMBEDDING_DIM:
        raise ValueError(f"expected {EMBEDDING_DIM}-dim embedding, got {len(floats)}")
    return struct.pack(f"{EMBEDDING_DIM}f", *floats)


# ---------- commands ----------

def cmd_corpus_create(args, db: Database) -> int:
    if db.get_corpus_by_slug(args.slug):
        print(f"corpus '{args.slug}' já existe")
        return 1
    corpus_id = db.add_corpus(
        slug=args.slug,
        display_name=args.name,
        description=args.description or "",
        language=args.language,
        embedding_model=EMBEDDING_MODEL_DEFAULT,
    )
    print(f"corpus criado: id={corpus_id} slug={args.slug} name={args.name!r}")
    return 0


def cmd_corpus_list(args, db: Database) -> int:
    rows = db.list_corpora(only_enabled=False)
    if not rows:
        print("(nenhum corpus cadastrado)")
        return 0
    print(f"{'ID':<4} {'SLUG':<24} {'NAME':<32} {'DOCS':>5} {'CHUNKS':>7} {'LANG':<6} ENABLED")
    for r in rows:
        print(
            f"{r['id']:<4} {r['slug']:<24} {r['display_name'][:32]:<32} "
            f"{r['document_count']:>5} {r['chunk_count']:>7} "
            f"{(r['language'] or '-'):<6} {'yes' if r['enabled'] else 'no'}"
        )
    return 0


def cmd_corpus_delete(args, db: Database) -> int:
    c = db.get_corpus_by_slug(args.slug)
    if not c:
        print(f"corpus '{args.slug}' não encontrado")
        return 1
    db.delete_corpus(c["id"])
    pdf_dir = os.path.join(RAG_PDF_DIR, args.slug)
    if os.path.isdir(pdf_dir):
        shutil.rmtree(pdf_dir)
    print(f"corpus '{args.slug}' (id={c['id']}) e seus documentos foram removidos")
    return 0


def cmd_doc_add(args, db: Database) -> int:
    c = db.get_corpus_by_slug(args.corpus)
    if not c:
        print(f"corpus '{args.corpus}' não encontrado")
        return 1
    if not db.vec_available:
        print("ERRO: sqlite-vec indisponível — não é possível adicionar documentos")
        return 2

    pdf_path = os.path.abspath(os.path.expanduser(args.pdf))
    if not os.path.isfile(pdf_path):
        print(f"arquivo não encontrado: {pdf_path}")
        return 1

    print("[1/5] sha256...")
    sha = _sha256_file(pdf_path)
    existing = db.conn.execute(
        "SELECT id, filename FROM rag_documents WHERE corpus_id=? AND sha256=?",
        (c["id"], sha),
    ).fetchone()
    if existing:
        print(f"PDF já ingerido (doc id={existing['id']}, filename={existing['filename']}); pulando")
        return 0

    print(f"[2/5] copiando para data/rag/corpora/{args.corpus}/...")
    target_dir = os.path.join(RAG_PDF_DIR, args.corpus)
    os.makedirs(target_dir, exist_ok=True)
    target_filename = _slugify_filename(os.path.basename(pdf_path))
    target_path = os.path.join(target_dir, target_filename)
    shutil.copy2(pdf_path, target_path)

    print("[3/5] extraindo texto...")
    pages = _extract_text(target_path)
    if not any(t for _, t in pages):
        print("ERRO: PDF sem texto extraível (pode ser scaneado)")
        os.remove(target_path)
        return 1
    page_count = len(pages)

    print(f"[4/5] chunking ({page_count} páginas)...")
    chunks = _chunk_pages(pages)
    if not chunks:
        print("ERRO: nenhum chunk válido gerado")
        os.remove(target_path)
        return 1
    print(f"  -> {len(chunks)} chunks")

    print(f"[5/5] embeddings via Ollama ({EMBEDDING_MODEL_DEFAULT})...")
    doc_id = db.add_document(
        corpus_id=c["id"],
        filename=target_filename,
        filepath=target_path,
        sha256=sha,
        page_count=page_count,
        chunk_count=0,
    )
    inserted = 0
    for i, ch in enumerate(chunks):
        emb = _embed_text(ch["text"])
        if emb is None:
            print(f"  chunk {i+1}/{len(chunks)}: FALHOU (embedding)")
            continue
        try:
            packed = _pack_floats(emb)
        except ValueError as e:
            print(f"  chunk {i+1}/{len(chunks)}: FALHOU ({e})")
            continue
        db.add_chunk(
            corpus_id=c["id"],
            document_id=doc_id,
            chunk_index=i,
            text=ch["text"],
            embedding=packed,
            page_start=ch["page_start"],
            page_end=ch["page_end"],
        )
        inserted += 1
        if (i + 1) % 10 == 0 or (i + 1) == len(chunks):
            print(f"  chunk {i+1}/{len(chunks)} ok")

    db.conn.execute(
        "UPDATE rag_documents SET chunk_count=? WHERE id=?",
        (inserted, doc_id),
    )
    db.conn.commit()
    db.update_corpus_counts(c["id"])
    print(f"OK: doc id={doc_id}, {inserted}/{len(chunks)} chunks inseridos")
    return 0 if inserted > 0 else 1


def cmd_doc_list(args, db: Database) -> int:
    c = db.get_corpus_by_slug(args.corpus)
    if not c:
        print(f"corpus '{args.corpus}' não encontrado")
        return 1
    rows = db.get_documents_by_corpus(c["id"])
    if not rows:
        print("(nenhum documento)")
        return 0
    print(f"{'ID':<4} {'FILENAME':<48} {'PAGES':>5} {'CHUNKS':>7} INGESTED")
    for r in rows:
        print(
            f"{r['id']:<4} {r['filename'][:48]:<48} "
            f"{(r['page_count'] or 0):>5} {(r['chunk_count'] or 0):>7} {r['ingested_at']}"
        )
    return 0


def cmd_memory_backfill(args, db: Database) -> int:
    """Embed user_memories rows that are missing a user_memories_vec entry."""
    if not db.vec_available:
        print("sqlite-vec indisponível — backfill abortado")
        return 1
    rows = db.memories_missing_embedding()
    if not rows:
        print("nenhuma memória pendente de embedding")
        return 0
    print(f"{len(rows)} memória(s) sem embedding — gerando...")
    ok = 0
    fail = 0
    for r in rows:
        vec = _embed_text(r["content"])
        if vec is None:
            print(f"  id={r['id']} user={r['user_id']}: embed falhou")
            fail += 1
            continue
        try:
            packed = _pack_floats(vec)
            db.conn.execute(
                "INSERT INTO user_memories_vec(rowid, user_id, embedding) VALUES (?, ?, ?)",
                (r["id"], r["user_id"], packed),
            )
            db.conn.commit()
            ok += 1
            print(f"  id={r['id']} user={r['user_id']}: ok")
        except Exception as e:
            print(f"  id={r['id']} user={r['user_id']}: insert falhou: {e}")
            fail += 1
    print(f"backfill concluído: {ok} ok, {fail} falha(s)")
    return 0 if fail == 0 else 1


def cmd_doc_delete(args, db: Database) -> int:
    doc = db.get_document(args.doc_id)
    if not doc:
        print(f"documento id={args.doc_id} não encontrado")
        return 1
    corpus_id = doc["corpus_id"]
    filepath = doc["filepath"]
    db.delete_document(args.doc_id)
    if filepath and os.path.isfile(filepath):
        try:
            os.remove(filepath)
        except OSError as e:
            print(f"aviso: não foi possível remover {filepath}: {e}")
    db.update_corpus_counts(corpus_id)
    print(f"documento id={args.doc_id} ({doc['filename']}) removido")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="ingest", description="RAG ingest CLI")
    sp = p.add_subparsers(dest="entity", required=True)

    pc = sp.add_parser("corpus", help="manage corpora")
    pcs = pc.add_subparsers(dest="action", required=True)

    pc_create = pcs.add_parser("create", help="create new corpus")
    pc_create.add_argument("--slug", required=True)
    pc_create.add_argument("--name", required=True)
    pc_create.add_argument("--description", default="")
    pc_create.add_argument("--language", default="pt-BR")
    pc_create.set_defaults(func=cmd_corpus_create)

    pc_list = pcs.add_parser("list", help="list corpora")
    pc_list.set_defaults(func=cmd_corpus_list)

    pc_delete = pcs.add_parser("delete", help="delete corpus and all its documents")
    pc_delete.add_argument("--slug", required=True)
    pc_delete.set_defaults(func=cmd_corpus_delete)

    pd = sp.add_parser("doc", help="manage documents")
    pds = pd.add_subparsers(dest="action", required=True)

    pd_add = pds.add_parser("add", help="ingest a PDF into a corpus")
    pd_add.add_argument("--corpus", required=True, help="corpus slug")
    pd_add.add_argument("--pdf", required=True, help="path to PDF file")
    pd_add.set_defaults(func=cmd_doc_add)

    pd_list = pds.add_parser("list", help="list documents in a corpus")
    pd_list.add_argument("--corpus", required=True)
    pd_list.set_defaults(func=cmd_doc_list)

    pd_delete = pds.add_parser("delete", help="delete a document")
    pd_delete.add_argument("--doc-id", type=int, required=True, dest="doc_id")
    pd_delete.set_defaults(func=cmd_doc_delete)

    pm = sp.add_parser("memory", help="manage user memory embeddings")
    pms = pm.add_subparsers(dest="action", required=True)

    pm_backfill = pms.add_parser(
        "backfill",
        help="embed user_memories rows that don't yet have a vec entry",
    )
    pm_backfill.set_defaults(func=cmd_memory_backfill)

    args = p.parse_args()
    db = Database(DB_PATH)
    try:
        return args.func(args, db) or 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
