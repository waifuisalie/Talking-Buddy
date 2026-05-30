#!/bin/bash
# TalkingBuddy - Sistema Integrado de Cadastro e Voz
# Script de inicialização completo

set -e  # Exit on error

# Cores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}    TALKINGBUDDY - Sistema Integrado de Cadastro e Voz${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# ============================================================================
# 1. VERIFICAÇÕES PRÉ-INICIALIZAÇÃO
# ============================================================================
echo -e "${YELLOW}[1/8]${NC} Verificando pré-requisitos..."

# Verificar Python3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 não encontrado.${NC}"
    echo "   Instale com: sudo apt install python3"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python 3 encontrado"

# Verificar Ollama
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}❌ Ollama não encontrado.${NC}"
    echo "   Execute o setup primeiro: cd ../rpi5-chatbot && bash setup.sh"
    exit 1
fi
echo -e "${GREEN}✓${NC} Ollama instalado"

# ============================================================================
# 2. INICIAR OLLAMA SERVICE
# ============================================================================
echo ""
echo -e "${YELLOW}[2/8]${NC} Verificando serviço Ollama..."

if ! systemctl is-active --quiet ollama 2>/dev/null; then
    echo "🔄 Iniciando serviço Ollama..."
    if ! sudo systemctl start ollama; then
        echo -e "${RED}❌ Falha ao iniciar Ollama${NC}"
        echo "   Verifique: sudo systemctl status ollama"
        exit 1
    fi
    
    # Aguardar Ollama ficar pronto
    echo "⏳ Aguardando Ollama inicializar..."
    for i in {1..30}; do
        if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} Ollama pronto!"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}❌ Ollama não respondeu em 30 segundos${NC}"
            exit 1
        fi
        sleep 1
    done
else
    echo -e "${GREEN}✓${NC} Ollama já está rodando"
fi

# Verificar modelo (accept base model or any personality model)
if ! ollama list | grep -qE "gemma3:1b|gemma3-ptbr|qwen2\.5.*-ptbr|llama3\.2.*-ptbr"; then
    echo -e "${YELLOW}⚠️  Nenhum modelo encontrado. Baixando gemma3:1b...${NC}"
    ollama pull gemma3:1b
fi

# Count personality models
PERSONALITY_COUNT=$(ollama list | grep -cE "(gemma3|qwen2\.5|llama3\.2).*-ptbr-" 2>/dev/null || echo "0")
if [ "$PERSONALITY_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓${NC} Modelo Ollama disponível ($PERSONALITY_COUNT personalidades)"
else
    echo -e "${GREEN}✓${NC} Modelo Ollama disponível (sem personalidades - usando modelo base)"
fi

# Aquecimento do Ollama: envia uma mensagem curta para carregar o modelo na RAM
# e aquecer o KV-cache. Sem isso, o primeiro pedido do usuário demora ~7-9s
# para o primeiro token; após este aquecimento, cai para ~3-5s.
OLLAMA_WARMUP_MODEL="${OLLAMA_MODEL:-gemma3:1b}"
echo "🔄 Aquecendo Ollama (carregando modelo $OLLAMA_WARMUP_MODEL na RAM)..."
WARMUP_START=$SECONDS
WARMUP_RESPONSE=$(curl -s --max-time 60 http://127.0.0.1:11434/api/chat \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"$OLLAMA_WARMUP_MODEL\",
        \"messages\": [{\"role\": \"user\", \"content\": \"Olá\"}],
        \"stream\": false,
        \"options\": {\"num_predict\": 1}
    }" 2>/dev/null)
WARMUP_SECS=$(( SECONDS - WARMUP_START ))

if echo "$WARMUP_RESPONSE" | grep -q '"message"'; then
    echo -e "${GREEN}✓${NC} Ollama aquecido em ${WARMUP_SECS}s — modelo $OLLAMA_WARMUP_MODEL na RAM"
else
    echo -e "${YELLOW}⚠️  Aquecimento do Ollama falhou (${WARMUP_SECS}s) — primeiro request pode ser lento${NC}"
    echo -e "   Resposta: $(echo "$WARMUP_RESPONSE" | head -c 120)"
fi

# Aquecimento do modelo de embedding (RAG + memória semântica).
# keep_alive=-1 instrui o Ollama a manter o modelo residente até desligar.
EMBED_WARMUP_MODEL="${EMBED_MODEL:-granite-embedding:278m}"
echo "🔄 Aquecendo embedding ($EMBED_WARMUP_MODEL, keep_alive=-1)..."
EMBED_WARMUP_START=$SECONDS
EMBED_WARMUP_RESPONSE=$(curl -s --max-time 60 http://127.0.0.1:11434/api/embed \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"$EMBED_WARMUP_MODEL\",
        \"input\": \"aquecimento\",
        \"keep_alive\": -1
    }" 2>/dev/null)
EMBED_WARMUP_SECS=$(( SECONDS - EMBED_WARMUP_START ))

if echo "$EMBED_WARMUP_RESPONSE" | grep -q '"embeddings"'; then
    echo -e "${GREEN}✓${NC} Embedding aquecido em ${EMBED_WARMUP_SECS}s — $EMBED_WARMUP_MODEL na RAM"
else
    echo -e "${YELLOW}⚠️  Aquecimento do embedding falhou (${EMBED_WARMUP_SECS}s) — primeiro FACT_RECALL/RAG pode ser lento${NC}"
    echo -e "   Resposta: $(echo "$EMBED_WARMUP_RESPONSE" | head -c 120)"
fi

# ============================================================================
# 3. VERIFICAR AMBIENTE PYTHON
# ============================================================================
echo ""
echo -e "${YELLOW}[3/8]${NC} Verificando ambiente Python..."

# Verificar virtual environment
if [ ! -d "venv" ]; then
    echo "🔄 Criando ambiente virtual..."
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Virtual environment criado"
fi

# Ativar virtual environment
source venv/bin/activate

# Verificar Flask
if ! python3 -c "import flask" 2>/dev/null; then
    echo "🔄 Instalando dependências..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Erro ao instalar dependências${NC}"
        echo "   Execute: pip3 install -r requirements.txt"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Dependências instaladas"
else
    echo -e "${GREEN}✓${NC} Dependências já instaladas"
fi

# Verificar openWakeWord (necessário para detecção de wake word local)
# Instalado com --no-deps pois tflite-runtime não tem wheel para aarch64
if ! python3 -c "import openwakeword" 2>/dev/null; then
    echo "🔄 Instalando openWakeWord (sem tflite para aarch64)..."
    pip install openwakeword --no-deps --quiet
fi
if python3 -c "import openwakeword" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} openWakeWord disponível (wake word local)"
else
    echo -e "${YELLOW}⚠️  openWakeWord não disponível (wake word desabilitado)${NC}"
