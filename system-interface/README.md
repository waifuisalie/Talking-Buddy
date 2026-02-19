# Sistema de Cadastro RFID + Assistente de Voz com Wake Word

Sistema web **100% OFFLINE** para gerenciamento de usuários com leitor RFID, assistente de voz com IA e detecção de wake word via ESP32.

**Funciona sem internet** - Todos os arquivos são locais (sem CDNs ou APIs externas).

## 🚀 Início Rápido

### Primeira vez (Instalação):
```bash
cd rpi5-chatbot
bash setup.sh
```

### Iniciar o sistema (sempre):
```bash
cd system-interface
bash start.sh
```

Depois abra o navegador: **http://localhost:5000**

## ✨ Funcionalidades

- ✅ **RFID**: Identificação automática de usuários
- ✅ **Wake Word**: Diga "Marvin" para ativar o assistente (ESP32)
- ✅ **Voz**: Reconhecimento (Whisper) + Resposta (Ollama) + Síntese (Piper TTS)
- ✅ **Chat**: Interface animada com robô
- ✅ **100% Offline**: Sem internet necessária
- ✅ **Auto-detecção**: Sistema encontra ESP32 em qualquer porta USB

## 🎤 Wake Word Detection

O sistema suporta **dois modos** de detecção de wake word:

### Modo 1: Local (Vosk) - Recomendado ✅

Detecção 100% no Raspberry Pi usando o microfone USB.

**Vantagens:**
- ✅ Melhor qualidade (microfone USB > microfone I2S do ESP32)
- ✅ Apenas 1 microfone necessário
- ✅ Mais simples (sem hardware adicional)
- ✅ 100% offline (sem API keys)
- ✅ Palavra customizável facilmente

**Configuração (.env):**
```bash
WAKE_WORD_MODE=local
WAKE_WORD_KEYWORD=marvin
VOSK_MODEL_PATH=~/vosk-models/vosk-model-small-pt-0.3
```

**Instalação:**
```bash
# 1. Instalar Vosk (já instalado no venv)
pip3 install vosk

# 2. Baixar modelo português (~31MB)
cd ~
mkdir -p vosk-models && cd vosk-models
wget https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip
unzip vosk-model-small-pt-0.3.zip
rm vosk-model-small-pt-0.3.zip
```

### Modo 2: ESP32 (Hardware Externo)

Detecção via ESP32-S3 com TensorFlow Lite.

**Vantagens:**
- ✅ Não usa CPU do Raspberry
- ✅ Latência muito baixa (~100ms)

**Desvantagens:**
- ❌ Microfone I2S de qualidade inferior
- ❌ Hardware adicional necessário
- ❌ 2 microfones no sistema

**Configuração (.env):**
```bash
WAKE_WORD_MODE=esp32
ESP32_BAUD_RATE=115200
ESP32_RECONNECT_INTERVAL=5
```

**Requisitos:**
- ESP32-S3 com firmware de wake word
- Usuário no grupo `dialout`:
  ```bash
  sudo usermod -a -G dialout $USER
  # Fazer logout/login após
  ```

### Como funciona:

1. **Detecção**: Sistema detecta palavra "marvin" (ou configurada)
2. **Ação automática**:
   - Tela do robô: Abre chat + toca som + ativa microfone
   - Tela do chat: Toca som + ativa microfone
3. **Gravação**: VAD grava até silêncio
4. **Processamento**: Whisper → Ollama → Piper

### Testar:

```bash
# Testar detector local
cd system-interface
source venv/bin/activate
python3 src/local_wake_word.py
# Diga "marvin" próximo ao microfone

# Testar integração completa
bash start.sh
# Sistema deve mostrar: "✅ Local Wake Word Manager ativado"
```

### Desabilitar Wake Word:

```bash
# No .env
WAKE_WORD_MODE=disabled
```

## 🚀 Início Rápido

```bash
pip3 install flask
python3 src/init_system.py
```

## Uso

```bash
python3 src/app.py
```

Acesse: **http://localhost:5000**

## Estrutura

```
├── src/
│   ├── app.py           # Servidor Flask (localhost)
│   ├── database.py      # SQLite local
│   └── init_system.py   # Inicializador
├── templates/           # HTML local
├── static/              # CSS e JS local
└── assistant.db         # Banco SQLite (criado automaticamente)
```

## Características

- ✅ 100% Offline (sem internet)
- ✅ Banco de dados SQLite local
- ✅ Todos os arquivos locais (CSS, JS, HTML)
- ✅ Servidor apenas em localhost (127.0.0.1)
- ✅ Teclado virtual integrado

## Campos

- Nome, CPF (11 dígitos), Email, Telefone, RFID
