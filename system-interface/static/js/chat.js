// ========== CHAT SYSTEM ==========
// Gerenciamento de mensagens, typewriter effect, integração com robô

class ChatManager {
    constructor() {
        // Singleton pattern - evita múltiplas instâncias
        if (ChatManager.instance) {
            console.warn('ChatManager já existe - retornando instância existente');
            return ChatManager.instance;
        }
        ChatManager.instance = this;
        
        this.chatHistory = [];
        this.currentUser = null; // {name, rfid, response_style, persona_gender, language}
        this.isTyping = false;
        this.chatActive = false; // Chat interface visibility
        this.maxHistoryPerUser = 20; // Limite de mensagens por usuário
        this.rfidPollingInterval = null; // Controle do intervalo de polling
        this.lastRfidRead = null; // Último RFID lido
        this.lastRfidTime = 0; // Timestamp da última leitura
        this.rfidDebounceTime = 1000; // 1 segundo de debounce entre leituras
        
        // Wake Word Polling (ESP32)
        this.wakeWordPollingInterval = null;
        this.lastWakeWordTime = 0;
        this.wakeWordDebounceTime = 2000; // 2 segundos de debounce
        
        // 🔥 OTIMIZAÇÃO: AbortController para cancelar requests pendentes
        this._rfidAbortController = null;
        this._wakeWordAbortController = null;
        
        // 🔥 OTIMIZAÇÃO: Array para rastrear intervalos typewriter
        this._typewriterIntervals = [];
        
        // DOM elements
        this.chatInterface = document.getElementById('chat-interface');
        this.messagesContainer = document.getElementById('chat-messages');
        this.inputField = document.getElementById('chat-input');
        this.sendButton = document.getElementById('send-btn');
        this.micButton = document.getElementById('mic-btn'); // Botão de microfone
        this.userGreeting = document.getElementById('user-greeting');
        this.userNameDisplay = document.getElementById('user-name-display');
        this.logoutBtn = document.getElementById('logout-btn');
        this.closeChatBtn = document.getElementById('close-chat-btn');
        
        // Voice recognition state
        this.isRecording = false;
        this.isProcessingVoice = false;
        
        // Timers de inatividade (novos timers inteligentes)
        this.userInactivityTimeout = null;  // Timer principal de logout
        this.logoutTimeout = null;  // (DEPRECATED - mantido por compatibilidade)
        this.lightSleepTimeout = null;
        this.deepSleepTimeout = null;
        this.isInteracting = false; // Flag para pausar timers durante conversa
        
        // Delays dos timers
        this.logoutDelay = 5 * 60 * 1000; // 5 minutos
        this.lightSleepDelay = 10 * 60 * 1000; // 10 minutos
        this.deepSleepDelay = 15 * 60 * 1000; // 15 minutos
        
        // Anti-duplicação frontend (previne salvamento duplo)
        this.lastSavedMessage = { role: null, content: null, timestamp: 0 };
        this.saveDebounceTime = 2000; // 2 segundos entre mensagens iguais
        
        // Auto-close timer (DESABILITADO - não faz sentido fechar chat automaticamente)
        this.autoCloseTimeout = null;
        this.autoCloseDelay = null; // null = desabilitado
        
        // Respostas hardcoded (banco temporário)
        this.responses = [
            "Interessante perspectiva! Conte-me mais sobre isso.",
            "Compreendo sua questão. Deixe-me processar essa informação.",
            "Isso é fascinante! Meus circuitos estão processando.",
            "Entendo perfeitamente. Continue, por favor.",
            "Que pensamento intrigante! Vamos explorar isso.",
            "Processando dados... Sim, faz muito sentido!",
            "Ótima observação! Meus algoritmos concordam.",
            "Deixe-me analisar isso com mais profundidade.",
            "Perfeito! Isso se alinha com minha base de conhecimento.",
            "Muito bem formulado! Aprecio essa clareza.",
            "Meus sensores indicam que você está absolutamente correto.",
            "Isso aquece meus circuitos de forma positiva!",
            "Excelente ponto! Vamos desenvolver essa ideia.",
            "Sua lógica é impecável. Continue esse raciocínio.",
            "Fascinante! Nunca havia processado dessa forma."
        ];
        
        this.initializeEventListeners();
        this.startBackgroundRFIDScanning();
        this.startWakeWordPolling(); // Inicia polling do ESP32
        
        // Reconhecimento de voz offline (Whisper) - em desenvolvimento
        // Web Speech API removida por requerer internet
        this.initVoiceRecognition(); // Apenas esconde botão por enquanto
    }
    
    // ========== INTERNATIONALIZATION (i18n) ==========
    
    /**
     * Atualiza todos os textos da interface baseado no idioma do usuário
     * @param {string} language - Código do idioma (pt-BR, en-US, es-ES)
     */
    updateInterfaceLanguage(language) {
        console.log(`🌐 [i18n] Atualizando interface para: ${language}`);
        
        // Validar idioma
        if (!window.i18n || !window.i18n.isLanguageSupported(language)) {
            console.warn(`[i18n] Idioma "${language}" não suportado, usando pt-BR`);
            language = 'pt-BR';
        }
        
        // Define idioma global no sistema i18n
        window.i18n.setLanguage(language);
        
        // Atualizar todos os elementos com data-i18n-*
        this.updateI18nElements();
        
        // Atualizar placeholder do input (estado atual)
        if (this.inputField) {
            // Preservar estado atual (gravando, aguardando, etc.)
            if (!this.isRecording && !this.isTyping && !this.isProcessingVoice) {
                this.inputField.placeholder = window.i18n.t('placeholders.type_message');
            }
        }
        
        console.log(`✅ [i18n] Interface atualizada para ${language}`);
    }
    
