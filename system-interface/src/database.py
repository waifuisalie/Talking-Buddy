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

# Schema do banco de dados
SCHEMA_SQL = """
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

CREATE INDEX IF NOT EXISTS idx_user_data_user_id ON user_data(user_id);
CREATE INDEX IF NOT EXISTS idx_users_name ON users(name);
CREATE INDEX IF NOT EXISTS idx_users_rfid ON users(rfid);
CREATE INDEX IF NOT EXISTS idx_conversation_user_id ON conversation_history(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_created_at ON conversation_history(created_at);

CREATE TABLE IF NOT EXISTS rag_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  source_file TEXT NOT NULL,
  chunk_count INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL,
  chunk_index INTEGER NOT NULL,
  chunk_text TEXT NOT NULL,
  embedding BLOB NOT NULL,
  FOREIGN KEY(document_id) REFERENCES rag_documents(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS user_facts_fts USING fts5(
  topic, content, content=user_data, content_rowid=id
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
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()
        # Migration: add specialization_id to existing databases
        try:
            self.conn.execute(
                "ALTER TABLE users ADD COLUMN specialization_id INTEGER "
                "REFERENCES rag_documents(id)"
            )
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

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
                 persona_gender: str, language: str) -> int:
        """
        Adiciona um novo usuário
        Retorna o ID do usuário criado
        """
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO users(name, rfid, response_style, persona_gender, language, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (name, rfid, response_style, persona_gender, language, now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_user(self, user_id: int, name: str, rfid: str,
                    response_style: str, persona_gender: str, language: str) -> None:
        """Atualiza dados de um usuário existente"""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE users SET name=?, rfid=?, response_style=?, persona_gender=?, language=? WHERE id=?",
            (name, rfid, response_style, persona_gender, language, user_id),
        )
        self.conn.commit()

    def set_user_specialization(self, user_id: int, specialization_id: Optional[int]) -> None:
        """Define ou remove a especialização RAG de um usuário"""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE users SET specialization_id=? WHERE id=?",
            (specialization_id, user_id),
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

    # ========== PERSONAL FACTS (memory) ==========

    def store_fact(self, user_id: int, topic: str, content: str) -> int:
        """Armazena um fato pessoal do usuário e atualiza o índice FTS5"""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO user_data(user_id, key, value, created_at) VALUES (?,?,?,?)",
            (user_id, topic, content, now_iso()),
        )
        row_id = cur.lastrowid
        # Manually sync FTS index (content table trigger)
        cur.execute(
            "INSERT INTO user_facts_fts(rowid, topic, content) VALUES (?,?,?)",
            (row_id, topic, content),
        )
        self.conn.commit()
        return row_id

    def search_facts(self, user_id: int, query: str, limit: int = 5) -> List[dict]:
        """Busca fatos pessoais do usuário via FTS5"""
        try:
            cur = self.conn.cursor()
            # FTS5 search scoped to user via JOIN
            cur.execute(
                """
                SELECT ud.id, ud.key, ud.value, ud.created_at
                FROM user_data ud
                JOIN user_facts_fts fts ON fts.rowid = ud.id
                WHERE ud.user_id = ?
                  AND ud.key LIKE 'fato%'
                  AND user_facts_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (user_id, query, limit),
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    # ========== RAG DOCUMENTS ==========

    def create_rag_document(self, name: str, source_file: str) -> int:
        """Cria um novo documento RAG e retorna seu ID"""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO rag_documents(name, source_file, chunk_count, created_at) VALUES (?,?,0,?)",
            (name, source_file, now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid

    def delete_rag_document(self, doc_id: int) -> None:
        """Remove documento RAG e seus chunks (CASCADE)"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM rag_documents WHERE id=?", (doc_id,))
        self.conn.commit()

    def list_rag_documents(self) -> List[dict]:
        """Lista todos os documentos RAG disponíveis"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, source_file, chunk_count, created_at FROM rag_documents ORDER BY name COLLATE NOCASE"
        )
        return [dict(r) for r in cur.fetchall()]

    def store_rag_chunk(self, document_id: int, chunk_index: int,
                        chunk_text: str, embedding_bytes: bytes) -> None:
        """Armazena um chunk com seu embedding"""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO rag_chunks(document_id, chunk_index, chunk_text, embedding) VALUES (?,?,?,?)",
            (document_id, chunk_index, chunk_text, embedding_bytes),
        )
        self.conn.commit()

    def get_rag_chunks(self, document_id: int) -> List[dict]:
        """Retorna todos os chunks de um documento"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, chunk_index, chunk_text, embedding FROM rag_chunks WHERE document_id=? ORDER BY chunk_index",
            (document_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def update_rag_document_chunk_count(self, doc_id: int, count: int) -> None:
        """Atualiza o número de chunks de um documento"""
        cur = self.conn.cursor()
        cur.execute("UPDATE rag_documents SET chunk_count=? WHERE id=?", (count, doc_id))
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
            "FROM conversation_history "
            "WHERE user_id=? "
            "ORDER BY created_at ASC "
            "LIMIT ?",
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
