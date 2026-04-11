"""
Cliente Piper TTS para síntese de voz
Simplificado para integração com system-interface
"""

import subprocess
import time
import re
from pathlib import Path
from typing import Optional
from .voice_config import VoiceConfig


class TTSClient:
    """Cliente para Text-to-Speech com Piper"""
    
    def __init__(self, config: VoiceConfig):
        self.config = config
        self.temp_files = []
    
    def synthesize(self, text: str, output_filename: Optional[str] = None) -> Optional[str]:
        """
        Sintetiza texto em arquivo de áudio WAV
        
        Args:
            text: Texto para sintetizar
            output_filename: Nome do arquivo de saída (sem path, só nome)
        
        Returns:
            Path relativo do arquivo gerado (para servir via Flask) ou None
        """
        try:
            # Limpa texto
            clean_text = self._clean_text_for_tts(text)
            
            if not clean_text.strip():
                print("⚠️ [TTS] Texto vazio após limpeza")
                return None
            
            # Gera nome do arquivo
            if output_filename is None:
                timestamp = int(time.time() * 1000)
                output_filename = f"tts_{timestamp}.wav"
            
            # Path completo para salvar
            output_path = Path(self.config.audio_static_dir) / output_filename
            
            # Garante que diretório existe
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Path do modelo
            model_path = Path(self.config.piper_model_path) / self.config.piper_model
            
            if not model_path.exists():
                print(f"❌ [TTS] Modelo não encontrado: {model_path}")
                return None
            
            cmd = [
                self.config.piper_binary,
                "--model", str(model_path),
                "--output_file", str(output_path)
            ]
            
            print(f"🔊 [TTS] Sintetizando: '{clean_text[:60]}{'...' if len(clean_text) > 60 else ''}'")
            print(f"📝 [TTS] Tamanho do texto: {len(clean_text)} caracteres")
            
            # Calcula timeout dinâmico baseado no tamanho do texto
            # ~0.15s por caractere + margem de segurança
            estimated_time = len(clean_text) * 0.15
            timeout = max(30, min(120, estimated_time * 1.5))  # Mínimo 30s, máximo 120s
            
            print(f"⏱️  [TTS] Timeout calculado: {timeout:.0f}s")
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            start_time = time.time()
            stdout, stderr = process.communicate(input=clean_text, timeout=timeout)
            elapsed = time.time() - start_time
            
            if process.returncode == 0 and output_path.exists():
                # Normalizar volume do áudio para consistência com sons do sistema
                self._normalize_audio(output_path)
                
                # Retorna path relativo para servir via Flask
                relative_path = f"audio/{output_filename}"
                self.temp_files.append(str(output_path))
                
                # Calcula duração aproximada (para sincronização)
                duration = self._estimate_audio_duration(clean_text)
                
                print(f"✅ [TTS] Áudio gerado em {elapsed:.1f}s: {relative_path} (~{duration:.1f}s de áudio)")
                return relative_path
            else:
                print(f"❌ [TTS] Falha ao gerar áudio (code {process.returncode})")
                if stderr:
                    print(f"    Stderr: {stderr[:200]}")
                return None
                
        except subprocess.TimeoutExpired:
            print("❌ [TTS] Timeout ao gerar áudio")
            return None
        except Exception as e:
            print(f"❌ [TTS] Erro: {e}")
            return None
    
    def _normalize_audio(self, audio_path: Path, target_db: float = -6.0):
        """
        Normaliza volume do áudio TTS para consistência com sons do sistema.
        
        Args:
            audio_path: Caminho do arquivo de áudio
            target_db: Nível de pico alvo em dB (padrão: -6dB)
        """
        try:
            # Usar sox para normalização rápida
            temp_path = audio_path.with_suffix('.norm.wav')
            result = subprocess.run(
                ['sox', str(audio_path), str(temp_path), 'norm', str(target_db)],
                capture_output=True,
                timeout=10
            )
            
            if result.returncode == 0 and temp_path.exists():
                # Substituir arquivo original
                temp_path.replace(audio_path)
            else:
                # Se falhar, manter original
                if temp_path.exists():
                    temp_path.unlink()
                    
        except Exception as e:
            print(f"⚠️  [TTS] Normalização falhou (ignorando): {e}")
    
    def _clean_text_for_tts(self, text: str) -> str:
        """Limpa texto para melhor pronúncia no TTS"""
        # Remove markdown
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # **bold**
        text = re.sub(r'\*(.*?)\*', r'\1', text)      # *italic*
        text = re.sub(r'`(.*?)`', r'\1', text)        # `code`
        
        # Remove URLs
        text = re.sub(r'http[s]?://\S+', '', text)
        
        # Remove caracteres especiais (mantém pontuação básica)
        text = re.sub(r'[^\w\s.,!?;:()\"\'-]', '', text)
        
        # Normaliza espaços
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Garante pontuação final
        if text and not text.endswith(('.', '!', '?')):
            text += '.'
        
        return text
    
    def _estimate_audio_duration(self, text: str) -> float:
        """
        Estima duração do áudio em segundos
        Baseado em ~150 palavras por minuto (velocidade média de fala)
        """
        words = len(text.split())
        duration = (words / 150.0) * 60.0  # palavras / (palavras/min) * 60s
        return max(duration, 1.0)  # Mínimo 1 segundo
    
    def is_available(self) -> bool:
        """Verifica se Piper está disponível"""
        try:
            if not Path(self.config.piper_binary).exists():
                print(f"❌ [TTS] Binary não encontrado: {self.config.piper_binary}")
                return False
            
            model_path = Path(self.config.piper_model_path) / self.config.piper_model
            if not model_path.exists():
                print(f"❌ [TTS] Modelo não encontrado: {model_path}")
                return False
            
            return True
        except Exception as e:
            print(f"❌ [TTS] Erro ao verificar disponibilidade: {e}")
            return False
    
    def warmup(self) -> bool:
        """Pré-testa o Piper TTS para garantir que está funcionando"""
        try:
            print(f"🔥 [TTS] Testando Piper TTS...")
            
            # Gera áudio de teste simples
            test_audio = self.synthesize("Teste", output_filename="warmup_test.wav")
            
            if test_audio:
                # Remove arquivo de teste
                test_path = Path(self.config.audio_static_dir) / "warmup_test.wav"
                if test_path.exists():
                    test_path.unlink()
                
                print("✅ [TTS] Piper funcionando corretamente")
                return True
            else:
                print("⚠️  [TTS] Piper não respondeu ao teste")
                return False
                
        except Exception as e:
            print(f"⚠️  [TTS] Erro no warmup: {e}")
            return False
    
    def cleanup_temp_files(self, keep_recent: int = 10):
        """
        Limpa arquivos temporários antigos
        
        Args:
            keep_recent: Número de arquivos recentes para manter
        """
        try:
            audio_dir = Path(self.config.audio_static_dir)
            if not audio_dir.exists():
                return
            
            # Lista todos os arquivos de áudio
            audio_files = sorted(
                audio_dir.glob("tts_*.wav"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            # Remove arquivos antigos (mantém os N mais recentes)
            removed = 0
            for audio_file in audio_files[keep_recent:]:
                try:
                    audio_file.unlink()
                    removed += 1
                except Exception as e:
                    print(f"⚠️ [TTS] Erro ao remover {audio_file}: {e}")
            
            if removed > 0:
                print(f"🧹 [TTS] Removidos {removed} arquivos antigos")
                
        except Exception as e:
            print(f"❌ [TTS] Erro na limpeza: {e}")