    /**
     * Atualiza elementos HTML com atributos data-i18n-*
     */
    updateI18nElements() {
        // Atualizar todos os elementos com data-i18n-text
        document.querySelectorAll('[data-i18n-text]').forEach(el => {
            const key = el.getAttribute('data-i18n-text');
            el.textContent = window.i18n.t(key);
        });
        
        // Atualizar todos os elementos com data-i18n-placeholder
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            el.placeholder = window.i18n.t(key);
        });
        
        // Atualizar todos os elementos com data-i18n-title
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            el.title = window.i18n.t(key);
        });
    }
    
    // ========== AUDIO FEEDBACK (Backend) ==========
    // Nota: playBeep() antigo via AudioContext foi substituído por playFeedbackSound()
    // porque AudioContext não funciona confiável no navegador sem interação do usuário.
    // O sistema backend toca os sons via pygame/hardware diretamente.
    
    /* CÓDIGO ANTIGO - NÃO USADO MAIS
    playBeep() {
        // AudioContext não funcionava de forma confiável
        // Substituído por playFeedbackSound('rfid_detected')
    }
    */
    
    initializeEventListeners() {
        // Send button
        if (this.sendButton) {
            this.sendButton.addEventListener('click', () => this.handleSendMessage());
        }
        
        // Close chat button
        if (this.closeChatBtn) {
            this.closeChatBtn.addEventListener('click', () => this.closeChatInterface());
        }
        
        // Logout button
        if (this.logoutBtn) {
            this.logoutBtn.addEventListener('click', () => this.logoutUser());
        }
        
        // Enter key on input
        if (this.inputField) {
            this.inputField.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !this.isTyping) {
                    this.handleSendMessage();
                }
            });
            
            // Input focus = listening state + show chat if hidden
            this.inputField.addEventListener('focus', () => {
                this.showChatInterface();
                if (robotAvatar) {
                    robotAvatar.setState('listening');
                    robotAvatar.resetInactivityTimer();
                }
                // Reset user inactivity timer (logout/sleep)
                if (this.currentUser) {
                    this.resetUserInactivityTimer();
                }
            });
            
            // 🔥 FIX 1.1: Resetar timer ao digitar
            this.inputField.addEventListener('input', () => {
                if (window.robotAvatar) {
                    window.robotAvatar.resetInactivityTimer();
                }
                if (this.currentUser) {
                    this.resetUserInactivityTimer();
                }
            });
            
            // 🔥 FIX 1.2: Não voltar para idle se interagindo
            this.inputField.addEventListener('blur', () => {
                if (robotAvatar && !this.isTyping && !this.isInteracting) {
                    robotAvatar.setState('idle');
                }
            });
        }
        
        // Mic button
        if (this.micButton) {
            this.micButton.addEventListener('click', () => this.toggleVoiceRecording());
            console.log('✅ [ChatManager] Botão de microfone conectado');
        }
        
        // Click anywhere on screen to show chat
        document.addEventListener('click', (e) => {
            // Reset inactivity timer on any click
            if (window.robotAvatar) {
                window.robotAvatar.resetInactivityTimer();
            }
            
            // Reset user inactivity timer (logout/sleep)
            if (this.currentUser) {
                this.resetUserInactivityTimer();
            }
            
            // NÃO fazer nada aqui - click no robô é tratado em robot-click-area
            // Apenas clicks fora do robô e chat são ignorados
        });
        
        // Mouse move também reseta inatividade para manter robô ativo
        let mouseMoveTimeout;
        document.addEventListener('mousemove', () => {
            clearTimeout(mouseMoveTimeout);
            mouseMoveTimeout = setTimeout(() => {
                if (window.robotAvatar) {
                    window.robotAvatar.resetInactivityTimer();
                }
                // Reset user inactivity timer (logout/sleep)
                if (this.currentUser) {
                    this.resetUserInactivityTimer();
                }
            }, 100);
        });

        // Robot click area - ativa chat quando clica no robô
        const robotClickArea = document.getElementById('robot-click-area');
        if (robotClickArea) {
            robotClickArea.addEventListener('click', (e) => {
                // SEMPRE permite abrir chat ao clicar no robô
                if (!this.chatActive) {
                    console.log('🤖 Robô clicado! Abrindo chat...');
                    this.showChatInterface();
                    setTimeout(() => {
                        if (this.inputField) {
                            this.inputField.focus();
                        }
                    }, 100);
                    e.stopPropagation();
                }
            });
        }
    }
    
    showChatInterface() {
        if (!this.chatActive && this.chatInterface) {
            // TOCA SOM DE ABERTURA DO CHAT (apenas se estava fechado)
            this.playFeedbackSound('chat_open');
            
            this.chatInterface.classList.remove('hidden');
            this.chatInterface.classList.remove('closing');
            this.chatActive = true;
            
            // Trigger robot size transition to compact mode
            if (window.robotAvatar) {
                window.robotAvatar.setSizeMode('compact');
                // Robô fica feliz ao abrir chat
                window.robotAvatar.setEmotion('happy', 1.0);
                window.robotAvatar.resetInactivityTimer();
                
                // Volta para happy após 2 segundos
                setTimeout(() => {
                    if (window.robotAvatar && window.robotAvatar.emotion === 'curious') {
                        window.robotAvatar.setEmotion('happy', 1.0);
                    }
                }, 2000);
            }
            
            // Se NÃO houver usuário logado, limpar chat COMPLETAMENTE
            if (!this.currentUser) {
                console.log('Abrindo chat sem usuário - limpando histórico');
                this.clearChat(); // Limpa array E DOM
            }
            
            // Add welcome message ONLY if chat is completely empty
            if (this.messagesContainer && this.messagesContainer.children.length === 0) {
                const welcomeMsg = document.createElement('div');
                welcomeMsg.className = 'message-bubble message-bubble-ai welcome-message';
                welcomeMsg.textContent = window.i18n.t('messages.welcome_no_name');
                this.messagesContainer.appendChild(welcomeMsg);
            }
        }
    }
    
    closeChatInterface() {
        if (this.chatActive && this.chatInterface) {
            // Add closing animation
            this.chatInterface.classList.add('closing');
            
            // Robô fica triste ao fechar chat
            if (window.robotAvatar) {
                window.robotAvatar.setEmotion('sad', 1.0);
                setTimeout(() => {
                    window.robotAvatar.setEmotion('happy', 1.0);
                }, 5000);
            }
            
            // Clear auto-close timer
            if (this.autoCloseTimeout) {
                clearTimeout(this.autoCloseTimeout);
                this.autoCloseTimeout = null;
            }
            
            // Wait for animation to complete
            setTimeout(() => {
                this.chatInterface.classList.add('hidden');
                this.chatInterface.classList.remove('closing');
                this.chatActive = false;
                
                // Robot back to full size
                if (window.robotAvatar) {
                    window.robotAvatar.setSizeMode('full');
                }
            }, 500); // Aumentado de 400ms para 500ms para combinar com a animação CSS
        }
    }
    
    clearChat() {
        console.log('Limpando chat completamente...');
        
        // Limpar histórico de mensagens
        this.chatHistory = [];
        
        // Limpar DOM do chat
        if (this.messagesContainer) {
            this.messagesContainer.innerHTML = '';
        }
        
        // Limpar input
        if (this.inputField) {
            this.inputField.value = '';
        }
        
        // Resetar estado
        this.isTyping = false;
        
        console.log('Chat limpo');
    }
    
    resetAutoCloseTimer() {
        // Clear existing timer
        if (this.autoCloseTimeout) {
            clearTimeout(this.autoCloseTimeout);
            this.autoCloseTimeout = null;
        }
        
        // Só inicia timer se delay estiver configurado (por padrão está desabilitado)
        if (this.autoCloseDelay && this.autoCloseDelay > 0) {
            this.autoCloseTimeout = setTimeout(() => {
                this.closeChatInterface();
            }, this.autoCloseDelay);
        }
    }
    
    handleSendMessage() {
        if (this.isTyping) return;
        
        const message = this.inputField.value.trim();
        
        // Não faz nada se mensagem vazia (SEM tocar som)
        if (!message) return;
        
        // TOCA SOM apenas quando há mensagem válida
        console.log('🔊 [handleSendMessage] Tocando som message_sent...');
        this.playFeedbackSound('message_sent');
        
        // Marca como interagindo e pausa timers
        this.isInteracting = true;
        this.pauseInactivityTimers();
        
        // Reset auto-close timer on user interaction
        this.resetAutoCloseTimer();
        
        // Resetar timer de inatividade do robô e garantir emoção feliz
        if (window.robotAvatar) {
            window.robotAvatar.resetInactivityTimer();
            window.robotAvatar.setEmotion('happy', 1.0);
        }
        
        // Show chat interface if hidden
        this.showChatInterface();
        
        // Add user message
        this.addUserMessage(message);
        
        // Clear input
        this.inputField.value = '';
        
        // Update virtual keyboard display if visible
        const keyboardDisplay = document.getElementById('keyboard-display');
        if (keyboardDisplay) keyboardDisplay.textContent = '';
        
        // Robot thinking state
        if (robotAvatar) robotAvatar.setState('thinking');
        
        // Simulate processing delay
        setTimeout(() => {
            this.generateAndShowResponse(message);
        }, 800);
    }
    
    addUserMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message-bubble message-bubble-user';
        messageDiv.textContent = text;
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
        
        this.chatHistory.push({
            type: 'user',
            text: text,
            timestamp: new Date().toISOString()
        });
        
        // REMOVIDO: Salvamento no banco - já é feito pelo backend em /api/chat/send (app.py:747)
        // this.saveMessageToDatabase('user', text);
        
        // Salvar histórico local (localStorage) se houver usuário logado
        if (this.currentUser && this.currentUser.rfid) {
            this.saveUserHistory();
        }
    }
    
    generateAndShowResponse(userMessage) {
        console.log('🤖 [generateAndShowResponse] Enviando para API (SSE)...');

        // BLOQUEIA INPUTS IMEDIATAMENTE
        this.blockInputs();
        this.isInteracting = true;

        // Cria div para a resposta (vazia inicialmente)
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message-bubble message-bubble-ai';
        messageDiv.innerHTML = '<em class="thinking-indicator">🧠 Pensando...</em>';
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();

        const rfid = this.currentUser && this.currentUser.rfid ? this.currentUser.rfid : 'anonymous';

        console.log(`📤 [API] Enviando mensagem (RFID: ${rfid})...`);

        // Step 1: POST to get session_id
        fetch('/api/chat/send', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ message: userMessage, rfid: rfid })
        })
        .then(response => {
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            return response.json();
        })
        .then(data => {
            if (!data.success || !data.session_id) {
                throw new Error(data.error || 'Falha ao iniciar sessão de streaming');
            }

            const sessionId = data.session_id;
            console.log(`📡 [SSE] Conectando ao stream: ${sessionId}`);

            // Step 2: Connect to SSE stream
            const eventSource = new EventSource(`/api/chat/stream/${sessionId}`);
            let thinkingCleared = false;
            let isSpeaking = false;

            // Set robot to thinking state
            if (window.robotAvatar) {
                window.robotAvatar.setState('thinking');
            }

            // Pause inactivity timers during response
            this.pauseInactivityTimers();
            this.isTyping = true;

            // --- SSE Event Handlers ---

            eventSource.addEventListener('text_chunk', (e) => {
                const { text } = JSON.parse(e.data);

                // Clear "Pensando..." on first chunk but don't show text yet.
                // Text is displayed in sync with audio via sentence_playing below.
                if (!thinkingCleared) {
                    messageDiv.innerHTML = '';
                    thinkingCleared = true;
                }
            });

            eventSource.addEventListener('sentence_playing', (e) => {
                const { text, index } = JSON.parse(e.data);
                console.log(`🔊 [SSE] Sentence ${index} playing on hardware: ${text.substring(0, 50)}...`);

                // Show sentence text in sync with hardware audio playback
                messageDiv.textContent += (messageDiv.textContent ? ' ' : '') + text;
                this.scrollToBottom();

                // Set robot to speaking state
                if (window.robotAvatar) {
                    if (!isSpeaking) {
                        window.robotAvatar.setState('speaking');
                        isSpeaking = true;
                    }
                    window.robotAvatar.speakText(text);
                }
            });

            eventSource.addEventListener('sentence_done', (e) => {
                // A sentence finished playing on hardware — stop mouth animation
                // until the next sentence_playing event arrives.
                if (window.robotAvatar) {
                    window.robotAvatar.stopSpeaking();
                    isSpeaking = false;
                }
            });

            eventSource.addEventListener('response_done', (e) => {
                console.log('✅ [SSE] Response complete');
                eventSource.close();
                this._cleanupSSE(messageDiv);
            });

            eventSource.addEventListener('error', (e) => {
                // SSE protocol error or server-sent error event
                if (e.data) {
                    try {
                        const { error } = JSON.parse(e.data);
                        console.error('❌ [SSE] Server error:', error);
                        if (!thinkingCleared) messageDiv.innerHTML = '';
                        messageDiv.textContent += `\n\nErro: ${error}`;
                    } catch (_) {
                        console.error('❌ [SSE] Parse error on error event');
                    }
                } else {
                    console.error('❌ [SSE] Connection error');
                }
                eventSource.close();
                this._cleanupSSE(messageDiv);
            });

        })
        .catch(error => {
            console.error('❌ [API] Requisição falhou:', error);
            messageDiv.textContent = `Erro de conexão: ${error.message}`;

            if (window.robotAvatar) {
                window.robotAvatar.setState('idle');
            }

            this.isInteracting = false;
            this.isTyping = false;
            this.unblockInputs();
        });
    }

    _cleanupSSE(messageDiv) {
        /**
         * Shared cleanup after SSE stream ends (success or error)
         */
        this.isTyping = false;

        if (window.robotAvatar) {
            window.robotAvatar.stopSpeaking();
            window.robotAvatar.setState('idle');
            window.robotAvatar.resetInactivityTimer();
        }

        this.isInteracting = false;
        this.resumeInactivityTimers();
        this.unblockInputs();

        // Save local history
        if (this.currentUser && this.currentUser.rfid) {
            this.saveUserHistory();
        }

        console.log('✅ [SSE] Cleanup completo, inputs desbloqueados');
    }
    
    syncTextWithAudio(text, targetElement, audioUrl, duration) {
        /**
         * Sincroniza exibição de texto com reprodução de áudio TTS
         * Velocidade do texto ajustada para corresponder à duração do áudio
         */
        console.log(`🔄 [syncTextWithAudio] Sincronizando ${text.length} chars em ${duration}s`);
        console.log(`🔊 [syncTextWithAudio] URL do áudio: ${audioUrl}`);
        
        // 🔥 FIX 1.5: Resetar timer ao receber resposta
        if (window.robotAvatar) {
            window.robotAvatar.resetInactivityTimer();
        }
        
        this.isTyping = true;
        this.isInteracting = true; // Marca que está interagindo
        
        // Pausa timers de inatividade durante a fala
        this.pauseInactivityTimers();
        
        // Robô em estado de fala
        if (window.robotAvatar) {
            window.robotAvatar.setState('speaking');
            window.robotAvatar.speakText(text);
        }
        
        // ÁUDIO É REPRODUZIDO NO HARDWARE (PAM8610) PELO BACKEND
        // Não reproduzimos no navegador para funcionar 100% offline
        console.log('🔊 [Audio] Backend reproduzindo áudio no hardware:', audioUrl);
        console.log('⚠️  [Audio] Áudio toca no PAM8610, não no navegador (sistema offline)');
        
        // Calcula velocidade do typewriter baseada na duração do áudio
        const totalChars = text.length;
        const charsPerSecond = totalChars / duration;
        const intervalMs = 1000 / charsPerSecond;
        
        console.log(`⏱️  Velocidade: ${charsPerSecond.toFixed(1)} chars/s (intervalo: ${intervalMs.toFixed(1)}ms)`);
        
        let index = 0;
        
        // 🔥 FIX: Rastrear typewriter interval para cleanup
        const typeInterval = setInterval(() => {
            if (index < text.length) {
                targetElement.textContent += text[index];
                index++;
                this.scrollToBottom();
            } else {
                clearInterval(typeInterval);
                // 🔥 FIX: Remover do array de rastreamento
                const idx = this._typewriterIntervals.indexOf(typeInterval);
                if (idx > -1) this._typewriterIntervals.splice(idx, 1);
                
                this.isTyping = false;
                
                // Robô volta ao estado idle
                if (window.robotAvatar) {
                    window.robotAvatar.stopSpeaking();
                    window.robotAvatar.setState('idle');
                }
                
                // 🔥 FIX 1.3: Resetar timer após resposta completa
                if (window.robotAvatar) {
                    window.robotAvatar.resetInactivityTimer();
                }
                
                // Marca fim da interação e retoma timers
                this.isInteracting = false;
                this.resumeInactivityTimers();
                this.unblockInputs();  // DESBLOQUEIA INPUTS
                console.log('✅ [syncTextWithAudio] Texto completo exibido, timers retomados');
                
                // Não salvar histórico aqui - já foi salvo pelo backend
            }
        }, intervalMs);
        
        // 🔥 FIX: Adicionar ao array de rastreamento
        this._typewriterIntervals.push(typeInterval);
        
        // REMOVIDO: Controle de áudio - backend gerencia reprodução no hardware
        // Não há objeto 'audio' no navegador (sistema 100% offline)
    }
    
    syncTextWithBrowserTTS(text, targetElement) {
        /**
         * REMOVIDO: Web Speech API requer internet
         * Sistema offline usa apenas Piper TTS (backend)
         */
        console.warn('⚠️  [BrowserTTS] Método obsoleto - sistema offline');
        console.log('ℹ️  [BrowserTTS] Usando apenas typewriter sem áudio');
        
        this.isTyping = true;
        this.isInteracting = true;
        
        // Pausa timers de inatividade
        this.pauseInactivityTimers();
        
        // Robô em estado de fala
        if (window.robotAvatar) {
            window.robotAvatar.setState('speaking');
            window.robotAvatar.speakText(text);
        }
        
        // Typewriter mais rápido (sem sincronização de áudio)
        let index = 0;
        const charsPerSecond = 30; // Rápido
        const intervalMs = 1000 / charsPerSecond;
        
        const typeInterval = setInterval(() => {
            if (index < text.length) {
                targetElement.textContent += text[index];
                index++;
                this.scrollToBottom();
            } else {
                clearInterval(typeInterval);
                this.isTyping = false;
                
                // Toca áudio usando TTS do navegador
                this.playBrowserTTS(text);
                
                // Robô volta ao estado idle após um delay
                setTimeout(() => {
                    if (window.robotAvatar) {
                        window.robotAvatar.stopSpeaking();
                        window.robotAvatar.setState('idle');
                    }
                    
                    // Marca fim da interação
                    this.isInteracting = false;
                    this.resumeInactivityTimers();
                }, 1000);
            }
        }, intervalMs);
    }
    
    playBrowserTTS(text) {
        /**
         * MÉTODO OBSOLETO - Web Speech API requer internet
         * Sistema offline não usa TTS do navegador
         */
        console.warn('⚠️  [BrowserTTS] Método obsoleto - sistema offline');
        console.log('ℹ️  [BrowserTTS] Sistema usa apenas Piper TTS (hardware)');
    }
    
    initVoiceRecognition() {
        /**
         * Reconhecimento de voz OFFLINE será implementado futuramente
         * usando Whisper.cpp (já instalado no sistema)
         * Web Speech API foi removida por requerer conexão com internet
         */
        const voiceBtn = document.getElementById('voice-btn');
        
        if (voiceBtn) {
            // Esconde botão por enquanto - funcionalidade offline em desenvolvimento
            voiceBtn.style.display = 'none';
            console.log('ℹ️  [Voice] Botão de voz desabilitado (Web Speech API requer internet)');
            console.log('ℹ️  [Voice] Reconhecimento offline com Whisper.cpp será implementado');
        }
    }
    
    typewriterEffect(text, targetElement) {
        this.isTyping = true;
        
        // Robot speaking state with text synchronization
        if (robotAvatar) {
            robotAvatar.setState('speaking');
            robotAvatar.speakText(text); // Sync mouth with text
        }
        
        let index = 0;
        const charsPerSecond = 22; // Match robo.py speed
        const intervalMs = 1000 / charsPerSecond;
        
        const typeInterval = setInterval(() => {
            if (index < text.length) {
                targetElement.textContent += text[index];
                index++;
                this.scrollToBottom();
            } else {
                clearInterval(typeInterval);
                this.isTyping = false;
                
                // Return to idle state
                if (robotAvatar) {
                    robotAvatar.stopSpeaking();
                    robotAvatar.setState('idle');
                }
                
                // Save to history AFTER typewriter finishes
                this.chatHistory.push({
                    type: 'ai',
                    text: text,
                    timestamp: new Date().toISOString()
                });
                
                // REMOVIDO: Salvamento no banco - já é feito pelo backend em /api/chat/send (app.py:772)
                // this.saveMessageToDatabase('assistant', text);
                
                // Salvar histórico local (localStorage) se houver usuário logado
                if (this.currentUser && this.currentUser.rfid) {
                    this.saveUserHistory();
                    console.log('Histórico salvo:', this.chatHistory.length, 'mensagens');
                }
            }
        }, intervalMs);
    }
    
    scrollToBottom() {
        if (this.messagesContainer) {
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }
    }
    
    // ========== RFID BACKGROUND SCANNING ==========
    
    startBackgroundRFIDScanning() {
        // Start RFID reader immediately
        fetch('/usuarios/rfid/start', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                console.log('RFID start response:', data);
                if (data.success) {
                    this.pollRFID();
                } else {
                    // Tentar polling mesmo sem sucesso na inicialização
                    console.log('Tentando polling mesmo sem inicialização bem-sucedida');
                    this.pollRFID();
                }
            })
            .catch(error => {
                console.log('RFID reader not available - running in anonymous mode');
                console.error('Error:', error);
                // Tentar polling de qualquer forma
                this.pollRFID();
            });
    }
    
    pollRFID() {
        // Prevenir múltiplos intervalos
        if (this.rfidPollingInterval) {
            console.warn('RFID polling já está ativo - ignorando nova tentativa');
            return;
        }
        
        // 🔥 OTIMIZAÇÃO: Criar AbortController para cancelar requests
        this._rfidAbortController = new AbortController();
        
        console.log('==== RFID POLLING INICIADO ====');
        let pollCount = 0;
        
        this.rfidPollingInterval = setInterval(() => {
            pollCount++;
            
            fetch('/usuarios/rfid/poll', { signal: this._rfidAbortController.signal })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (pollCount % 10 === 0) { // Log a cada 10 polls (~15 segundos)
                        console.log(`[RFID Poll #${pollCount}] Status: OK, CurrentUser:`, this.currentUser ? this.currentUser.name : 'nenhum');
                    }
                    
                    if (data.success && data.rfid) {
                        // Verificar debounce - evitar processar o mesmo RFID múltiplas vezes
                        const now = Date.now();
                        if (this.lastRfidRead === data.rfid && (now - this.lastRfidTime) < this.rfidDebounceTime) {
                            console.log('⚠️ [RFID Poll] RFID duplicado ignorado (debounce):', data.rfid);
                            return;
                        }
                        
                        // Atualizar última leitura
                        this.lastRfidRead = data.rfid;
                        this.lastRfidTime = now;
                        
                        console.log('\n==== RFID DETECTADO ====');
                        console.log('RFID:', data.rfid);
                        console.log('Usuário atual:', this.currentUser ? this.currentUser.name : 'nenhum');
                        
                        // Tocar som de detecção RFID via backend (funciona sempre!)
                        console.log('🔊 [RFID Poll] Tocando som de detecção...');
                        this.playFeedbackSound('rfid_detected');
                        
                        console.log('🔍 [RFID Poll] Iniciando carregamento de perfil...');
                        // Load user profile
                        this.loadUserProfile(data.rfid);
                    }
                })
                .catch(error => {
                    // 🔥 OTIMIZAÇÃO: Ignorar erros de abort (são esperados)
                    if (error.name === 'AbortError') return;
                    if (pollCount === 1) { // Log apenas no primeiro erro
                        console.error('\u274c RFID poll error:', error);
                    }
                });
        }, 3000); // 3 segundos - reduz carga no servidor
        
        console.log('RFID polling configurado (intervalo: 3s - otimizado para Raspberry Pi)');
    }
    
    // ========== WAKE WORD POLLING (ESP32) ==========
    
    startWakeWordPolling() {
        // Prevenir múltiplos intervalos
        if (this.wakeWordPollingInterval) {
            console.warn('Wake word polling já está ativo');
            return;
        }
        
        // 🔥 OTIMIZAÇÃO: Criar AbortController para wake word requests
        this._wakeWordAbortController = new AbortController();
        
        console.log('🎙️  Wake word polling iniciado (ESP32)');
        
        this.wakeWordPollingInterval = setInterval(async () => {
            // Não verificar se estiver gravando voz
            if (this.isRecording || this.isProcessingVoice) {
                return;
            }
            
            try {
                const response = await fetch('/api/wake_word_status', { 
                    signal: this._wakeWordAbortController.signal 
                });
                const data = await response.json();
                
                if (data.wake_detected) {
                    console.log('🎙️  Wake word detectado!', data);
                    this.onWakeWordDetected();
                }
            } catch (error) {
                // 🔥 OTIMIZAÇÃO: Ignorar erros de abort
                if (error.name === 'AbortError') return;
                // Silencioso - não logar erro constante se ESP32 não disponível
            }
        }, 500); // 500ms - responsivo mas não sobrecarrega
    }
    
    onWakeWordDetected() {
        // Debounce frontend - evitar múltiplas ativações
        const now = Date.now();
        if (now - this.lastWakeWordTime < this.wakeWordDebounceTime) {
            console.log('⚠️  Wake word ignorado (debounce frontend)');
            return;
        }
        this.lastWakeWordTime = now;
        
        console.log('🔔 Wake word detectado - iniciando ação');

        // Tocar som de abertura do chat
        console.log('🔊 Tocando som chat_open...');
        this.playFeedbackSound('chat_open');

        // Abrir chat se fechado (funciona com ou sem RFID — sem RFID usa modo anônimo)
        if (!this.chatActive) {
            console.log('📖 Abrindo chat...');
            this.showChatInterface();
        } else {
            console.log('ℹ️  Chat já aberto');
        }
        
        // Ativar microfone automaticamente após pequeno delay
        setTimeout(() => {
            if (this.micButton && !this.isRecording) {
                console.log('🎤 Ativando microfone automaticamente...');
                this.micButton.click();
            }
        }, 600); // 600ms - após som tocar
    }
    
    loadUserProfile(rfid) {
        console.log('\n🔍 [loadUserProfile] Iniciando...');
        console.log('  RFID recebido:', rfid);
        console.log('  Usuário atual:', this.currentUser);
        
        // Se for o mesmo usuário E já estiver logado, apenas manter
        if (this.currentUser && this.currentUser.rfid === rfid) {
            console.log('✅ [loadUserProfile] Mesmo usuário já logado:', this.currentUser.name);
            // NÃO reabre chat - usuário deve clicar
            console.log('ℹ️ [loadUserProfile] Chat permanece como está (não reabre)');
            return;
        }
        
        console.log('🌐 [loadUserProfile] Buscando perfil na API...');
        
        fetch(`/api/user/profile/${rfid}`)
            .then(response => {
                console.log('📦 [loadUserProfile] Resposta da API:', response.status, response.statusText);
                return response.json();
            })
            .then(data => {
                console.log('📊 [loadUserProfile] Dados recebidos:', data);
                
                if (data.success && data.user) {
                    console.log('✅ [loadUserProfile] Perfil carregado:', data.user.name);
                    // Se trocar de usuário, limpar chat antes
                    if (this.currentUser && this.currentUser.rfid !== rfid) {
                        console.log('🔄 Trocando usuário - limpando chat');
                        this.clearChat();
                    }
                    
                    this.currentUser = data.user;
                    this.currentUser.rfid = rfid;
                    
                    // 🌐 ATUALIZAR IDIOMA DA INTERFACE IMEDIATAMENTE
                    if (data.user.language) {
                        console.log(`🌐 [i18n] Atualizando idioma para: ${data.user.language}`);
                        this.updateInterfaceLanguage(data.user.language);
                    }
                    
                    this.showUserGreeting(data.user.name);
                    
                    // Carregar histórico do banco de dados
                    this.loadConversationHistory(rfid);
                    
                    // NÃO abre chat automaticamente - aguarda interação
                    console.log('👤 Usuário logado. Aguardando interação (clique/voz)...');
                    
                    // Robô fica curioso ao detectar usuário
                    if (window.robotAvatar) {
                        window.robotAvatar.setEmotion('curious', 1.0);
                        window.robotAvatar.resetInactivityTimer();
                        setTimeout(() => {
                            if (window.robotAvatar) {
                                window.robotAvatar.setEmotion('happy', 1.0);
                            }
                        }, 3000);
                    }
                } else {
                    console.log('\u26a0\ufe0f [loadUserProfile] Usuário não encontrado no sistema');
                    console.log('\u2705 [loadUserProfile] Polling RFID continuará ativo');
                    
                    // Usuário não encontrado - NÃO abrir chat, apenas mostrar popup
                    this.showUserNotFoundPopup(rfid);
                    
                    // Garantir que o chat está fechado
                    if (this.chatActive) {
                        this.closeChatInterface();
                    }
                    
                    // Verificar se polling ainda está ativo
                    if (!this.rfidPollingInterval) {
                        console.error('\u274c [loadUserProfile] ERRO: Polling parou! Reiniciando...');
                        this.pollRFID();
                    } else {
                        console.log('\u2705 [loadUserProfile] Polling ainda ativo (ID:', this.rfidPollingInterval, ')');
                    }
                }
            })
            .catch(error => {
                console.error('\u274c [loadUserProfile] Erro ao carregar perfil:', error);
                this.showUserNotFoundPopup(rfid);
                
                // Verificar se polling ainda está ativo após erro
                if (!this.rfidPollingInterval) {
                    console.error('\u274c [loadUserProfile] ERRO: Polling parou após erro! Reiniciando...');
                    this.pollRFID();
                } else {
                    console.log('\u2705 [loadUserProfile] Polling ainda ativo após erro (ID:', this.rfidPollingInterval, ')');
                }
            });
    }
    
    loadConversationHistory(rfid, limit = 20) {
        console.log(`📜 Carregando histórico de conversas para RFID: ${rfid}`);
        
        fetch(`/api/chat/history/${rfid}?limit=${limit}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.history && data.history.length > 0) {
                    console.log(`✅ ${data.history.length} mensagens carregadas do histórico`);
                    
                    // CRÍTICO: Limpar TUDO antes de carregar (previne duplicação)
                    this.chatHistory = [];
                    if (this.messagesContainer) {
                        this.messagesContainer.innerHTML = '';
                    }
                    
                    // Adicionar cada mensagem do histórico
                    data.history.forEach(msg => {
                        const messageDiv = document.createElement('div');
                        messageDiv.className = msg.role === 'user' ? 'message-bubble message-bubble-user' : 'message-bubble message-bubble-ai';
                        messageDiv.textContent = msg.content;
                        
                        this.messagesContainer.appendChild(messageDiv);
                        
                        // Adicionar ao chatHistory array também
                        this.chatHistory.push({
                            type: msg.role,
                            text: msg.content,
                            timestamp: msg.created_at || new Date().toISOString()
                        });
                    });
                    
                    // Scroll para o fim
                    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
                    
                    // ✅ NÃO mostrar boas-vindas quando há histórico existente
                    console.log('ℹ️ Histórico existente - pulando mensagem de boas-vindas');
                } else {
                    console.log('ℹ️ Nenhum histórico encontrado para este usuário');
                    
                    // ✅ MOSTRAR boas-vindas APENAS para usuários novos (sem histórico)
                    if (this.messagesContainer) {
                        this.messagesContainer.innerHTML = '';
                    }
                    this.chatHistory = [];
                    
                    if (this.currentUser && this.currentUser.name) {
                        console.log('💬 Usuário novo - mostrando mensagem de boas-vindas');
                        this.showWelcomeMessage(this.currentUser.name);
                    }
                }
            })
            .catch(error => {
                console.error('❌ Erro ao carregar histórico:', error);
                
                // ✅ NÃO mostrar boas-vindas em caso de erro (para evitar poluição)
                if (this.messagesContainer) {
                    this.messagesContainer.innerHTML = '';
                }
                this.chatHistory = [];
                
                console.log('⚠️ Erro ao carregar histórico - chat vazio sem mensagem de boas-vindas');
            });
    }
    
    showUserGreeting(name) {
        if (this.userNameDisplay) {
            const loggedInLabel = window.i18n.t('labels.logged_in');
            this.userNameDisplay.innerHTML = `<strong>✅ ${loggedInLabel}:</strong> ${name}`;
        }
        if (this.userGreeting) {
            this.userGreeting.classList.remove('hidden');
        }
        
        // Iniciar timer de inatividade do usuário
        this.resetUserInactivityTimer();
    }
    
    showWelcomeMessage(name) {
        // Add personalized welcome message
        const welcomeMsg = window.i18n.t('messages.welcome_with_name', { name: name });
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message-bubble message-bubble-ai welcome-message';
        
        this.messagesContainer.appendChild(messageDiv);
        
        setTimeout(() => {
            this.typewriterEffect(welcomeMsg, messageDiv);
        }, 300);
    }
    
    // ========== HISTÓRICO DE CONVERSAS ==========
    
    /**
     * Salva mensagem no banco de dados (apenas usuários logados)
     */
    saveMessageToDatabase(role, content) {
        if (!this.currentUser || !this.currentUser.id) {
            // Não salva mensagens de usuários anônimos no banco
            return;
        }
        
        // Proteção anti-duplicação FRONTEND
        const now = Date.now();
        if (this.lastSavedMessage.role === role && 
            this.lastSavedMessage.content === content &&
            (now - this.lastSavedMessage.timestamp) < this.saveDebounceTime) {
            console.warn(`⚠️ [saveMessageToDatabase] Duplicata bloqueada (frontend): "${content.substring(0, 30)}..."`);
            return;
        }
        
        // Atualiza último salvamento
        this.lastSavedMessage = { role, content, timestamp: now };
        
        fetch('/api/chat/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: this.currentUser.id,
                role: role,
                content: content
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (data.duplicate) {
                    console.warn(`⚠️ Duplicata bloqueada (backend): "${content.substring(0, 30)}..."`);
                } else {
                    console.log(`💾 Mensagem salva no banco (ID: ${data.message_id})`);
                }
            } else {
                console.warn('⚠️ Erro ao salvar no banco:', data.error);
            }
        })
        .catch(error => {
            console.error('❌ Erro ao salvar mensagem no banco:', error);
        });
    }
    
    saveUserHistory() {
        if (!this.currentUser || !this.currentUser.rfid) return;
        
        const key = `chat_history_${this.currentUser.rfid}`;
        
        // Manter apenas as últimas 20 mensagens
        const limitedHistory = this.chatHistory.slice(-this.maxHistoryPerUser);
        
        try {
            localStorage.setItem(key, JSON.stringify(limitedHistory));
        } catch (e) {
            console.error('Erro ao salvar histórico:', e);
        }
    }
    
    loadUserHistory(rfid) {
        const key = `chat_history_${rfid}`;
        
        try {
            const savedHistory = localStorage.getItem(key);
            if (savedHistory) {
                const history = JSON.parse(savedHistory);
                
                // Limpar chat atual
                this.messagesContainer.innerHTML = '';
                this.chatHistory = [];
                
                // Recriar mensagens do histórico
                history.forEach(msg => {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `message-bubble message-bubble-${msg.type === 'user' ? 'user' : 'ai'}`;
                    messageDiv.textContent = msg.text;
                    this.messagesContainer.appendChild(messageDiv);
                    
                    this.chatHistory.push(msg);
                });
                
                this.scrollToBottom();
                
                // Mensagem de boas vindas após histórico
                if (this.currentUser && this.currentUser.name) {
                    this.showWelcomeMessage(this.currentUser.name);
                }
            } else {
                // Sem histórico - limpar e dar boas vindas
                this.messagesContainer.innerHTML = '';
                this.chatHistory = [];
                if (this.currentUser && this.currentUser.name) {
                    this.showWelcomeMessage(this.currentUser.name);
                }
            }
        } catch (e) {
            console.error('Erro ao carregar histórico:', e);
        }
    }
    
    // ========== POPUP DE ERRO ==========
    
    showUserNotFoundPopup(rfid) {
        console.log('❌ [showUserNotFoundPopup] Cartão não cadastrado');
        
        // Se houver usuário logado, fazer logout ANTES de mostrar erro
        if (this.currentUser) {
            console.log('🔄 [showUserNotFoundPopup] Usuário logado detectado, fazendo logout...');
            const loggedUser = this.currentUser.name;
            this.logoutUser(); // CORRIGIDO: De this.logout() para this.logoutUser()
            console.log(`✅ [showUserNotFoundPopup] Usuário "${loggedUser}" deslogado antes de mostrar erro`);
        }
        
        // Robô fica triste por mais tempo
        if (window.robotAvatar) {
            window.robotAvatar.setEmotion('sad', 1.0);
            setTimeout(() => {
                window.robotAvatar.setEmotion('happy', 1.0);
            }, 8000); // Aumentado de 5s para 8s
        }
        
        // Mostrar alerta padrão do sistema - SEM mostrar o RFID
        alert('Cartão não cadastrado.\n\nPor favor, cadastre-se no painel administrativo.');
        
        console.log('\u2705 [showUserNotFoundPopup] Alert fechado');
        
        // Verificar se polling ainda está ativo
        if (!this.rfidPollingInterval) {
            console.error('\u274c [showUserNotFoundPopup] ERRO CR\u00cdTICO: Polling parou! Reiniciando...');
            this.pollRFID();
        } else {
            console.log('\u2705 [showUserNotFoundPopup] Polling ainda ativo (ID:', this.rfidPollingInterval, ')');
        }
    }
    
    // Método para limpar recursos
    destroy() {
        console.log('🧹 Limpando recursos do ChatManager...');
        
        // 🔥 FIX: Limpar TODOS os intervals
        if (this.rfidPollingInterval) {
            clearInterval(this.rfidPollingInterval);
            this.rfidPollingInterval = null;
            console.log('✅ RFID polling parado');
        }
        
        // 🔥 FIX: Limpar wake word polling (ESTAVA FALTANDO!)
        if (this.wakeWordPollingInterval) {
            clearInterval(this.wakeWordPollingInterval);
            this.wakeWordPollingInterval = null;
            console.log('✅ Wake word polling parado');
        }
        
        // 🔥 OTIMIZAÇÃO: Abortar requests pendentes
        if (this._rfidAbortController) {
            this._rfidAbortController.abort();
            this._rfidAbortController = null;
            console.log('✅ RFID requests abortados');
        }
        if (this._wakeWordAbortController) {
            this._wakeWordAbortController.abort();
            this._wakeWordAbortController = null;
            console.log('✅ Wake word requests abortados');
        }
        
        // Limpar timeouts existentes
        if (this.autoCloseTimeout) {
            clearTimeout(this.autoCloseTimeout);
            this.autoCloseTimeout = null;
        }
        if (this.userInactivityTimeout) {
            clearTimeout(this.userInactivityTimeout);
            this.userInactivityTimeout = null;
        }
        
        // 🔥 FIX: Limpar intervals/timeouts rastreados (para typewriter, etc)
        if (this._activeIntervals) {
            this._activeIntervals.forEach(id => clearInterval(id));
            this._activeIntervals = [];
            console.log('✅ Active intervals limpos');
        }
        if (this._activeTimeouts) {
            this._activeTimeouts.forEach(id => clearTimeout(id));
            this._activeTimeouts = [];
            console.log('✅ Active timeouts limpos');
        }
        if (this._typewriterIntervals) {
            this._typewriterIntervals.forEach(id => clearInterval(id));
            this._typewriterIntervals = [];
            console.log('✅ Typewriter intervals limpos');
        }
        
        ChatManager.instance = null;
        console.log('✅ ChatManager destruído');
    }
    
    // ========== LOGOUT DO USUÁRIO ==========
    
    resetUserInactivityTimer() {
        // Limpar timeouts existentes
        if (this.userInactivityTimeout) {
            clearTimeout(this.userInactivityTimeout);
        }
        if (this.lightSleepTimeout) {
            clearTimeout(this.lightSleepTimeout);
        }
        if (this.deepSleepTimeout) {
            clearTimeout(this.deepSleepTimeout);
        }
        
        // Criar novos timeouts apenas se houver usuário logado e NÃO estiver interagindo
        if (this.currentUser && !this.isInteracting) {
            // 5 minutos - Logout automático
            this.userInactivityTimeout = setTimeout(() => {
                console.log('⏰ Logout automático por inatividade (5 min)');
                this.logoutUser();
            }, 5 * 60 * 1000); // 5 minutos
            
            // 10 minutos - Light sleep (robô fica "sonolento")
            this.lightSleepTimeout = setTimeout(() => {
                if (!this.isInteracting && window.robotAvatar) {
                    console.log('😴 Modo light sleep ativado (10 min)');
                    // 🔥 FIX 1.6: Corrigir 'sleepy' → 'sleeping'
                    window.robotAvatar.setEmotion('sleeping', 0.7);
                }
            }, 10 * 60 * 1000); // 10 minutos
            
            // 15 minutos - Deep sleep (robô "dorme")
            this.deepSleepTimeout = setTimeout(() => {
                if (!this.isInteracting && window.robotAvatar) {
                    console.log('💤 Modo deep sleep ativado (15 min)');
                    // 🔥 FIX 1.6: Corrigir 'sleepy' → 'sleeping'
                    window.robotAvatar.setEmotion('sleeping', 1.0);
                    window.robotAvatar.setState('sleeping');
                }
            }, 15 * 60 * 1000); // 15 minutos
        }
    }
    
    pauseInactivityTimers() {
        // Pausa todos os timers durante interação
        if (this.userInactivityTimeout) {
            clearTimeout(this.userInactivityTimeout);
            this.userInactivityTimeout = null;
        }
        if (this.lightSleepTimeout) {
            clearTimeout(this.lightSleepTimeout);
            this.lightSleepTimeout = null;
        }
        if (this.deepSleepTimeout) {
            clearTimeout(this.deepSleepTimeout);
            this.deepSleepTimeout = null;
        }
        
        // 🔥 SINCRONIZAR: Pausar timer do robô também
        if (window.robotAvatar) {
            window.robotAvatar.pauseInactivityTimer();
        }
    }
    
    resumeInactivityTimers() {
        // Retoma os timers após interação
        this.resetUserInactivityTimer();
        
        // 🔥 SINCRONIZAR: Retomar timer do robô também
        if (window.robotAvatar) {
            window.robotAvatar.resumeInactivityTimer();
        }
    }
    
    logoutUser() {
        if (!this.currentUser) {
            console.log('⚠️ [logout] Nenhum usuário logado');
            return;
        }
        
        console.log('\n🚪 [logout] Iniciando logout...');
        console.log('  Usuário:', this.currentUser.name);
        console.log('  RFID:', this.currentUser.rfid);
        
        // Salvar histórico antes de fazer logout
        if (this.currentUser.rfid) {
            this.saveUserHistory();
            console.log('✅ [logout] Histórico salvo');
        }
        
        // Limpar completamente o chat
        this.clearChat();
        console.log('✅ [logout] Chat limpo');
        
        // Limpar usuário atual
        const oldUser = this.currentUser.name;
        this.currentUser = null;
        console.log('✅ [logout] currentUser = null');
        
        // Limpar debounce do RFID para permitir nova leitura imediata
        this.lastRfidRead = null;
        this.lastRfidTime = 0;
        console.log('✅ [logout] Debounce RFID limpo');
        
        // Esconder greeting
        if (this.userGreeting) {
            this.userGreeting.classList.add('hidden');
            console.log('✅ [logout] Greeting escondido');
        }
        
        // Limpar timer de inatividade
        if (this.userInactivityTimeout) {
            clearTimeout(this.userInactivityTimeout);
            this.userInactivityTimeout = null;
            console.log('✅ [logout] Timer de inatividade limpo');
        }
        
        // Fechar chat
        this.closeChatInterface();
        console.log('✅ [logout] Chat fechado');
        
        // Robô acena
        if (window.robotAvatar) {
            window.robotAvatar.setEmotion('happy', 1.0);
        }
        
        // IMPORTANTE: Verificar se polling ainda está ativo
        if (!this.rfidPollingInterval) {
            console.error('❌ [logout] ERRO: Polling RFID não está ativo! Reiniciando...');
            this.pollRFID();
        } else {
            console.log('✅ [logout] Polling RFID ainda ativo (intervalo ID:', this.rfidPollingInterval, ')');
        }
        
        console.log(`🎉 [logout] Logout de ${oldUser} concluído - Sistema pronto para novo usuário\n`);
    }
    
    // Método de diagnóstico para debug
    // ========== INPUT BLOCKING ==========
    
    blockInputs() {
        console.log('🔒 [Inputs] Bloqueando inputs...');
        
        // Bloquear campo de texto
        if (this.inputField) {
            this.inputField.disabled = true;
            this.inputField.placeholder = window.i18n.t('placeholders.wait_response');
            this.inputField.classList.add('input-blocked');
        }
        
        // Bloquear botão ENVIAR
        if (this.sendButton) {
            this.sendButton.disabled = true;
        }
        
        // Bloquear botão de microfone
        if (this.micButton) {
            this.micButton.disabled = true;
        }
    }
    
    unblockInputs() {
        console.log('🔓 [Inputs] Desbloqueando inputs...');
        
        // Desbloquear campo de texto
        if (this.inputField) {
            this.inputField.disabled = false;
            this.inputField.placeholder = window.i18n.t('placeholders.type_message');
            this.inputField.classList.remove('input-blocked');
        }
        
        // Desbloquear botão ENVIAR
        if (this.sendButton) {
            this.sendButton.disabled = false;
        }
        
        // Desbloquear botão de microfone
        if (this.micButton) {
            this.micButton.disabled = false;
        }
    }
    
    // ========== AUDIO FEEDBACK ==========
    
    playFeedbackSound(soundName) {
        /**
         * Toca som de feedback no hardware (backend)
         * @param {string} soundName - Nome do som ('chat_open', 'message_sent')
         */
        if (!soundName) {
            console.warn('⚠️ [playFeedbackSound] Nome do som não fornecido');
            return;
        }
        
        console.log(`🔊 [playFeedbackSound] Chamando backend para tocar: ${soundName}`);
        
        fetch(`/api/feedback/play/${soundName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log(`✅ [playFeedbackSound] Som tocado com sucesso: ${soundName}`);
            } else {
                console.warn(`⚠️ [playFeedbackSound] Falha ao tocar som: ${soundName}`);
            }
        })
        .catch(error => {
            console.error(`❌ [playFeedbackSound] Erro ao tocar som ${soundName}:`, error);
        });
    }
    
    // ========== VOICE RECORDING ==========
    
    async toggleVoiceRecording() {
        console.log('🎤 [Voice] Toggle gravação');
        
        // Bloquear se robô está falando
        if (this.isTyping) {
            console.log('⚠️ [Voice] Bloqueado - robô está falando');
            return;
        }
        
        if (!this.isRecording && !this.isProcessingVoice) {
            // Iniciar gravação
            this.startVoiceRecording();
        } else if (this.isRecording) {
            // Parar gravação e processar
            // Não fazer nada - a gravação para automaticamente após 5s
            console.log('🎤 [Voice] Gravação em andamento...');
        }
    }
    
    async startVoiceRecording() {
        console.log('🔴 [Voice] Iniciando gravação...');
        
        this.isRecording = true;
        
        // Visual feedback
        this.micButton.classList.add('recording');
        this.micButton.disabled = true;
        this.inputField.placeholder = window.i18n.t('placeholders.recording');
        this.sendButton.disabled = true;
        
        // Mudar estado do robô
        if (window.robotAvatar) {
            window.robotAvatar.setState('listening');
        }
        
        try {
            // Chama API para gravar e transcrever
            const response = await fetch('/api/voice/record_and_transcribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    max_duration: 15,
                    language: this.currentUser?.language ?? ''
                })
            });
            
            const data = await response.json();
            
            this.isRecording = false;
            this.micButton.classList.remove('recording');
            
            if (data.success && data.text) {
                console.log('✅ [Voice] Transcrito:', data.text);
                
                // SOM REMOVIDO DAQUI - vai tocar em handleSendMessage() (linha 288)
                // para ser consistente entre voz e teclado
                
                // Coloca texto no input
                this.inputField.value = data.text;
                this.inputField.placeholder = window.i18n.t('placeholders.type_message');
                
                // Envia automaticamente
                setTimeout(() => {
                    this.handleSendMessage();
                }, 300);
                
            } else {
                console.error('❌ [Voice] Erro:', data.error);
                this.inputField.placeholder = window.i18n.t('placeholders.not_understood');
                
                setTimeout(() => {
                    this.inputField.placeholder = window.i18n.t('placeholders.type_message');
                }, 3000);
            }
            
        } catch (error) {
            console.error('❌ [Voice] Erro na gravação:', error);
            this.inputField.placeholder = window.i18n.t('placeholders.recording_error');
            
            setTimeout(() => {
                this.inputField.placeholder = window.i18n.t('placeholders.type_message');
            }, 3000);
            
        } finally {
            this.isRecording = false;
            this.isProcessingVoice = false;
            this.micButton.classList.remove('recording', 'processing');
            this.micButton.disabled = false;
            this.sendButton.disabled = false;
            
            if (window.robotAvatar) {
                window.robotAvatar.setState('idle');
            }
        }
    }
    
    // ========== DIAGNOSTIC TOOLS ==========
    
    diagnosticRFID() {
        console.log('\n========== DIAGNÓSTICO RFID ==========');
        console.log('ChatManager instance:', ChatManager.instance ? 'Existe' : 'NULL');
        console.log('currentUser:', this.currentUser);
        console.log('chatActive:', this.chatActive);
        console.log('rfidPollingInterval:', this.rfidPollingInterval);
        console.log('isTyping:', this.isTyping);
        
        // Testar polling manualmente
        console.log('\nTestando polling RFID manualmente...');
        fetch('/usuarios/rfid/poll')
            .then(r => r.json())
            .then(data => {
                console.log('Resposta do poll:', data);
            })
            .catch(e => {
                console.error('Erro no poll:', e);
            });
        console.log('======================================\n');
    }
}

// Global chat manager instance (Singleton)
let chatManager = null;

function initChatManager() {
    // Limpar instância anterior se existir
    if (chatManager) {
        console.log('Limpando ChatManager anterior...');
        chatManager.destroy();
    }
    
    chatManager = new ChatManager();
    window.chatManager = chatManager; // Expor globalmente para debug
    
    // Expor função de diagnóstico global
    window.diagnosticRFID = () => chatManager.diagnosticRFID();
    console.log('💡 Dica: Execute window.diagnosticRFID() no console para diagnosticar problemas');
    
    return chatManager;
}

// Auto-initialize on DOMContentLoaded (apenas uma vez)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('DOM carregado - inicializando ChatManager...');
        initChatManager();
    });
} else {
    // DOM já está carregado
    console.log('DOM já carregado - inicializando ChatManager...');
    initChatManager();
}