fi

# Verificar Supertonic TTS (obrigatório)
if python3 -c "import supertonic" 2>/dev/null; then
    SUPERTONIC_AVAILABLE=true
    echo -e "${GREEN}✓${NC} Supertonic 2 TTS disponível (multilingual, 9x mais rápido)"
else
    SUPERTONIC_AVAILABLE=false
    echo -e "${RED}❌ Supertonic 2 TTS não instalado${NC}"
    echo "   Para instalar: pip install supertonic"
fi

# ============================================================================
# 4. VERIFICAR CONFIGURAÇÃO
# ============================================================================
echo ""
echo -e "${YELLOW}[4/8]${NC} Verificando configuração..."

# Verificar .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "🔄 Criando .env a partir de .env.example..."
        cp .env.example .env
        
        # Atualizar paths automaticamente
        echo -e "${GREEN}✓${NC} Arquivo .env criado"
    else
        echo -e "${YELLOW}⚠️  .env não encontrado (voz pode não funcionar)${NC}"
    fi
else
    echo -e "${GREEN}✓${NC} Arquivo .env existe"
fi

# Verificar diretórios necessários
mkdir -p data
mkdir -p static/audio
echo -e "${GREEN}✓${NC} Diretórios criados"

# ============================================================================
# 5. INICIALIZAR BANCO DE DADOS
# ============================================================================
echo ""
echo -e "${YELLOW}[5/8]${NC} Verificando banco de dados..."

if [ ! -f "data/users.db" ]; then
    echo "🔄 Inicializando banco de dados..."
    if [ -f "src/init_system.py" ]; then
        python3 src/init_system.py
        echo -e "${GREEN}✓${NC} Banco de dados inicializado"
    else
        echo -e "${YELLOW}⚠️  init_system.py não encontrado, banco será criado automaticamente${NC}"
    fi
else
    echo -e "${GREEN}✓${NC} Banco de dados já existe"
fi

# ============================================================================
# 6. PRÉ-CARREGAR MODELOS (aquecimento de caches)
# ============================================================================
echo ""
echo -e "${YELLOW}[6/8]${NC} Aquecendo modelos de IA..."

