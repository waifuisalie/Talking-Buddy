#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de gerenciamento do banco de dados SQLite
Responsável por todas as operações de BD (admins, users, user_data)
"""

import datetime as _dt
import hashlib
import os
import secrets
import sqlite3
from typing import Optional, List

try:
    import sqlite_vec  # type: ignore
    _SQLITE_VEC_IMPORT_OK = True
    _SQLITE_VEC_IMPORT_ERR: Optional[str] = None
except Exception as _e:
    sqlite_vec = None  # type: ignore
    _SQLITE_VEC_IMPORT_OK = False
    _SQLITE_VEC_IMPORT_ERR = str(_e)

# Configurações de segurança
PBKDF2_ITERS = 200_000
PBKDF2_HASH = "sha256"
SALT_LEN = 16

# Opções do sistema
RESPONSE_STYLES = [
    "short (objective)",
    "neutral (balanced)",
    "detailed (explanatory)",
    "formal (business)",
    "casual (chatty)",
]
GENDERS = ["male", "female"]
LANGUAGES = ["pt-BR", "en-US", "es-ES"]

EMBEDDING_MODEL_DEFAULT = "granite-embedding:278m"
EMBEDDING_DIM = 768

# Tabelas base: existem independentemente da extensão sqlite-vec.
# Inclui RAG metadata (rag_corpora / rag_documents / rag_chunks_text) — apenas
# o índice vetorial real exige a extensão.
SCHEMA_SQL_BASE = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  pass_salt BLOB NOT NULL,
  pass_hash BLOB NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  rfid TEXT NOT NULL UNIQUE,
  response_style TEXT NOT NULL DEFAULT 'neutral (balanced)',
  persona_gender TEXT NOT NULL DEFAULT 'male',
  language TEXT NOT NULL DEFAULT 'pt-BR',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_data (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversation_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  metadata TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rag_corpora (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  description TEXT,
  language TEXT,
  embedding_model TEXT NOT NULL,
  document_count INTEGER NOT NULL DEFAULT 0,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rag_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  corpus_id INTEGER NOT NULL,
  filename TEXT NOT NULL,
  filepath TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  page_count INTEGER,
  chunk_count INTEGER,
  ingested_at TEXT NOT NULL,
  FOREIGN KEY(corpus_id) REFERENCES rag_corpora(id) ON DELETE CASCADE,
  UNIQUE(corpus_id, sha256)
);

CREATE TABLE IF NOT EXISTS rag_chunks_text (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  corpus_id INTEGER NOT NULL,
  document_id INTEGER NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  page_start INTEGER,
  page_end INTEGER,
  FOREIGN KEY(document_id) REFERENCES rag_documents(id) ON DELETE CASCADE,
  FOREIGN KEY(corpus_id) REFERENCES rag_corpora(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_data_user_id ON user_data(user_id);
CREATE INDEX IF NOT EXISTS idx_users_name ON users(name);
CREATE INDEX IF NOT EXISTS idx_users_rfid ON users(rfid);
CREATE INDEX IF NOT EXISTS idx_conversation_user_id ON conversation_history(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_created_at ON conversation_history(created_at);
CREATE INDEX IF NOT EXISTS idx_ragdoc_corpus ON rag_documents(corpus_id);
CREATE INDEX IF NOT EXISTS idx_ragchunks_corpus ON rag_chunks_text(corpus_id);
CREATE INDEX IF NOT EXISTS idx_ragchunks_doc ON rag_chunks_text(document_id);
"""

# Memória Ordenada: user_memories + FTS5. Independente da extensão sqlite-vec.
SCHEMA_SQL_MEMORY = """
CREATE TABLE IF NOT EXISTS user_memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  content TEXT NOT NULL,
  extracted_value TEXT,
  occurred_at TEXT,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'voice',
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_um_user_time ON user_memories(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_um_user_type ON user_memories(user_id, event_type);

CREATE VIRTUAL TABLE IF NOT EXISTS user_memories_fts USING fts5(
  content,
  content='user_memories',
  content_rowid='id',
  tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS user_memories_ai AFTER INSERT ON user_memories BEGIN
  INSERT INTO user_memories_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS user_memories_ad AFTER DELETE ON user_memories BEGIN
  INSERT INTO user_memories_fts(user_memories_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
"""

