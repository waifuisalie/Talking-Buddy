# 🚀 Guia Rápido de Início

## TL;DR - Comandos Essenciais

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar (se necessário)
nano .env

# 3. Validar instalação
python3 test_voice_system.py

# 4. Iniciar Ollama (se não estiver rodando)
ollama serve &
ollama pull gemma3:1b

# 5. Iniciar aplicação
python3 src/app.py

# 6. Acessar no navegador
# http://localhost:5000
```

---

## 📋 Checklist Pré-Execução

### No Raspberry Pi

- [ ] Ollama instalado e rodando (`ollama serve`)
- [ ] Modelo `gemma3:1b` baixado (`ollama pull gemma3:1b`)
- [ ] Piper TTS instalado (binary + modelo pt_BR)
- [ ] ALSA configurado (áudio funcionando)
- [ ] Dependências Python instaladas (`pip install -r requirements.txt`)
- [ ] Arquivo `.env` configurado (copiar de `.env.example`)

---

## 🎯 Fluxo de Uso

### 1. Login
- Aproximar cartão RFID
- Aguardar saudação aparecer
- Chat NÃO abre automaticamente

### 2. Abrir Chat
- Clicar em qualquer lugar no robô
- Chat abre em modo compacto
- Histórico carrega automaticamente

### 3. Conversar
- Digitar mensagem no campo de texto
- Pressionar Enter ou clicar em Enviar
- Aguardar resposta (texto + áudio sincronizados)

### 4. Timers
- **5 min** sem interação → Logout automático
- **10 min** sem interação → Robô sonolento
- **15 min** sem interação → Robô dormindo
- Durante conversa: timers pausam automaticamente

---

## 🔧 Configurações Importantes (.env)

```bash
# Modelo de IA
OLLAMA_MODEL=gemma3:1b

# Piper TTS
PIPER_BINARY=~/piper/piper/piper
PIPER_MODEL=pt_BR-faber-medium.onnx
PIPER_MODEL_PATH=~/piper/piper/

# Áudio (ajustar conforme seu hardware)
AUDIO_DEVICE=default  # Ou: hw:0,0, plughw:0,0
```

---

## 🧪 Teste Rápido da API

```bash
# 1. Status do sistema
curl http://localhost:5000/api/voice/status

# 2. Enviar mensagem
curl -X POST http://localhost:5000/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Olá!", "rfid": "TEST001", "user_id": 1}'

# 3. Ver histórico
curl http://localhost:5000/api/chat/history/TEST001
```

---

## 🐛 Troubleshooting Rápido

### "Voice system not available"
```bash
# Verificar Ollama
curl http://localhost:11434/api/tags

# Se não responder:
ollama serve &
```

### Áudio não reproduz
```bash
# Listar dispositivos ALSA
aplay -L

# Testar áudio
speaker-test -c2 -t wav

# Ajustar .env
AUDIO_DEVICE=hw:0,0
```

### Histórico não carrega
```bash
# Verificar tabela
sqlite3 data/users.db ".schema conversation_history"

# Verificar dados
sqlite3 data/users.db "SELECT COUNT(*) FROM conversation_history;"
```

---

## 📚 Documentação Completa

- **VOICE_SYSTEM_README.md** - Documentação técnica detalhada
- **IMPLEMENTATION_SUMMARY.md** - Resumo da implementação
- **test_voice_system.py** - Script de validação automática

---

## ⚡ Performance Esperada

**Raspberry Pi 4 (4GB RAM):**
- Tempo de resposta: 2-5 segundos (Ollama + TTS)
- Uso de RAM: ~1.2GB (com gemma3:1b)
- Uso de CPU: 60-80% durante processamento

**Raspberry Pi 5 (8GB RAM):**
- Tempo de resposta: 1-3 segundos
- Uso de RAM: ~1.2GB
- Uso de CPU: 40-60% durante processamento

---

## 🎓 Logs Úteis

### Backend (Terminal)
```
✅ Voice system initialized
🔊 Playing audio: /static/audio/tts_1234567890.wav
⚠️ Voice system not available: [erro]
```

### Frontend (F12 → Console)
```
🤖 Robô clicado! Abrindo chat...
📜 Carregando histórico de conversas
🔄 [syncTextWithAudio] Sincronizando...
⏰ Logout automático por inatividade (5 min)
```

---

**Pronto para usar! 🎉**

Se todos os testes passarem em `test_voice_system.py`, o sistema está 100% funcional.