# [DEAD CODE] faster-whisper warmup — moved back to whisper.cpp CLI (better ARM NEON
# performance on RPi5 Cortex-A76). Kept for reference in case faster-whisper is revisited.
#
# if python3 -c "import faster_whisper" 2>/dev/null; then
#     echo "🔄 Aquecendo faster-whisper (primeira inferência)..."
#     WARMUP_WAV=$(mktemp /tmp/warmup_XXXXXX.wav)
#     USED_SPEECH=false
#     if command -v espeak &>/dev/null; then
#         espeak -v pt-br -s 140 "Olá, tudo bem? Como posso ajudar você hoje?" \
#                --stdout 2>/dev/null > "$WARMUP_WAV" && USED_SPEECH=true
#     fi
#     if [ "$USED_SPEECH" = false ] && command -v espeak-ng &>/dev/null; then
#         espeak-ng -v pt-br -s 140 "Olá, tudo bem? Como posso ajudar você hoje?" \
#                   --stdout 2>/dev/null > "$WARMUP_WAV" && USED_SPEECH=true
#     fi
#     WARMUP_START=$SECONDS
#     WARMUP_RESULT=$(python3 - "$WARMUP_WAV" "$USED_SPEECH" <<'PYEOF'
# import wave, struct, os, sys, time
# warmup_wav = sys.argv[1]
# used_speech = sys.argv[2] == 'true'
# if not used_speech or os.path.getsize(warmup_wav) < 1000:
#     sample_rate, duration = 16000, 2
#     num_samples = sample_rate * duration
#     with wave.open(warmup_wav, 'w') as wf:
#         wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate)
#         wf.writeframes(struct.pack('<' + 'h' * num_samples, *([0] * num_samples)))
#     used_speech = False
# try:
#     from faster_whisper import WhisperModel
#     model = WhisperModel(os.environ.get('FASTER_WHISPER_MODEL', 'base'), device='cpu', compute_type='int8')
#     segs, info = model.transcribe(warmup_wav, language='pt', beam_size=1, condition_on_previous_text=False,
#                                    vad_filter=used_speech)
#     text = ' '.join(s.text for s in segs).strip()
#     print(f'OK|{time.time()}|transcrito: "{text[:60]}"')
# except Exception as e:
#     print(f'FAIL|{e}')
# finally:
#     os.path.exists(warmup_wav) and os.unlink(warmup_wav)
# PYEOF
#     )
#     echo -e "${GREEN}✓${NC} faster-whisper aquecido"
# else
#     echo -e "${YELLOW}⚠️  faster-whisper não instalado, pulando aquecimento${NC}"
# fi
echo -e "${GREEN}✓${NC} STT: usando whisper-cli (sem aquecimento necessário)"

# ============================================================================
# 7. PRÉ-CARREGAR SUPERTONIC TTS
# ============================================================================
echo ""
echo -e "${YELLOW}[7/8]${NC} Aquecendo Supertonic TTS..."

if python3 -c "import supertonic" 2>/dev/null; then
    WARMUP_START=$SECONDS
    WARMUP_RESULT=$(python3 - <<'PYEOF'
import sys, os, time, tempfile

try:
    from supertonic import TTS
    t0 = time.time()
    tts = TTS()
    t_load = time.time() - t0

    phrase = "Olá! Estou pronto para conversar com você."

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        out_path = f.name

    t1 = time.time()
    wav_array, duration = tts.synthesize(phrase, voice_style=tts.get_voice_style("M2"), lang="pt")
    tts.save_audio(wav_array, out_path)
    t_synth = time.time() - t1

    try:
        os.unlink(out_path)
    except Exception:
        pass

    dur_s = float(duration[0]) if duration else 0.0
    print(f"OK|{t_load:.1f}s load|{t_synth:.1f}s synth|{dur_s:.2f}s audio")

except Exception as e:
    print(f"FAIL|{e}")
PYEOF
    )
    WARMUP_SECS=$(( SECONDS - WARMUP_START ))

    if echo "$WARMUP_RESULT" | grep -q "^OK|"; then
        TLOAD=$(echo "$WARMUP_RESULT" | cut -d'|' -f2)
        TSYNTH=$(echo "$WARMUP_RESULT" | cut -d'|' -f3)
        TAUDIO=$(echo "$WARMUP_RESULT" | cut -d'|' -f4)
        echo -e "${GREEN}✓${NC} Supertonic TTS aquecido em ${WARMUP_SECS}s"
        echo -e "   ${TLOAD} | ${TSYNTH} | ${TAUDIO} gerado"
    else
        ERR=$(echo "$WARMUP_RESULT" | cut -d'|' -f2-)
        echo -e "${RED}❌ Falha no aquecimento do Supertonic: ${ERR}${NC}"
        echo -e "${YELLOW}   (primeira síntese do usuário pode ser mais lenta)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Supertonic não instalado, pulando aquecimento${NC}"
fi

