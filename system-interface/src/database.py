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
            "SELECT id, name, rfid, response_style, persona_gender, language, created_at "
            "FROM users ORDER BY name COLLATE NOCASE"
        )
        return cur.fetchall()

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        """Busca um usuário por ID"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, rfid, response_style, persona_gender, language, created_at "
            "FROM users WHERE id=?",
            (user_id,),
        )
        return cur.fetchone()
    
    def get_user_by_rfid(self, rfid: str) -> Optional[sqlite3.Row]:
        """Busca um usuário por RFID"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, rfid, response_style, persona_gender, language, created_at "
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
    
    def get_user_by_rfid(self, rfid: str) -> Optional[sqlite3.Row]:
        """Busca um usuário pelo RFID"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, rfid, response_style, persona_gender, language, created_at "
            "FROM users WHERE rfid=?",
            (rfid,),
        )
        return cur.fetchone()

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
