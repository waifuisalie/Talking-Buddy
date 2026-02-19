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
echo -e "${YELLOW}[1/6]${NC} Verificando pré-requisitos..."

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
echo -e "${YELLOW}[2/6]${NC} Verificando serviço Ollama..."

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

# Verificar modelo
if ! ollama list | grep -q "gemma3:1b\|gemma3-ptbr"; then
    echo -e "${YELLOW}⚠️  Nenhum modelo encontrado. Baixando gemma3:1b...${NC}"
    ollama pull gemma3:1b
fi
echo -e "${GREEN}✓${NC} Modelo Ollama disponível"

# ============================================================================
# 3. VERIFICAR AMBIENTE PYTHON
# ============================================================================
echo ""
echo -e "${YELLOW}[3/6]${NC} Verificando ambiente Python..."

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

# Verificar PyAudio (necessário para reconhecimento de voz)
if ! python3 -c "import pyaudio" 2>/dev/null; then
    echo "🔄 Instalando PyAudio (reconhecimento de voz)..."
    pip install pyaudio
    echo -e "${GREEN}✓${NC} PyAudio instalado"
fi

# ============================================================================
# 4. VERIFICAR CONFIGURAÇÃO
# ============================================================================
echo ""
echo -e "${YELLOW}[4/6]${NC} Verificando configuração..."

# Verificar .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "🔄 Criando .env a partir de .env.example..."
        cp .env.example .env
        
        # Atualizar paths automaticamente
        sed -i "s|~/piper/piper/piper|$HOME/piper/piper/piper|g" .env 2>/dev/null || \
        sed -i '' "s|~/piper/piper/piper|$HOME/piper/piper/piper|g" .env 2>/dev/null
        
        sed -i "s|~/piper/piper/|$HOME/piper/piper/|g" .env 2>/dev/null || \
        sed -i '' "s|~/piper/piper/|$HOME/piper/piper/|g" .env 2>/dev/null
        
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
echo -e "${YELLOW}[5/6]${NC} Verificando banco de dados..."

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
# 6. INICIAR SERVIDOR FLASK
# ============================================================================
echo ""
echo -e "${YELLOW}[6/6]${NC} Iniciando servidor Flask..."
echo ""
echo -e "${BLUE}======================================================================${NC}"
echo -e "${GREEN}✓ Sistema pronto!${NC}"
echo ""
echo -e "${BLUE}Acesse o sistema em:${NC}"
echo -e "  ${GREEN}http://localhost:5000${NC}"
echo ""
echo -e "${BLUE}Funcionalidades disponíveis:${NC}"
echo "  • Cadastro de usuários via RFID"
echo "  • Interface de chat com robô"
echo "  • Integração de voz (TTS com Piper)"
echo "  • Reconhecimento de voz (STT com Whisper)"
echo "  • Conversas com IA (Ollama)"
echo "  • Histórico de conversas (SQLite)"
echo ""
echo -e "${YELLOW}Dispositivos de áudio configurados:${NC}"
echo "  • Saída: adaptador P2 USB (Card 3)"
echo "  • Entrada: microfone USB (Card 2)"
echo "  • Execute test_audio_devices.py para reconfigurar"
echo ""
echo -e "${BLUE}Logs do sistema aparecerão abaixo:${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo ""

# Iniciar Flask
python3 src/app.py