# ============================================================================
# 6b. CALIBRAR VAD (medir ruído ambiente)
# ============================================================================
echo ""
echo -e "${YELLOW}[6b]${NC} Calibrando VAD para o ambiente atual..."

VAD_CALIBRATION=$(python3 - <<'PYEOF'
import os
try:
    import pyaudio, numpy as np

    DURATION = 2.0
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 1024

    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_fd = os.dup(2)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    try:
        p = pyaudio.PyAudio()
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)

    # Fall back to device native rate if 16000 Hz isn't supported
    try:
        p.is_format_supported(SAMPLE_RATE, input_device=None,
                              input_channels=1, input_format=pyaudio.paInt16)
    except ValueError:
        SAMPLE_RATE = int(p.get_default_input_device_info()['defaultSampleRate'])

    stream = p.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                    input=True, frames_per_buffer=CHUNK_SIZE)

    n_chunks = int(DURATION * SAMPLE_RATE / CHUNK_SIZE)
    rms_values = []
    for _ in range(n_chunks):
        data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        arr = np.frombuffer(data, dtype=np.int16).astype(np.float64)
        rms_sq = np.mean(arr ** 2)
        if not (np.isnan(rms_sq) or np.isinf(rms_sq) or rms_sq < 0):
            rms_values.append(np.sqrt(rms_sq))

    stream.stop_stream()
    stream.close()
    p.terminate()

    rms_arr = np.array(rms_values)
    median = float(np.median(rms_arr))
    clean = rms_arr[rms_arr <= median * 3]
    if len(clean) < 3:
        clean = rms_arr
    mean = float(np.mean(clean))
    std = float(np.std(clean))
    threshold = max(20, int(mean + 2 * std))
    print(f"OK|{threshold}|{mean:.1f}|{std:.1f}")
except Exception as e:
    print(f"FAIL|{e}")
PYEOF
)

if echo "$VAD_CALIBRATION" | grep -q "^OK|"; then
    VAD_THRESHOLD=$(echo "$VAD_CALIBRATION" | cut -d'|' -f2)
    VAD_MEAN=$(echo "$VAD_CALIBRATION" | cut -d'|' -f3)
    VAD_STD=$(echo "$VAD_CALIBRATION" | cut -d'|' -f4)
    export VAD_THRESHOLD
    echo -e "${GREEN}✓${NC} VAD calibrado: ambient=${VAD_MEAN} ±${VAD_STD} → threshold=${VAD_THRESHOLD}"
else
    ERR=$(echo "$VAD_CALIBRATION" | cut -d'|' -f2-)
    echo -e "${YELLOW}⚠️  Calibração VAD falhou: ${ERR} (usando padrão=30)${NC}"
fi

# ============================================================================
# 8. INICIAR SERVIDOR FLASK
# ============================================================================
echo ""
echo -e "${YELLOW}[8/8]${NC} Iniciando servidor Flask..."
echo ""
echo -e "${BLUE}======================================================================${NC}"
echo -e "${GREEN}✓ Sistema pronto!${NC}"
echo ""
echo -e "${BLUE}Acesse o sistema em:${NC}"
echo -e "  ${GREEN}http://localhost:5000${NC}"
echo ""
echo -e "${BLUE}Funcionalidades disponíveis:${NC}"
echo "  • Cadastro de usuários via RFID"
echo "  • Interface de chat com robô (animação SSE em tempo real)"
echo "  • Integração de voz (TTS com Supertonic)"
echo "  • Reconhecimento de voz (STT com Whisper + Mean VAD)"
echo "  • Conversas com IA (Ollama + streaming)"
echo "  • Sistema de personalidades (9 estilos de resposta)"
echo "  • Histórico de conversas (SQLite)"
echo ""
echo -e "${YELLOW}Configuração de TTS:${NC}"
if [ "$SUPERTONIC_AVAILABLE" = true ]; then
    echo "  • Engine: Supertonic 2 (multilingual, 9x mais rápido)"
else
    echo "  • ⚠️  Supertonic não instalado - TTS indisponível (pip install supertonic)"
fi
echo ""
echo -e "${YELLOW}Dispositivos de áudio:${NC}"
echo "  • Execute test_audio_devices.py para configurar"
echo ""
echo -e "${BLUE}Logs do sistema aparecerão abaixo:${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo ""

# Iniciar Flask
# O trap garante que Ctrl+C no shell encerra o processo Python de forma limpa
trap 'echo -e "\n${YELLOW}⚠️  Interrompido pelo usuário${NC}"; kill $FLASK_PID 2>/dev/null; wait $FLASK_PID 2>/dev/null; exit 0' SIGINT SIGTERM

python3 src/app.py &
FLASK_PID=$!
wait $FLASK_PID



