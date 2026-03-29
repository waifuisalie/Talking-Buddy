#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RFID Manager - Processo contínuo de leitura RFID

NOTA: Este processo roda INDEFINIDAMENTE enquanto o servidor estiver ativo.
Não possui timeout automático - isto é intencional:
  - Usuário pode ficar minutos/horas sem passar cartão (uso normal)
  - killall_rfid_processes() ao iniciar servidor previne processos órfãos
  - Processo encerra apenas via SIGTERM/SIGINT (parada do servidor)
"""

import MFRC522
import signal
import sys
import time
import os

continue_reading = True

def end_read(sig, frame):
    global continue_reading
    print("\n🛑 Sinal recebido - encerrando...", flush=True)
    continue_reading = False

# Registra handlers para encerramento gracioso
signal.signal(signal.SIGINT, end_read)
signal.signal(signal.SIGTERM, end_read)

# Arquivo de saída
script_dir = os.path.dirname(os.path.abspath(__file__))
output_file = os.path.join(script_dir, '../last_rfid.txt')
output_file = os.path.abspath(output_file)

# Limpa arquivo ao iniciar
try:
    with open(output_file, 'w') as f:
        f.write('')
    print(f"📄 Arquivo limpo: {output_file}", flush=True)
except:
    pass

print("🔧 Inicializando leitor RFID...", flush=True)
reader = MFRC522.MFRC522()
print("✅ Pronto - Aguardando cartões (modo contínuo 24/7)", flush=True)

last_uid = None
last_time = 0

# Loop principal - roda indefinidamente até SIGTERM/SIGINT
while continue_reading:
    (status, TagType) = reader.MFRC522_Request(reader.PICC_REQIDL)

    if status == reader.MI_OK:
        (status, uid) = reader.MFRC522_Anticoll1()
        if status == reader.MI_OK:
            # Converte UID para hex
            uid_num = 0
            for i in range(0, 5):
                uid_num = uid_num * 256 + uid[i]
            uid_hex = format(uid_num, 'X')
            
            # Debounce de 1s - evita leituras duplicadas
            current_time = time.time()
            if uid_hex != last_uid or (current_time - last_time) > 1.0:
                last_uid = uid_hex
                last_time = current_time
                
                # Salva UID no arquivo
                with open(output_file, 'w') as f:
                    f.write(uid_hex)
                
                print("=" * 50, flush=True)
                print(f"✅ CARTÃO DETECTADO: {uid_hex}", flush=True)
                print("=" * 50, flush=True)
            
            time.sleep(0.1)
    else:
        # Sleep curto para não sobrecarregar CPU
        time.sleep(0.05)

print("✅ Processo encerrado", flush=True)

