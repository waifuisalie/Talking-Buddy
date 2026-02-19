"""
Player de áudio para hardware (Raspberry Pi)
Reproduz áudio via ALSA (P2 ou pinout)
"""

import pygame
import os
import time
from pathlib import Path
from typing import Optional, Callable
from .voice_config import VoiceConfig


class HardwareAudioPlayer:
    """Player de áudio para reprodução em hardware físico"""
    
    def __init__(self, config: VoiceConfig):
        self.config = config
        self.is_playing = False
        self._use_aplay_fallback = False  # Flag para usar aplay se pygame falhar
        self._initialize_pygame()
    
    def _initialize_pygame(self):
        """Inicializa pygame mixer com configurações ALSA"""
        try:
            # Se já inicializado, não faz nada
            if pygame.mixer.get_init() is not None:
                print(f"🔊 [AudioPlayer] Já inicializado (device: {self.config.audio_device})")
                return
            
            # Configura ALSA como backend
            os.environ['SDL_AUDIODRIVER'] = 'alsa'
            
            # Define dispositivo de áudio
            if self.config.audio_device != 'default':
                os.environ['AUDIODEV'] = self.config.audio_device
            
            # Inicializa mixer
            pygame.mixer.init(
                frequency=self.config.audio_sample_rate,
                size=-16,
                channels=2,
                buffer=2048  # Aumentado de 1024 para evitar corte no início
            )
            
            print(f"🔊 [AudioPlayer] Inicializado (device: {self.config.audio_device})")
            
        except Exception as e:
            print(f"❌ [AudioPlayer] Erro ao inicializar pygame: {e}")
            print("⚠️  [AudioPlayer] Tentando usar aplay como fallback...")
            self._use_aplay_fallback = True
    
    def _play_with_aplay(self, audio_file: str) -> bool:
        """Reproduz áudio usando aplay (fallback)"""
        try:
            import subprocess
            
            # -B para buffer maior e evitar cortes
            cmd = ['aplay', '-D', self.config.audio_device, '-B', '200000', audio_file]
            print(f"🔊 [AudioPlayer/aplay] Reproduzindo: {Path(audio_file).name}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print("✅ [AudioPlayer/aplay] Reprodução finalizada")
                return True
            else:
                print(f"❌ [AudioPlayer/aplay] Erro: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ [AudioPlayer/aplay] Erro: {e}")
            return False
    
    def play(self, audio_file: str, blocking: bool = True,
             on_start: Optional[Callable] = None,
             on_finish: Optional[Callable] = None) -> bool:
        """
        Reproduz arquivo de áudio
        
        Args:
            audio_file: Path do arquivo WAV
            blocking: Se True, aguarda fim da reprodução
            on_start: Callback ao iniciar
            on_finish: Callback ao finalizar
        
        Returns:
            True se reproduziu com sucesso
        """
        try:
            if not Path(audio_file).exists():
                print(f"❌ [AudioPlayer] Arquivo não encontrado: {audio_file}")
                return False
            
            # Se pygame falhou, usa aplay
            if self._use_aplay_fallback:
                if on_start:
                    on_start()
                result = self._play_with_aplay(audio_file)
                if on_finish and result:
                    on_finish()
                return result
            
            # Para reprodução anterior
            if self.is_playing:
                self.stop()
            
            self.is_playing = True
            
            if on_start:
                on_start()
            
            print(f"🔊 [AudioPlayer] Reproduzindo: {Path(audio_file).name}")
            
            # Carrega e reproduz
            pygame.mixer.music.load(audio_file)
            
            # Pequeno delay para garantir que buffer seja preenchido
            time.sleep(0.05)  # 50ms - previne corte no início
            
            pygame.mixer.music.play()
            
            if blocking:
                # Aguarda fim da reprodução
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                
                self.is_playing = False
                
                if on_finish:
                    on_finish()
                
                print("✅ [AudioPlayer] Reprodução finalizada")
            
            return True
            
        except Exception as e:
            print(f"❌ [AudioPlayer] Erro ao reproduzir com pygame: {e}")
            print("🔄 [AudioPlayer] Tentando com aplay...")
            
            # Tenta aplay como fallback
            self._use_aplay_fallback = True
            if on_start:
                on_start()
            result = self._play_with_aplay(audio_file)
            if on_finish and result:
                on_finish()
            
            self.is_playing = False
            return result
    
    def stop(self):
        """Para reprodução atual"""
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            self.is_playing = False
        except Exception as e:
            print(f"❌ [AudioPlayer] Erro ao parar: {e}")
    
    def get_volume(self) -> float:
        """Retorna volume atual (0.0 a 1.0)"""
        try:
            return pygame.mixer.music.get_volume()
        except:
            return 1.0
    
    def set_volume(self, volume: float):
        """
        Define volume (0.0 a 1.0)
        
        Args:
            volume: Valor entre 0.0 (mudo) e 1.0 (máximo)
        """
        try:
            volume = max(0.0, min(1.0, volume))
            pygame.mixer.music.set_volume(volume)
            print(f"🔊 [AudioPlayer] Volume: {int(volume * 100)}%")
        except Exception as e:
            print(f"❌ [AudioPlayer] Erro ao ajustar volume: {e}")
    
    def is_available(self) -> bool:
        """Verifica se player está disponível"""
        # Se temos aplay como fallback, sempre disponível
        if self._use_aplay_fallback:
            return True
        
        # Verifica pygame
        try:
            return pygame.mixer.get_init() is not None
        except:
            return False