# Índice vetorial: requer a extensão sqlite-vec. Criado apenas se vec_available.
SCHEMA_SQL_VEC = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_vec USING vec0(
  corpus_id INTEGER PARTITION KEY,
  embedding FLOAT[{EMBEDDING_DIM}]
);
"""


def now_iso() -> str:
    """Retorna timestamp ISO atual em UTC"""
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def ensure_dir(path: str) -> None:
    """Garante que o diretório do arquivo existe"""
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)


def pbkdf2_hash_password(password: str, salt: bytes) -> bytes:
    """Hash seguro de senha com PBKDF2"""
    return hashlib.pbkdf2_hmac(PBKDF2_HASH, password.encode("utf-8"), salt, PBKDF2_ITERS)


class Database:
    """Gerenciador de banco de dados SQLite"""

    def __init__(self, db_path: str):
        ensure_dir(db_path)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        # WAL: permite leitor + escritor concorrentes (necessário para a thread
        # async de extração de memória que escreve em paralelo ao streaming).
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.Error as e:
            print(f"[DB] PRAGMA journal_mode=WAL falhou (não-fatal): {e}")

        # Tenta carregar a extensão sqlite-vec. Se falhar, RAG vetorial fica off
        # mas o resto do app continua funcionando.
        self.vec_available = False
        self.vec_error: Optional[str] = None
        if not _SQLITE_VEC_IMPORT_OK:
            self.vec_error = f"sqlite_vec import failed: {_SQLITE_VEC_IMPORT_ERR}"
            print(f"[DB] sqlite-vec indisponível ({self.vec_error}) — RAG vetorial desativado")
        else:
            try:
                self.conn.enable_load_extension(True)
                sqlite_vec.load(self.conn)
                self.conn.enable_load_extension(False)
                self.vec_available = True
            except Exception as e:
                self.vec_error = str(e)
                print(f"[DB] sqlite-vec falhou ao carregar ({e}) — RAG vetorial desativado")

        # Cria tabelas base + memória ordenada
        self.conn.executescript(SCHEMA_SQL_BASE)
        self.conn.executescript(SCHEMA_SQL_MEMORY)

        # Índice vetorial só se a extensão estiver disponível
        if self.vec_available:
            try:
                self.conn.executescript(SCHEMA_SQL_VEC)
            except Exception as e:
                self.vec_available = False
                self.vec_error = f"vec0 schema falhou: {e}"
                print(f"[DB] {self.vec_error} — RAG vetorial desativado")

        # Migração idempotente: adiciona users.specialization_id se ausente
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(users)")}
        if "specialization_id" not in cols:
            self.conn.execute(
                "ALTER TABLE users ADD COLUMN specialization_id INTEGER REFERENCES rag_corpora(id)"
            )

        self.conn.commit()

    def close(self):
        """Fecha a conexão com o banco"""
        try:
            self.conn.close()
        except Exception:
            pass

    # ========== ADMINS ==========
    
    def has_any_admin(self) -> bool:
        """Verifica se existe pelo menos um admin cadastrado"""
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM admins LIMIT 1")
        return cur.fetchone() is not None

    def upsert_admin(self, username: str, password: str) -> None:
        """Cria ou atualiza um admin"""
        salt = secrets.token_bytes(SALT_LEN)
        ph = pbkdf2_hash_password(password, salt)
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM admins WHERE username=?", (username,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE admins SET pass_salt=?, pass_hash=?, created_at=? WHERE username=?",
                (salt, ph, now_iso(), username),
            )
        else:
            cur.execute(
                "INSERT INTO admins(username, pass_salt, pass_hash, created_at) VALUES (?,?,?,?)",
                (username, salt, ph, now_iso()),
            )
        self.conn.commit()

    def verify_admin(self, username: str, password: str) -> bool:
        """Verifica credenciais de admin"""
        cur = self.conn.cursor()
        cur.execute("SELECT pass_salt, pass_hash FROM admins WHERE username=?", (username,))
        row = cur.fetchone()
        if not row:
            return False
        salt = row["pass_salt"]
        expected = row["pass_hash"]
        candidate = pbkdf2_hash_password(password, salt)
        return secrets.compare_digest(expected, candidate)

    # ========== USERS ==========
    
    def list_users(self) -> List[sqlite3.Row]:
        """Lista todos os usuários ordenados por nome"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, rfid, response_style, persona_gender, language, specialization_id, created_at "
            "FROM users ORDER BY name COLLATE NOCASE"
        )
        return cur.fetchall()

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        """Busca um usuário por ID"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, rfid, response_style, persona_gender, language, specialization_id, created_at "
            "FROM users WHERE id=?",
            (user_id,),
        )
        return cur.fetchone()

    def get_user_by_rfid(self, rfid: str) -> Optional[sqlite3.Row]:
        """Busca um usuário por RFID"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, rfid, response_style, persona_gender, language, specialization_id, created_at "
            "FROM users WHERE rfid=?",
            (rfid,),
        )
        return cur.fetchone()
    
    def user_exists_by_name(self, name: str, exclude_id: Optional[int] = None) -> bool:
        """Verifica se já existe um usuário com esse nome"""
        cur = self.conn.cursor()
        if exclude_id:
            cur.execute("SELECT 1 FROM users WHERE name=? AND id!=? LIMIT 1", (name, exclude_id))
        else:
            cur.execute("SELECT 1 FROM users WHERE name=? LIMIT 1", (name,))
        return cur.fetchone() is not None
    
    def user_exists_by_rfid(self, rfid: str, exclude_id: Optional[int] = None) -> bool:
        """Verifica se já existe um usuário com esse RFID"""
        cur = self.conn.cursor()
        if exclude_id:
            cur.execute("SELECT 1 FROM users WHERE rfid=? AND id!=? LIMIT 1", (rfid, exclude_id))
        else:
            cur.execute("SELECT 1 FROM users WHERE rfid=? LIMIT 1", (rfid,))
        return cur.fetchone() is not None
    
    def add_user(self, name: str, rfid: str, response_style: str,
                 persona_gender: str, language: str,
                 specialization_id: Optional[int] = None) -> int:
        """
        Adiciona um novo usuário
        Retorna o ID do usuário criado
        """
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO users(name, rfid, response_style, persona_gender, language, specialization_id, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, rfid, response_style, persona_gender, language, specialization_id, now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_user(self, user_id: int, name: str, rfid: str,
                    response_style: str, persona_gender: str, language: str,
                    specialization_id: Optional[int] = None) -> None:
        """Atualiza dados de um usuário existente"""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE users SET name=?, rfid=?, response_style=?, persona_gender=?, language=?, specialization_id=? "
            "WHERE id=?",
            (name, rfid, response_style, persona_gender, language, specialization_id, user_id),
        )
        self.conn.commit()

    def delete_user(self, user_id: int) -> None:
        """Remove um usuário (CASCADE remove user_data também)"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM users WHERE id=?", (user_id,))
        self.conn.commit()

    # ========== USER DATA ==========
    
    def add_user_data(self, user_id: int, key: str, value: str) -> int:
        """
        Adiciona um dado personalizado para um usuário
        Ex: telefone, endereço, etc
        """
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO user_data(user_id, key, value, created_at) VALUES (?,?,?,?)",
            (user_id, key, value, now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid
    
    def get_user_data(self, user_id: int) -> List[sqlite3.Row]:
        """Retorna todos os dados personalizados de um usuário"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, key, value, created_at FROM user_data WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        )
        return cur.fetchall()
    
    def delete_user_data(self, data_id: int) -> None:
        """Remove um dado personalizado"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM user_data WHERE id=?", (data_id,))
        self.conn.commit()

    # ========== CONVERSATION HISTORY ==========
    
    def add_conversation_message(self, user_id: int, role: str, content: str, metadata: str = "{}") -> int:
        """
        Adiciona uma mensagem ao histórico de conversa
        
        Args:
            user_id: ID do usuário
            role: "user" ou "assistant"
            content: Texto da mensagem
            metadata: JSON string com metadados (audio_url, duration, etc)
        
        Returns:
            ID da mensagem inserida
        """
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO conversation_history(user_id, role, content, metadata, created_at) "
            "VALUES (?,?,?,?,?)",
            (user_id, role, content, metadata, now_iso())
        )
        self.conn.commit()
        return cur.lastrowid
    
    def get_conversation_history(self, user_id: int, limit: int = 50) -> List[sqlite3.Row]:
        """
        Recupera histórico de conversa de um usuário
        
        Args:
            user_id: ID do usuário
            limit: Número máximo de mensagens (padrão: 50)
        
        Returns:
            Lista de mensagens ordenadas por data (mais antigas primeiro)
        """
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, role, content, metadata, created_at "
            "FROM ("
            "  SELECT id, role, content, metadata, created_at "
            "  FROM conversation_history "
            "  WHERE user_id=? "
            "  ORDER BY created_at DESC "
            "  LIMIT ?"
            ") ORDER BY created_at ASC",
            (user_id, limit)
        )
        return cur.fetchall()
    
    def clear_conversation_history(self, user_id: int, keep_last: int = 0) -> int:
        """
        Limpa histórico de conversa de um usuário
        
        Args:
            user_id: ID do usuário
            keep_last: Número de mensagens recentes para manter (0 = limpa tudo)
        
        Returns:
            Número de mensagens removidas
        """
        cur = self.conn.cursor()
        
        if keep_last > 0:
            # Remove mensagens antigas, mantendo as N mais recentes
            cur.execute(
                "DELETE FROM conversation_history "
                "WHERE user_id=? AND id NOT IN ("
                "  SELECT id FROM conversation_history "
                "  WHERE user_id=? "
                "  ORDER BY created_at DESC "
                "  LIMIT ?"
                ")",
                (user_id, user_id, keep_last)
            )
        else:
            # Remove todas as mensagens
            cur.execute("DELETE FROM conversation_history WHERE user_id=?", (user_id,))

        removed = cur.rowcount
        self.conn.commit()
        return removed

    # ========== RAG CORPORA ==========

    def add_corpus(self, slug: str, display_name: str, description: str = "",
                   language: str = "pt-BR",
                   embedding_model: str = EMBEDDING_MODEL_DEFAULT) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO rag_corpora(slug, display_name, description, language, "
            "embedding_model, created_at) VALUES (?,?,?,?,?,?)",
            (slug, display_name, description, language, embedding_model, now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_corpus_by_id(self, corpus_id: int) -> Optional[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM rag_corpora WHERE id=?", (corpus_id,))
        return cur.fetchone()

    def get_corpus_by_slug(self, slug: str) -> Optional[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM rag_corpora WHERE slug=?", (slug,))
        return cur.fetchone()

    def list_corpora(self, only_enabled: bool = False) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        if only_enabled:
            cur.execute("SELECT * FROM rag_corpora WHERE enabled=1 ORDER BY display_name")
        else:
            cur.execute("SELECT * FROM rag_corpora ORDER BY display_name")
        return cur.fetchall()

    def delete_corpus(self, corpus_id: int) -> None:
        """Remove corpus + cascading documents/chunks_text. Vec rows must be deleted explicitly."""
        if self.vec_available:
            try:
                self.conn.execute("DELETE FROM rag_chunks_vec WHERE corpus_id=?", (corpus_id,))
            except Exception as e:
                print(f"[DB] delete_corpus vec cleanup falhou: {e}")
        self.conn.execute("DELETE FROM rag_corpora WHERE id=?", (corpus_id,))
        self.conn.commit()

    def update_corpus_counts(self, corpus_id: int) -> None:
        """Recompute and persist document_count + chunk_count for a corpus."""
        self.conn.execute(
            "UPDATE rag_corpora SET "
            "document_count=(SELECT COUNT(*) FROM rag_documents WHERE corpus_id=?), "
            "chunk_count=(SELECT COUNT(*) FROM rag_chunks_text WHERE corpus_id=?) "
            "WHERE id=?",
            (corpus_id, corpus_id, corpus_id),
        )
        self.conn.commit()

    # ========== RAG DOCUMENTS ==========

    def add_document(self, corpus_id: int, filename: str, filepath: str,
                     sha256: str, page_count: int, chunk_count: int = 0) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO rag_documents(corpus_id, filename, filepath, sha256, "
            "page_count, chunk_count, ingested_at) VALUES (?,?,?,?,?,?,?)",
            (corpus_id, filename, filepath, sha256, page_count, chunk_count, now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_document(self, document_id: int) -> Optional[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM rag_documents WHERE id=?", (document_id,))
        return cur.fetchone()

    def get_documents_by_corpus(self, corpus_id: int) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM rag_documents WHERE corpus_id=? ORDER BY ingested_at DESC",
            (corpus_id,),
        )
        return cur.fetchall()

    def delete_document(self, document_id: int) -> None:
        """Remove document + cascading chunks_text. Vec rows must be deleted explicitly via rowid."""
        if self.vec_available:
            try:
                cur = self.conn.cursor()
                cur.execute("SELECT id FROM rag_chunks_text WHERE document_id=?", (document_id,))
                chunk_ids = [r[0] for r in cur.fetchall()]
                if chunk_ids:
                    placeholders = ",".join("?" * len(chunk_ids))
                    self.conn.execute(
                        f"DELETE FROM rag_chunks_vec WHERE rowid IN ({placeholders})",
                        chunk_ids,
                    )
            except Exception as e:
                print(f"[DB] delete_document vec cleanup falhou: {e}")
        self.conn.execute("DELETE FROM rag_documents WHERE id=?", (document_id,))
        self.conn.commit()

    # ========== RAG CHUNKS ==========

    def add_chunk(self, corpus_id: int, document_id: int, chunk_index: int,
                  text: str, embedding: bytes,
                  page_start: Optional[int] = None,
                  page_end: Optional[int] = None) -> int:
        """Insert paired rows in rag_chunks_text and rag_chunks_vec. Vec rowid == text id (1:1)."""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO rag_chunks_text(corpus_id, document_id, chunk_index, text, "
            "page_start, page_end) VALUES (?,?,?,?,?,?)",
            (corpus_id, document_id, chunk_index, text, page_start, page_end),
        )
        chunk_id = cur.lastrowid
        if self.vec_available:
            cur.execute(
                "INSERT INTO rag_chunks_vec(rowid, corpus_id, embedding) VALUES (?,?,?)",
                (chunk_id, corpus_id, embedding),
            )
        self.conn.commit()
        return chunk_id

    def vector_search(self, corpus_id: int, query_embedding: bytes,
                      k: int = 3) -> List[sqlite3.Row]:
        """Return top-k chunks for a query, scoped to corpus_id by partition key."""
        if not self.vec_available:
            return []
        cur = self.conn.cursor()
        cur.execute(
            "SELECT t.id, t.document_id, t.chunk_index, t.text, t.page_start, t.page_end, v.distance "
            "FROM rag_chunks_vec v "
            "JOIN rag_chunks_text t ON t.id = v.rowid "
            "WHERE v.corpus_id = ? AND v.embedding MATCH ? AND k = ? "
            "ORDER BY v.distance",
            (corpus_id, query_embedding, k),
        )
        return cur.fetchall()

    # ── Ordered memory helpers ──────────────────────────────────────────────

    def add_memory(self, user_id: int, event_type: str, content: str,
                   extracted_value: Optional[str] = None,
                   occurred_at: Optional[str] = None,
                   source: str = "voice") -> int:
        from datetime import datetime, timezone
        created_at = datetime.now(timezone.utc).isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO user_memories (user_id, event_type, content, extracted_value, "
            "occurred_at, created_at, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, event_type, content, extracted_value, occurred_at, created_at, source),
        )
        self.conn.commit()
        return cur.lastrowid

    def recall_memory_fts(self, user_id: int, query: str, limit: int = 5) -> List[sqlite3.Row]:
        """FTS5 search across user_memories for this user, newest-first."""
        cur = self.conn.cursor()
        # FTS5 content table — join on rowid to get occurred_at and created_at
        cur.execute(
            "SELECT m.id, m.event_type, m.content, m.extracted_value, "
            "m.occurred_at, m.created_at "
            "FROM user_memories_fts f "
            "JOIN user_memories m ON m.id = f.rowid "
            "WHERE f.content MATCH ? AND m.user_id = ? "
            "ORDER BY m.occurred_at DESC, m.created_at DESC "
            "LIMIT ?",
            (query, user_id, limit),
        )
        return cur.fetchall()
