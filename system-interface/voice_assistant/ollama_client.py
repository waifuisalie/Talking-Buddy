"""
Cliente Ollama para geração de respostas
Simplificado para integração com system-interface
"""

import requests
import json
import time
from typing import Optional, Generator
from .voice_config import VoiceConfig


class OllamaClient:
    """Cliente para comunicação com Ollama LLM"""
    
    def __init__(self, config: VoiceConfig):
        self.config = config
    
    def generate_response(self, prompt: str, system_prompt: Optional[str] = None, 
                         conversation_context: Optional[list] = None) -> Optional[str]:
        """
        Gera resposta completa (blocking mode)
        
        Args:
            prompt: Mensagem do usuário
            system_prompt: Prompt de sistema (opcional)
            conversation_context: Lista de mensagens anteriores [{"role": "user/assistant", "content": "..."}]
        
        Returns:
            Texto da resposta ou None em caso de erro
        """
        try:
            messages = self._build_messages(prompt, system_prompt, conversation_context)
            
            payload = {
                "model": self.config.ollama_model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.config.ollama_temperature,
                    "num_predict": self.config.ollama_max_tokens
                }
            }
            
            print(f"🤖 [Ollama] Gerando resposta com {self.config.ollama_model}...")
            print(f"⏱️  [Ollama] Timeout configurado: {self.config.ollama_timeout}s")
            
            start_time = time.time()
            
            response = requests.post(
                self.config.ollama_url,
                json=payload,
                timeout=self.config.ollama_timeout
            )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result.get("message", {}).get("content", "").strip()
                
                if ai_response:
                    print(f"✅ [Ollama] Resposta gerada em {elapsed:.1f}s ({len(ai_response)} chars)")
                    return self._clean_response(ai_response)
                else:
                    print(f"⚠️ [Ollama] Resposta vazia após {elapsed:.1f}s")
                    return None
            else:
                print(f"❌ [Ollama] Erro HTTP {response.status_code} após {elapsed:.1f}s: {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"❌ [Ollama] Timeout após {self.config.ollama_timeout}s")
            print("💡 Dica: Ollama pode estar lento. Aguarde alguns segundos e tente novamente.")
            return None
        except requests.exceptions.ConnectionError:
            print("❌ [Ollama] Erro de conexão - Ollama está rodando?")
            print("💡 Dica: Execute 'sudo systemctl status ollama' para verificar")
            return None
        except Exception as e:
            print(f"❌ [Ollama] Erro: {e}")
            return None
    
    def generate_streaming_response(self, prompt: str, system_prompt: Optional[str] = None,
                                   conversation_context: Optional[list] = None,
                                   model: Optional[str] = None) -> Generator[str, None, None]:
        """
        Gera resposta em streaming (yields chunks)

        Args:
            prompt: Mensagem do usuário
            system_prompt: Prompt de sistema (opcional)
            conversation_context: Lista de mensagens anteriores
            model: Override model name (optional, defaults to config)

        Yields:
            Chunks de texto conforme são gerados
        """
        try:
            messages = self._build_messages(prompt, system_prompt, conversation_context)

            use_model = model or self.config.ollama_model

            payload = {
                "model": use_model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": self.config.ollama_temperature,
                    "num_predict": self.config.ollama_max_tokens
                }
            }

            print(f"🤖 [Ollama] Streaming com {use_model}...")
            
            response = requests.post(
                self.config.ollama_url,
                json=payload,
                timeout=self.config.ollama_timeout,
                stream=True
            )
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if 'message' in data and 'content' in data['message']:
                            chunk = data['message']['content']
                            if chunk:
                                yield chunk
                        
                        if data.get('done', False):
                            break
            else:
                print(f"❌ [Ollama] Erro HTTP {response.status_code}")
                yield ""
                
        except Exception as e:
            print(f"❌ [Ollama] Erro no streaming: {e}")
            yield ""
    
    def _build_messages(self, user_input: str, system_prompt: Optional[str] = None,
                       conversation_context: Optional[list] = None) -> list:
        """Constrói array de mensagens para Ollama"""
        messages = []
        
        # System prompt
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        
        # Contexto de conversa
        if conversation_context:
            messages.extend(conversation_context)
        
        # Mensagem atual do usuário
        messages.append({"role": "user", "content": user_input})
        
        return messages
    
    def _clean_response(self, response: str) -> str:
        """Limpa resposta da IA"""
        response = response.strip()
        response = " ".join(response.split())  # Normaliza espaços
        
        # Remove reticências excessivas
        if response.endswith(("...", "…")):
            response = response[:-3].strip()
        
        return response
    
    def is_available(self) -> bool:
        """Verifica se Ollama está disponível"""
        try:
            response = requests.get(
                self.config.ollama_url.replace('/api/chat', '/api/tags'),
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def warmup(self) -> bool:
        """Pré-carrega modelo na memória para respostas mais rápidas"""
        try:
            print(f"🔥 [Ollama] Pré-carregando modelo {self.config.ollama_model}...")
            start_time = time.time()
            
            # Envia uma pergunta simples para forçar carregamento do modelo
            payload = {
                "model": self.config.ollama_model,
                "messages": [{"role": "user", "content": "OK"}],
                "stream": False,
                "options": {"num_predict": 5}  # Apenas 5 tokens para warmup
            }
            
            response = requests.post(
                self.config.ollama_url,
                json=payload,
                timeout=120  # Primeira carga pode ser lenta
            )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                print(f"✅ [Ollama] Modelo pré-carregado em {elapsed:.1f}s")
                print("💡 Próximas respostas serão mais rápidas (modelo na RAM)")
                return True
            else:
                print(f"⚠️  [Ollama] Warmup falhou: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"⚠️  [Ollama] Erro no warmup: {e}")
            return False
