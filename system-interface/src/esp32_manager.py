#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32 Wake Word Manager
Gerencia conexão serial com ESP32-S3 para detecção de wake word.
Auto-detecta porta USB e reconecta automaticamente se desconectado.
"""

import serial
import serial.tools.list_ports
import threading
import time
from typing import Optional, Callable
from datetime import datetime


def find_esp32_port() -> Optional[str]:
    """
    Varre portas USB/Serial e identifica ESP32 automaticamente.
    
    Métodos de detecção:
    1. VID:PID conhecido (1A86:55D3 - CH340 comum em ESP32)
    2. Padrões de mensagem característicos do ESP32
    
    Returns:
        str: Caminho da porta (ex: '/dev/ttyACM0') ou None se não encontrado
    """
    ports = serial.tools.list_ports.comports()
    
    if not ports:
        return None
    
    for port in ports:
        # Método 1: Identificar por VID:PID
        if '1A86:55D3' in port.hwid:
            print(f"✅ ESP32 encontrado por VID:PID em {port.device}")
            return port.device
        
        # Método 2: Tentar abrir e verificar mensagens características
        # Procura por padrões como "ESP32", "Marvin", "Wake Word"
        try:
            ser = serial.Serial(port.device, 115200, timeout=1)
            time.sleep(0.5)
            
            # Ler algumas linhas para identificar
            attempts = 0
            while attempts < 5 and ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if any(keyword in line for keyword in ['Marvin', 'ESP32', 'Wake Word', 'heap']):
                        print(f"✅ ESP32 encontrado por mensagem em {port.device}: {line}")
                        ser.close()
                        return port.device
                except:
                    pass
                attempts += 1
            
            ser.close()
        except (serial.SerialException, PermissionError):
            continue
    
    return None


class ESP32Manager:
    """
    Gerenciador de conexão com ESP32 para wake word detection.
    
    Funcionalidades:
    - Auto-detecção de porta USB
    - Reconexão automática
    - Thread-safe para uso com Flask
    - Callback quando wake word detectado
    """
    
    def __init__(self, baud_rate: int = 115200, reconnect_interval: int = 5, 
                 debounce_time: float = 2.0):
        """
        Inicializa gerenciador ESP32.
        
        Args:
            baud_rate: Taxa de comunicação serial (padrão: 115200)
            reconnect_interval: Segundos entre tentativas de reconexão
            debounce_time: Segundos mínimos entre wake words (evita duplicatas)
        """
        self.baud_rate = baud_rate
        self.reconnect_interval = reconnect_interval
        self.debounce_time = debounce_time
        
        # Estado da conexão
        self.port: Optional[str] = None
        self.serial: Optional[serial.Serial] = None
        self.connected = False
        
        # Thread de monitoramento
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # Wake word detection (thread-safe)
        self._lock = threading.Lock()
        self._wake_detected = False
        self._last_wake_time = 0
        
        # Callback opcional
        self._wake_callback: Optional[Callable] = None
        
        # Estatísticas
        self.wake_count = 0
        self.connection_count = 0
        self.last_message_time: Optional[datetime] = None
    
    def register_wake_callback(self, callback: Callable):
        """
        Registra função callback para quando wake word for detectado.
        
        Args:
            callback: Função a ser chamada (sem argumentos)
        """
        self._wake_callback = callback
    
    def start(self):
        """Inicia thread de monitoramento do ESP32"""
        if self.running:
            print("⚠️  ESP32Manager já está rodando")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True, name="ESP32Monitor")
        self.thread.start()
        print("🚀 ESP32Manager iniciado")
    
    def stop(self):
        """Para thread de monitoramento e fecha conexão serial"""
        if not self.running:
            return
        
        print("🛑 Parando ESP32Manager...")
        self.running = False
        
        # Fechar conexão serial
        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except:
                pass
        
        # Aguardar thread terminar
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        
        print("✅ ESP32Manager parado")
    
    def _monitor_loop(self):
        """Loop principal de monitoramento (executa em thread separada)"""
        print("👂 ESP32 monitor thread iniciada")
        
        while self.running:
            # Se não conectado, tentar encontrar e conectar
            if not self.serial or not self.serial.is_open:
                self._attempt_connection()
                if not self.connected:
                    time.sleep(self.reconnect_interval)
                    continue
            
            # Ler mensagens do ESP32
            try:
                if self.serial.in_waiting > 0:
                    line = self.serial.readline().decode('utf-8', errors='ignore').strip()
                    
                    if line:
                        self.last_message_time = datetime.now()
                        
                        # Verificar wake word
                        if "WAKE_WORD_DETECTED" in line:
                            self._handle_wake_word()
                        else:
                            # Log outras mensagens para debug (opcional)
                            # print(f"[ESP32] {line}")
                            pass
                
                # Pequeno delay para não sobrecarregar CPU
                time.sleep(0.01)
                
            except serial.SerialException as e:
                print(f"❌ Erro de conexão serial: {e}")
                self._disconnect()
            except Exception as e:
                print(f"❌ Erro inesperado no monitor: {e}")
                time.sleep(1)
    
    def _attempt_connection(self):
        """Tenta conectar ao ESP32"""
        # Auto-detectar porta
        self.port = find_esp32_port()
        
        if not self.port:
            if self.connection_count == 0:  # Só mostrar na primeira tentativa
                print("⏳ ESP32 não encontrado. Tentando reconectar...")
            return
        
        # Tentar abrir porta serial
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=1
            )
            self.connected = True
            self.connection_count += 1
            print(f"✅ ESP32 conectado em {self.port} (conexão #{self.connection_count})")
            
        except serial.SerialException as e:
            print(f"❌ Erro ao abrir {self.port}: {e}")
            self.serial = None
            self.connected = False
        except Exception as e:
            print(f"❌ Erro inesperado ao conectar: {e}")
            self.serial = None
            self.connected = False
    
    def _disconnect(self):
        """Marca como desconectado e fecha porta serial"""
        if self.connected:
            print(f"🔌 ESP32 desconectado de {self.port}")
        
        self.connected = False
        if self.serial:
            try:
                self.serial.close()
            except:
                pass
            self.serial = None
    
    def _handle_wake_word(self):
        """Processa detecção de wake word com debounce"""
        current_time = time.time()
        
        # Debounce - ignorar se muito recente
        if current_time - self._last_wake_time < self.debounce_time:
            print(f"⚠️  Wake word ignorado (debounce: {current_time - self._last_wake_time:.1f}s)")
            return
        
        # Atualizar estado (thread-safe)
        with self._lock:
            self._wake_detected = True
            self._last_wake_time = current_time
            self.wake_count += 1
        
        print(f"🎙️  Wake word detectado! (total: {self.wake_count})")
        
        # Chamar callback se registrado
        if self._wake_callback:
            try:
                self._wake_callback()
            except Exception as e:
                print(f"❌ Erro no callback de wake word: {e}")
    
    def check_and_clear_wake(self) -> bool:
        """
        Verifica se wake word foi detectado e limpa flag (consumo único).
        Thread-safe para uso em rotas Flask.
        
        Returns:
            bool: True se wake word detectado desde última verificação
        """
        with self._lock:
            if self._wake_detected:
                self._wake_detected = False
                return True
        return False
    
    def is_connected(self) -> bool:
        """Retorna se ESP32 está conectado"""
        return self.connected
    
    def get_status(self) -> dict:
        """
        Retorna status completo do ESP32Manager.
        
        Returns:
            dict: Informações de status e estatísticas
        """
        return {
            "connected": self.connected,
            "port": self.port,
            "wake_count": self.wake_count,
            "connection_count": self.connection_count,
            "last_message_time": self.last_message_time.isoformat() if self.last_message_time else None,
            "running": self.running
        }


# Teste standalone
if __name__ == "__main__":
    print("=" * 60)
    print("Teste ESP32Manager")
    print("=" * 60)
    
    def on_wake():
        print("🔔 CALLBACK: Wake word detectado!")
    
    manager = ESP32Manager()
    manager.register_wake_callback(on_wake)
    manager.start()
    
    print("\nMonitorando ESP32... (Ctrl+C para parar)")
    print("Diga 'Marvin' próximo ao ESP32 para testar\n")
    
    try:
        while True:
            time.sleep(1)
            # Mostrar status a cada 10 segundos
            if int(time.time()) % 10 == 0:
                status = manager.get_status()
                print(f"\nStatus: Conectado={status['connected']}, "
                      f"Porta={status['port']}, "
                      f"Wake Count={status['wake_count']}")
    except KeyboardInterrupt:
        print("\n\nEncerrando...")
        manager.stop()
        print("✅ Teste finalizado")
