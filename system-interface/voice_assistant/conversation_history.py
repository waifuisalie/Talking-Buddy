"""
Gerenciador de histórico de conversas
Salva e recupera conversas do banco SQLite
"""

import json
from typing import List, Dict, Optional
from datetime import datetime


class ConversationHistory:
    """Gerencia histórico de conversas no banco de dados"""
    
    def __init__(self, db_connection):
        """
        Args:
            db_connection: Instância de Database (database.py)
        """
        self.db = db_connection
    
    def add_message(self, user_id: int, role: str, content: str, 
                   metadata: Optional[dict] = None) -> int:
        """
        Adiciona mensagem ao histórico
        
        Args:
            user_id: ID do usuário
            role: "user" ou "assistant"
            content: Texto da mensagem
            metadata: Dados extras (audio_url, duration, etc)
        
        Returns:
            ID da mensagem inserida
        """
        metadata_json = json.dumps(metadata) if metadata else "{}"
        
        message_id = self.db.add_conversation_message(
            user_id=user_id,
            role=role,
            content=content,
            metadata=metadata_json
        )
        
        return message_id
    
    def get_recent_messages(self, user_id: int, limit: int = 10) -> List[Dict]:
        """
        Recupera mensagens recentes de um usuário
        
        Args:
            user_id: ID do usuário
            limit: Número máximo de mensagens (padrão: 10)
        
        Returns:
            Lista de mensagens formatadas para Ollama
            [{"role": "user/assistant", "content": "..."}, ...]
        """
        rows = self.db.get_conversation_history(user_id, limit)
        
        messages = []
        for row in rows:
            messages.append({
                "role": row["role"],
                "content": row["content"]
            })
        
        return messages
    
    def get_full_history(self, user_id: int, limit: int = 50) -> List[Dict]:
        """
        Recupera histórico completo com metadata
        
        Returns:
            Lista completa com id, role, content, metadata, timestamp
        """
        rows = self.db.get_conversation_history(user_id, limit)
        
        history = []
        for row in rows:
            metadata = {}
            try:
                if row["metadata"]:
                    metadata = json.loads(row["metadata"])
            except:
                pass
            
            history.append({
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "metadata": metadata,
                "timestamp": row["created_at"]
            })
        
        return history
    
    def clear_history(self, user_id: int, keep_last: int = 0) -> int:
        """
        Limpa histórico de um usuário
        
        Args:
            user_id: ID do usuário
            keep_last: Número de mensagens recentes para manter
        
        Returns:
            Número de mensagens removidas
        """
        return self.db.clear_conversation_history(user_id, keep_last)
    
    def get_context_for_llm(self, user_id: int, max_messages: int = 8) -> List[Dict]:
        """
        Retorna contexto formatado para enviar ao LLM
        Limita para evitar exceder contexto do modelo
        
        Args:
            user_id: ID do usuário
            max_messages: Máximo de mensagens a incluir
        
        Returns:
            Lista de mensagens no formato Ollama
        """
        return self.get_recent_messages(user_id, limit=max_messages)
    
    def export_to_json(self, user_id: int, limit: int = 100) -> str:
        """
        Exporta histórico para JSON
        
        Returns:
            String JSON formatada
        """
        history = self.get_full_history(user_id, limit)
        return json.dumps(history, indent=2, ensure_ascii=False)
