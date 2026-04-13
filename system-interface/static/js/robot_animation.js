// ========== ROBÔ ANIMADO EXPRESSIVO ==========

// 🔥 OTIMIZAÇÃO: Lookup table pré-calculada para Math.sin() (evita cálculos a cada frame)
const SIN_TABLE = [];
const SIN_TABLE_SIZE = 360;
for (let i = 0; i < SIN_TABLE_SIZE; i++) {
    SIN_TABLE[i] = Math.sin((i * Math.PI) / 180);
}

// Helper rápido para buscar seno
function fastSin(degrees) {
    const index = Math.floor(degrees) % SIN_TABLE_SIZE;
    return SIN_TABLE[index < 0 ? index + SIN_TABLE_SIZE : index];
}

class RobotAvatar {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) {
            console.error(`Canvas ${canvasId} not found`);
            return;
        }
        
        this.ctx = this.canvas.getContext('2d');
        
        // Size modes: 'full' (tela toda) ou 'compact' (metade superior quando chat aberto)
        this.sizeMode = 'full';
        this.targetMode = 'full';
        this.transitionProgress = 1; // 0 to 1
        
        // Estados: idle, listening, thinking, speaking
        this.state = 'idle';
        
        // Emoções: happy, sad, curious, bored, nervous, sleeping
        this.emotion = 'happy';
        this.emotionIntensity = 1.0; // 0 a 1
        
        // Animação de flutuação suave e respiração
        this.floatPhase = 0;
        this.floatOffset = 0;
        this.breathPhase = 0;
        this.breathScale = 1.0;
        
        // 🔥 FIX: Rastrear requestAnimationFrame para cleanup adequado
        this._animationFrameId = null;
        
        // 🔥 OTIMIZAÇÃO: Offscreen canvas para grid (desenhar 1x, reutilizar sempre)
        this._gridCanvas = null;
        this._gridNeedsRedraw = true;
        
        // Inclinação da cabeça
        this.headTilt = 0; // radianos
        this.targetHeadTilt = 0;
        
        // Olhos - animações de piscada e movimento
        this.eyeBlinkTimer = 0;
        this.isBlinking = false;
        this.eyeBlinkDuration = 8;
        this.eyeBlinkProgress = 0;
        this.eyeBrightness = 1.0; // 0 a 1
        
        // Movimento dos olhos
        this.eyeLookDirection = 0; // -1 esquerda, 0 centro, 1 direita
        this.eyeLookY = 0; // Movimento vertical
        this.eyeLookTimer = 0;
        this.eyeFocused = true;
        
        // Idle animations variadas
        this.idleAnimationType = 'normal'; // normal, looking, yawning, sleeping, curious, bored, stretching, looking_around
        this.idleAnimationTimer = 0;
        this.idleAnimationProgress = 0;
        // 🔥 AJUSTADO: Mais frequente (antes: 400-1000, agora: 200-600 frames = ~3-10s)
        this.nextIdleChange = 200 + Math.random() * 400;
        
        // Expressões e emoções
        this.faceExpression = 'happy'; // happy, sad, speaking, thinking, surprised, curious, bored, nervous
        this.eyeEmotionOffset = 0;
        
        // Sistema de inatividade
        this.lastInteractionTime = Date.now();
        // 🔥 AJUSTADO: Tempos aumentados para sincronizar com ChatManager (5min logout)
        this.inactivityThresholds = {
            bored: 90000,      // 90s = 1.5 minutos (antes: 30s)
            sad: 180000,       // 180s = 3 minutos (antes: 60s)
            sleeping: 300000   // 300s = 5 minutos (antes: 120s)
        };
        
        // Boca - sincronização com texto
        this.mouthFrame = 0;
        this.mouthOpenness = 0; // 0 a 1
        this.targetMouthOpenness = 0;
        this.currentSpeakingText = '';
        this.speakingCharIndex = 0;
        
        // Animation frame counter
        this.animationFrame = 0;
        this.isAnimating = true;
        
        // Initialize
        this.resizeCanvas();
        
        // Prevenir múltiplas inicializações
        if (this._resizeListener) {
            window.removeEventListener('resize', this._resizeListener);
        }
        this._resizeListener = () => this.resizeCanvas();
        window.addEventListener('resize', this._resizeListener);
        
        this.animate();
    }
    
    // Método para limpar recursos
    destroy() {
        console.log('🧹 Destruindo RobotAvatar...');
        
        // Parar animação
        this.isAnimating = false;
        
        // 🔥 FIX: Cancelar animation frame pendente para evitar memory leak
        if (this._animationFrameId) {
            cancelAnimationFrame(this._animationFrameId);
            this._animationFrameId = null;
            console.log('✅ Animation frame cancelado');
        }
        
        // Remover event listener de resize
        if (this._resizeListener) {
            window.removeEventListener('resize', this._resizeListener);
            this._resizeListener = null;
            console.log('✅ Resize listener removido');
        }
        
        // Limpar canvas
        if (this.ctx) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }
        
        console.log('✅ RobotAvatar destruído');
    }
    
    resizeCanvas() {
        const newWidth = window.innerWidth;
        const newHeight = window.innerHeight;
        
        // Só redimensionar se realmente mudou (com threshold maior para evitar redimensionamentos mínimos)
        if (Math.abs(this.canvas.width - newWidth) > 20 || Math.abs(this.canvas.height - newHeight) > 20) {
            this.canvas.width = newWidth;
            this.canvas.height = newHeight;
            this.width = newWidth;
            this.height = newHeight;
            
            // 🔥 OTIMIZAÇÃO: Marcar grid para redesenho quando resize acontece
            this._gridNeedsRedraw = true;
        }
    }
    
    setSizeMode(mode) {
        if (this.targetMode !== mode) {
            this.targetMode = mode;
        }
    }
    
    // Função de easing para transição suave
    easeInOutCubic(t) {
        return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }
    
    updateTransition() {
        const speed = 0.04; // Velocidade mais suave e constante
        
        if (this.targetMode === 'compact' && this.transitionProgress > 0) {
            this.transitionProgress = Math.max(0, this.transitionProgress - speed);
        } else if (this.targetMode === 'full' && this.transitionProgress < 1) {
            this.transitionProgress = Math.min(1, this.transitionProgress + speed);
        }
        
        this.sizeMode = this.transitionProgress > 0.5 ? 'full' : 'compact';
    }
    
    setState(newState) {
        // 🆕 AWAKENING: Se estava dormindo e muda estado, animar acordar
        if ((this.emotion === 'sleeping' || this.idleAnimationType === 'sleeping') && newState !== 'idle') {
            this.idleAnimationType = 'awakening';
            this.idleAnimationProgress = 0;
        }
        
        this.state = newState;
        if (newState === 'speaking') {
            this.emotion = 'happy';
            this.faceExpression = 'speaking';
        } else if (newState === 'thinking') {
            this.faceExpression = 'thinking';
            this.targetHeadTilt = 0;
        } else if (newState === 'listening') {
            this.emotion = 'curious';
            this.faceExpression = 'curious';
        } else {
            // Se não estava dormindo, volta ao normal
            if (this.emotion !== 'sleeping') {
                this.emotion = 'happy';
                this.faceExpression = 'happy';
            }
            this.targetHeadTilt = 0;
        }
    }
    
    // Mudar emoção (pode ser chamado externamente)
    setEmotion(emotion, intensity = 1.0) {
        this.emotion = emotion; // happy, sad, curious, bored, nervous, sleeping
        this.emotionIntensity = Math.max(0, Math.min(1, intensity));
        this.faceExpression = emotion;
        this.resetInactivityTimer(); // Resetar timer ao mudar emoção manualmente
    }
    
    // Resetar timer de inatividade
    resetInactivityTimer() {
        this.lastInteractionTime = Date.now();
        this._inactivityPaused = false;  // Despausar se estava pausado
    }
    
    // 🔥 NOVO: Pausar timer de inatividade (sincronização com ChatManager)
    pauseInactivityTimer() {
        this._inactivityPaused = true;
    }
    
    // 🔥 NOVO: Retomar timer de inatividade
    resumeInactivityTimer() {
        this._inactivityPaused = false;
        this.lastInteractionTime = Date.now();  // Reseta ao retomar
    }
    
    // Sincronizar boca com texto sendo falado
    speakText(text) {
        this.currentSpeakingText = text;
        this.speakingCharIndex = 0;
        this.mouthFrame = 0; // Reset frame counter para sincronização correta
        this.state = 'speaking';
        this.faceExpression = 'speaking';
        this.resetInactivityTimer();
    }
    
    stopSpeaking() {
        this.currentSpeakingText = '';
        this.speakingCharIndex = 0;
        this.targetMouthOpenness = 0;
        if (this.state === 'speaking') {
            this.state = 'idle';
            this.faceExpression = 'happy';
        }
    }
    
    // Limpa o texto atual mas mantém o estado speaking (para transições entre frases)
    clearSpeakingText() {
        this.currentSpeakingText = '';
        this.speakingCharIndex = 0;
        // Não muda estado nem targetMouthOpenness - a animação fallback vai continuar
    }
    
    animate() {
        if (!this.isAnimating) return;
        
        try {
            this.animationFrame++;
            
            // Prevenir overflow do contador
            if (this.animationFrame > 1000000) {
                this.animationFrame = 0;
            }
        
        // Update transition animation
        this.updateTransition();
        
        // Floating animation (gentle bobbing) - atualizar a cada 2 frames
        if (this.animationFrame % 2 === 0) {
            this.floatPhase += 0.02;
            this.floatOffset = Math.sin(this.floatPhase) * 6;
        }
        
        // Breathing animation (sutil) - atualizar a cada 2 frames
        if (this.animationFrame % 2 === 0) {
            this.breathPhase += 0.03;
            // 🔥 OTIMIZAÇÃO: Usar lookup table ao invés de Math.sin()
            const breathDegrees = (this.breathPhase * 180) / Math.PI;
            this.breathScale = 1.0 + fastSin(breathDegrees) * 0.01;
        }
        
        // Head tilt smooth transition - mais suave ainda
        this.headTilt += (this.targetHeadTilt - this.headTilt) * 0.08;
        
        // Eye brightness control - atualizar apenas a cada 3 frames
        if (this.animationFrame % 3 === 0) {
            if (this.emotion === 'sleeping') {
                this.eyeBrightness = Math.max(0.3, this.eyeBrightness - 0.02);
            } else if (this.emotion === 'bored') {
                this.eyeBrightness = Math.max(0.6, this.eyeBrightness - 0.01);
            } else if (this.emotion === 'happy' || this.emotion === 'curious') {
                this.eyeBrightness = Math.min(1.0, this.eyeBrightness + 0.02);
            } else {
                this.eyeBrightness = Math.min(0.9, this.eyeBrightness + 0.01);
            }
        }
        
        // Sistema de inatividade - apenas quando em idle E não pausado
        // 🔥 OTIMIZADO: Verificar apenas a cada 60 frames (~1 segundo)
        if (this.state === 'idle' && !this._inactivityPaused && this.animationFrame % 60 === 0) {
            const inactiveTime = Date.now() - this.lastInteractionTime;
            
            // Apenas bored → sleeping (sem sad por inatividade)
            if (inactiveTime > this.inactivityThresholds.sleeping && this.emotion !== 'sleeping') {
                this.setEmotion('sleeping', 1.0);
                this.idleAnimationType = 'sleeping';
                this.idleAnimationProgress = 0;
            } else if (inactiveTime > this.inactivityThresholds.bored && this.emotion !== 'bored' && this.emotion !== 'sleeping') {
                this.setEmotion('bored', 1.0);
                this.idleAnimationType = 'bored';
                this.idleAnimationProgress = 0;
            }
        }
        
        // Blinking animation
        // 🔥 AJUSTADO: Mais frequente e natural (antes: 180-300 frames, agora: 120-240 frames = ~2-4s)
        this.eyeBlinkTimer++;
        if (!this.isBlinking && this.eyeBlinkTimer > 120 + Math.random() * 120) {
            this.isBlinking = true;
            this.eyeBlinkProgress = 0;
            this.eyeBlinkTimer = 0;
        }
        
        if (this.isBlinking) {
            this.eyeBlinkProgress++;
            if (this.eyeBlinkProgress >= this.eyeBlinkDuration * 2) {
                this.isBlinking = false;
                this.eyeBlinkProgress = 0;
            }
        }
        
        // Idle animations (apenas quando não está falando)
        if (this.state === 'idle') {
            this.idleAnimationTimer++;
            
            // Trocar tipo de animação idle aleatoriamente
            // 🔥 AJUSTADO: Mais variado com novas animações
            if (this.idleAnimationTimer >= this.nextIdleChange) {
                // Animações visuais SEM mudar emoção (emoção muda apenas por eventos)
                const rand = Math.random();
                if (rand < 0.35) {
                    this.idleAnimationType = 'normal';
                    this.targetHeadTilt = 0;
                } else if (rand < 0.55) {
                    this.idleAnimationType = 'looking'; // Olhar para os lados
                    this.eyeLookDirection = Math.random() < 0.5 ? -1 : 1;
                    this.targetHeadTilt = this.eyeLookDirection * 0.03;
                } else if (rand < 0.75) {
                    this.idleAnimationType = 'curious'; // Curioso
                    this.targetHeadTilt = 0.04;
                    this.eyeLookDirection = 0.5;
                    this.idleAnimationProgress = 0;
                } else {
                    this.idleAnimationType = 'looking_around';
                    this.idleAnimationProgress = 0;
                }
                
                // Animações especiais para estados específicos
                if (this.emotion === 'bored') {
                    this.idleAnimationType = 'bored';
                    this.targetHeadTilt = 0.05;
                    this.idleAnimationProgress = 0;
                } else if (this.emotion === 'sleeping') {
                    this.idleAnimationType = 'sleeping';
                    this.idleAnimationProgress = 0;
                    this.targetHeadTilt = 0.04;
                }
                
                this.idleAnimationTimer = 0;
                // 🔥 AJUSTADO: Mais frequente (antes: 400-1200, agora: 200-600)
                this.nextIdleChange = 200 + Math.random() * 400;
            }
            
            // Executar animação idle atual
            if (this.idleAnimationType === 'looking') {
                this.eyeLookTimer++;
                // 🔥 AJUSTADO: Movimento mais rápido (antes: 80/120, agora: 50/80 frames)
                if (this.eyeLookTimer > 50) {
                    this.eyeLookDirection *= 0.9; // Volta gradualmente
                    this.targetHeadTilt *= 0.95;
                    if (this.eyeLookTimer > 80) {
                        this.idleAnimationType = 'normal';
                        this.eyeLookTimer = 0;
                        this.eyeLookDirection = 0;
                        this.targetHeadTilt = 0;
                    }
                }
            } else if (this.idleAnimationType === 'curious') {
                this.idleAnimationProgress++;
                // 🔥 AJUSTADO: Movimento mais dinâmico (frequência aumentada)
                this.eyeLookDirection = Math.sin(this.idleAnimationProgress * 0.08) * 0.7;
                this.eyeLookY = Math.cos(this.idleAnimationProgress * 0.05) * 0.3;
                // 🔥 AJUSTADO: Duração reduzida (antes: 200, agora: 150 frames)
                if (this.idleAnimationProgress > 150) {
                    this.idleAnimationType = 'normal';
                    this.idleAnimationProgress = 0;
                    this.eyeLookDirection = 0;
                    this.eyeLookY = 0;
                    this.targetHeadTilt = 0;
                }
            } else if (this.idleAnimationType === 'bored') {
                this.idleAnimationProgress++;
                // Micro movimentos repetitivos mais suaves
                this.targetHeadTilt = 0.05 + Math.sin(this.idleAnimationProgress * 0.02) * 0.015;
                if (this.idleAnimationProgress > 250) {
                    this.idleAnimationType = 'normal';
                    this.idleAnimationProgress = 0;
                    this.targetHeadTilt = 0;
                }
            } else if (this.idleAnimationType === 'looking_around') {
                // 🆕 NOVA ANIMAÇÃO: Looking Around (olhando ao redor)
                this.idleAnimationProgress++;
                // Sequência: centro → esquerda → centro → direita → centro
                const cycle = this.idleAnimationProgress % 200;
                if (cycle < 50) {
                    // Olha para esquerda
                    this.eyeLookDirection = -Math.min(1, cycle / 25);
                    this.targetHeadTilt = -0.03 * Math.min(1, cycle / 25);
                } else if (cycle < 100) {
                    // Volta ao centro
                    this.eyeLookDirection = -1 + Math.min(1, (cycle - 50) / 25);
                    this.targetHeadTilt = -0.03 + 0.03 * Math.min(1, (cycle - 50) / 25);
                } else if (cycle < 150) {
                    // Olha para direita
                    this.eyeLookDirection = Math.min(1, (cycle - 100) / 25);
                    this.targetHeadTilt = 0.03 * Math.min(1, (cycle - 100) / 25);
                } else {
                    // Volta ao centro
                    this.eyeLookDirection = 1 - Math.min(1, (cycle - 150) / 25);
                    this.targetHeadTilt = 0.03 - 0.03 * Math.min(1, (cycle - 150) / 25);
                }
                if (this.idleAnimationProgress > 200) {
                    this.idleAnimationType = 'normal';
                    this.idleAnimationProgress = 0;
                    this.eyeLookDirection = 0;
                    this.targetHeadTilt = 0;
                }
            } else if (this.idleAnimationType === 'sleeping') {
                this.idleAnimationProgress++;
                if (this.idleAnimationProgress > 400) {
                    this.idleAnimationType = 'normal';
                    this.idleAnimationProgress = 0;
                    this.targetHeadTilt = 0;
                }
            } else if (this.idleAnimationType === 'awakening') {
                // 🆕 NOVA ANIMAÇÃO: Awakening (acordando)
                this.idleAnimationProgress++;
                
                // Transição gradual de sleeping para happy
                const progress = Math.min(1, this.idleAnimationProgress / 60);
                
                // Olhos abrindo gradualmente (simula piscada lenta)
                this.eyeBrightness = 0.3 + (progress * 0.7);
                
                // Bocejo sutil no início
                if (this.idleAnimationProgress < 30) {
                    this.targetMouthOpenness = Math.sin(this.idleAnimationProgress * 0.1) * 0.3;
                }
                
                // Movimento de cabeça (espreguiçando)
                this.targetHeadTilt = Math.sin(this.idleAnimationProgress * 0.15) * 0.05;
                
                if (this.idleAnimationProgress > 60) {
                    this.idleAnimationType = 'normal';
                    this.emotion = 'happy';
                    this.idleAnimationProgress = 0;
                    this.targetHeadTilt = 0;
                    this.targetMouthOpenness = 0;
                    this.eyeBrightness = 1.0;
                }
            }
        } else if (this.state === 'thinking') {
            this.idleAnimationType = 'normal';
            this.idleAnimationProgress = 0;
            this.eyeLookTimer = 0;

            const thinkingPhase = this.animationFrame * 0.08;
            this.eyeLookDirection = 0.12 + Math.sin(thinkingPhase) * 0.1;
            this.eyeLookY = -0.3 + Math.cos(thinkingPhase * 0.7) * 0.045;
            this.targetHeadTilt = 0;
        } else {
            // Reset idle quando não está idle
            this.idleAnimationType = 'normal';
            this.idleAnimationProgress = 0;
            this.eyeLookDirection = 0;
            this.eyeLookY = 0;
            this.eyeLookTimer = 0;
            this.targetHeadTilt = 0;
        }
        
        // Mouth animation for speaking
        if (this.state === 'speaking') {
            this.mouthFrame++;
            
            if (this.currentSpeakingText) {
                // Advance through speaking text character by character
                if (this.mouthFrame % 2 === 0) {
                    this.speakingCharIndex++;
                    if (this.speakingCharIndex >= this.currentSpeakingText.length) {
                        this.speakingCharIndex = 0;
                    }
                }
                
                // Animate mouth based on character
                const char = this.currentSpeakingText[this.speakingCharIndex] || '';
                const isVowel = 'aeiouAEIOU'.includes(char);
                const isPunctuation = '.!?,;'.includes(char);
                
                if (isPunctuation) {
                    this.targetMouthOpenness = 0;
                } else if (isVowel) {
                    this.targetMouthOpenness = 0.7 + Math.random() * 0.3;
                } else {
                    this.targetMouthOpenness = 0.2 + Math.random() * 0.3;
                }
            } else {
                // Fallback: animate mouth with sine wave when no text available
                // This keeps the mouth moving naturally even without specific text
                const sineValue = Math.sin(this.mouthFrame * 0.15);
                this.targetMouthOpenness = 0.3 + (sineValue + 1) * 0.35; // Range: 0.3 to 1.0
            }
        } else {
            this.targetMouthOpenness = 0;
        }
        
        // Smooth mouth transition
        this.mouthOpenness += (this.targetMouthOpenness - this.mouthOpenness) * 0.15; // Transição mais suave
        
        // Scanline offset removido (não usado mais)
        
        this.draw();
        
        } catch (error) {
            console.error('Erro na animação do robô:', error);
            // Continuar animando mesmo com erro
        } finally {
            // 🔥 FIX: Armazenar ID do frame para poder cancelar depois
            if (this.isAnimating) {
                this._animationFrameId = requestAnimationFrame(() => this.animate());
            }
        }
    }
    
    draw() {
        // Validação: canvas existe e tem tamanho válido
        if (!this.canvas || !this.ctx || this.width <= 0 || this.height <= 0) {
            return;
        }
        
        try {
            // Clear canvas with black background
            this.ctx.fillStyle = '#000000';
            this.ctx.fillRect(0, 0, this.width, this.height);
            
            // Desenhar grade simples e estática no fundo para decoração leve
            this.drawSimpleGrid();
        
        // Aplicar easing para transição suave
        const easedProgress = this.easeInOutCubic(this.transitionProgress);
        
        // Calculate BMO face size based on mode
        let faceWidth, faceHeight;
        
        // Tamanhos base
        const maxSizeFull = Math.min(this.width * 1.1, this.height * 1.1); // 110% no modo full
        const maxSizeCompact = Math.min(this.width * 0.35, this.height * 0.35); // 35% no modo compact
        
        // Interpolação suave entre os tamanhos usando easing
        const targetSize = maxSizeFull * easedProgress + maxSizeCompact * (1 - easedProgress);
        faceWidth = targetSize;
        faceHeight = faceWidth * 0.75; // BMO face aspect ratio
        
        // Position BMO face
        const centerX = this.width / 2;
        let centerY;
        
        // Posições base
        const fullModeY = this.height / 2;
        const compactModeY = this.height * 0.18; // 18% do topo no modo compact
        
        // Interpolate position based on eased transition progress
        centerY = fullModeY * easedProgress + compactModeY * (1 - easedProgress);
        centerY += this.floatOffset * (0.3 + easedProgress * 0.7); // Scale float effect
        
        this.ctx.save();
        this.ctx.translate(centerX, centerY);
        
        // Aplicar inclinação da cabeça e respiração
        this.ctx.rotate(this.headTilt);
        this.ctx.scale(this.breathScale, this.breathScale);
        
        // Draw robot face
        this.drawRobotCase(faceWidth, faceHeight);
        this.drawScreen(faceWidth, faceHeight);
        this.drawFace(faceWidth, faceHeight);
        // Scanlines removidas para performance
        
        this.ctx.restore();
        
        } catch (drawError) {
            console.error('Erro ao desenhar robô:', drawError);
            // Restaurar contexto em caso de erro
            try {
                this.ctx.restore();
            } catch (e) {
                // Ignora erro de restore
            }
        }
    }
    
    drawSimpleGrid() {
        // Grade simples e estática para decoração do fundo
        this.ctx.strokeStyle = 'rgba(0, 255, 0, 0.05)'; // Verde muito transparente
        this.ctx.lineWidth = 1;
        
        const gridSize = 50; // Espaçamento da grade
        
        // Linhas verticais
        for (let x = 0; x < this.width; x += gridSize) {
            this.ctx.beginPath();
            this.ctx.moveTo(x, 0);
            this.ctx.lineTo(x, this.height);
            this.ctx.stroke();
        }
        
        // Linhas horizontais
        for (let y = 0; y < this.height; y += gridSize) {
            this.ctx.beginPath();
            this.ctx.moveTo(0, y);
            this.ctx.lineTo(this.width, y);
            this.ctx.stroke();
        }
    }
    
    drawRobotCase(w, h) {
        const caseX = -w / 2;
        const caseY = -h / 2;
        
        // Outer case - retro TV style
        this.ctx.fillStyle = '#001100';
        this.ctx.strokeStyle = '#00ff00';
        this.ctx.lineWidth = 5;
        
        this.roundRect(caseX - 15, caseY - 15, w + 30, h + 30, 25);
        this.ctx.fill();
        this.ctx.stroke();
        
        // Inner bezel
        this.ctx.strokeStyle = '#00cc00';
        this.ctx.lineWidth = 3;
        this.roundRect(caseX - 8, caseY - 8, w + 16, h + 16, 18);
        this.ctx.stroke();
    }
    
    roundRect(x, y, width, height, radius) {
        this.ctx.beginPath();
        this.ctx.moveTo(x + radius, y);
        this.ctx.lineTo(x + width - radius, y);
        this.ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        this.ctx.lineTo(x + width, y + height - radius);
        this.ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
        this.ctx.lineTo(x + radius, y + height);
        this.ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
        this.ctx.lineTo(x, y + radius);
        this.ctx.quadraticCurveTo(x, y, x + radius, y);
        this.ctx.closePath();
    }
    
    drawScreen(w, h) {
        const screenX = -w / 2;
        const screenY = -h / 2;
        
        // Fundo simples e estático
        this.ctx.fillStyle = '#003300';
        this.roundRect(screenX, screenY, w, h, 12);
        this.ctx.fill();
        
        // Borda interna sutil para dar profundidade
        this.ctx.strokeStyle = 'rgba(0, 100, 0, 0.3)';
        this.ctx.lineWidth = 2;
        this.roundRect(screenX + 5, screenY + 5, w - 10, h - 10, 8);
        this.ctx.stroke();
    }
    
    drawFace(w, h) {
        // Eyes
        this.drawEyes(w, h);
        
        // Mouth
        this.drawMouth(w, h);

        // Efeito visual de "ideia surgindo" durante o pensamento
        if (this.state === 'thinking') {
            this.drawThinkingIdea(w, h);
        }
    }
    
    drawEyes(w, h) {
        const baseEyeY = -h * 0.15;
        const eyeSpacing = w * 0.18;
        let eyeWidth = w * 0.038; // Reduzido de 0.04
        let eyeHeight = w * 0.062; // Reduzido de 0.065
        
        // Movimento dos olhos
        const eyeOffsetX = this.eyeLookDirection * (w * 0.03);
        const eyeOffsetY = this.eyeLookY * (h * 0.02);
        const eyeY = baseEyeY + eyeOffsetY;
        
        // Cor verde
        const eyeColor = `rgba(0, 255, 0, ${this.eyeBrightness})`;
        
        // === DORMINDO ===
        if (this.emotion === 'sleeping' || this.idleAnimationType === 'sleeping') {
            this.ctx.strokeStyle = eyeColor;
            this.ctx.lineWidth = 4;
            this.ctx.shadowColor = '#00ff00';
            this.ctx.shadowBlur = 10 * this.eyeBrightness;
            
            // Olhos fechados - linhas horizontais
            this.ctx.beginPath();
            this.ctx.moveTo(-eyeSpacing - eyeWidth + eyeOffsetX, eyeY);
            this.ctx.lineTo(-eyeSpacing + eyeWidth + eyeOffsetX, eyeY);
            this.ctx.stroke();
            
            this.ctx.beginPath();
            this.ctx.moveTo(eyeSpacing - eyeWidth + eyeOffsetX, eyeY);
            this.ctx.lineTo(eyeSpacing + eyeWidth + eyeOffsetX, eyeY);
            this.ctx.stroke();
            
            // Z z z flutuando
            this.ctx.font = `${w * 0.04}px monospace`;
            this.ctx.fillStyle = eyeColor;
            const floatZ = Math.sin(this.idleAnimationProgress * 0.08) * 8;
            this.ctx.fillText('Z', w * 0.25, -h * 0.28 + floatZ);
            this.ctx.fillText('z', w * 0.28, -h * 0.32 + floatZ * 0.7);
            this.ctx.fillText('z', w * 0.3, -h * 0.35 + floatZ * 0.5);
            
            this.ctx.shadowBlur = 0;
            return;
        }
        
        // === TRISTE ===
        let eyeShapeModifier = 1.0;
        if (this.emotion === 'sad') {
            eyeHeight *= 0.7; // Olhos menores e mais fechados
            eyeWidth *= 0.85;
            eyeShapeModifier = 0.7; // Semicerrados
        }
        
        // === NERVOSO ===
        let nervousTremor = 0;
        if (this.emotion === 'nervous') {
            // Tremor sutil
            nervousTremor = Math.sin(this.animationFrame * 0.3) * 2;
        }
        
        // === ENTEDIADO ===
        if (this.emotion === 'bored' || this.idleAnimationType === 'bored') {
            eyeShapeModifier = 0.5; // Semicerrados
        }

        // === PENSANDO ===
        if (this.state === 'thinking') {
            eyeHeight *= 0.84;
            eyeWidth *= 1.08;
            eyeShapeModifier = 0.78 + Math.sin(this.animationFrame * 0.08) * 0.07;
        }
        
        // Piscar
        let eyeScaleY = eyeShapeModifier;
        if (this.isBlinking) {
            const blinkProgress = this.eyeBlinkProgress / this.eyeBlinkDuration;
            let blinkAmount;
            if (blinkProgress < 1) {
                blinkAmount = 1 - blinkProgress;
            } else {
                blinkAmount = blinkProgress - 1;
            }
            eyeScaleY *= Math.max(0.1, blinkAmount);
        }
        
        // Desenhar olhos OVAIS VERTICAIS
        this.ctx.fillStyle = eyeColor;
        this.ctx.shadowColor = '#00ff00';
        this.ctx.shadowBlur = 15 * this.eyeBrightness; // Reduzido de 20 para 15
        
        // === CURIOSO - olhos ligeiramente maiores ===
        if (this.emotion === 'curious' || this.idleAnimationType === 'curious') {
            eyeHeight *= 1.15;
            eyeWidth *= 1.1;
        }
        
        // Olho esquerdo - OVAL VERTICAL
        this.ctx.save();
        this.ctx.translate(-eyeSpacing + eyeOffsetX + nervousTremor, eyeY);
        
        this.ctx.beginPath();
        this.ctx.ellipse(0, 0, eyeWidth, eyeHeight * eyeScaleY, 0, 0, Math.PI * 2);
        this.ctx.closePath();
        this.ctx.fill();
        
        this.ctx.restore();
        
        // Olho direito - OVAL VERTICAL
        this.ctx.save();
        this.ctx.translate(eyeSpacing + eyeOffsetX + nervousTremor, eyeY);
        
        this.ctx.beginPath();
        this.ctx.ellipse(0, 0, eyeWidth, eyeHeight * eyeScaleY, 0, 0, Math.PI * 2);
        this.ctx.closePath();
        this.ctx.fill();
        
        this.ctx.restore();
        
        this.ctx.shadowBlur = 0;

        // Sobrancelhas no estado de pensamento
        if (this.state === 'thinking') {
            const browY = eyeY - eyeHeight * 1.35;
            const browHalf = eyeWidth * 1.32;
            const browPulse = Math.sin(this.animationFrame * 0.1) * 0.65;

            this.ctx.strokeStyle = eyeColor;
            this.ctx.lineWidth = 2;
            this.ctx.shadowColor = '#00ff00';
            this.ctx.shadowBlur = 5;

            this.ctx.beginPath();
            this.ctx.moveTo(-eyeSpacing - browHalf, browY + 1 + browPulse);
            this.ctx.quadraticCurveTo(-eyeSpacing, browY - 2.2 + browPulse, -eyeSpacing + browHalf, browY + 1 + browPulse);
            this.ctx.stroke();

            this.ctx.beginPath();
            this.ctx.moveTo(eyeSpacing - browHalf, browY + 1 + browPulse);
            this.ctx.quadraticCurveTo(eyeSpacing, browY - 2.2 + browPulse, eyeSpacing + browHalf, browY + 1 + browPulse);
            this.ctx.stroke();

            this.ctx.shadowBlur = 0;
        }
    }
    
    drawMouth(w, h) {
        const baseMouthY = h * 0.14;
        let mouthWidth = w * 0.08;
        let mouthY = baseMouthY;
        
        const mouthColor = `rgba(0, 255, 0, ${this.eyeBrightness})`;
        this.ctx.strokeStyle = mouthColor;
        this.ctx.fillStyle = mouthColor;
        this.ctx.lineWidth = 4;
        this.ctx.lineCap = 'round';
        this.ctx.shadowColor = '#00ff00';
        this.ctx.shadowBlur = 15;
        
        this.ctx.beginPath();
        
        // === FALANDO === (prioridade máxima - deve vir primeiro!)
        if (this.state === 'speaking') {
            const openAmount = this.mouthOpenness;
            
            // Boca oval que abre e fecha naturalmente
            const mouthWidthSpeaking = mouthWidth * 1.5;
            const mouthHeightSpeaking = mouthWidth * (0.3 + openAmount * 0.8); // Altura varia com abertura
            
            this.ctx.lineWidth = 3;
            this.ctx.beginPath();
            this.ctx.ellipse(0, mouthY, mouthWidthSpeaking, mouthHeightSpeaking, 0, 0, Math.PI * 2);
            this.ctx.stroke();
            
            // Adicionar linha interna quando muito aberto para efeito de profundidade
            if (openAmount > 0.5) {
                this.ctx.globalAlpha = openAmount * 0.6;
                this.ctx.beginPath();
                this.ctx.ellipse(0, mouthY + mouthHeightSpeaking * 0.3, mouthWidthSpeaking * 0.6, mouthHeightSpeaking * 0.4, 0, 0, Math.PI * 2);
                this.ctx.fill();
                this.ctx.globalAlpha = 1.0;
            }
        }
        // === PENSANDO ===
        else if (this.state === 'thinking') {
            const thoughtWave = Math.sin(this.animationFrame * 0.1) * 0.9;
            const mouthTension = Math.sin(this.animationFrame * 0.06) * 0.4;
            this.ctx.lineWidth = 3;
            this.ctx.moveTo(-mouthWidth * 0.58, mouthY + 1.2);
            this.ctx.quadraticCurveTo(
                0,
                mouthY - 2 + thoughtWave - mouthTension,
                mouthWidth * 0.58,
                mouthY + 1.2
            );
            this.ctx.stroke();
        }
        // Dormindo
        else if (this.emotion === 'sleeping' || this.idleAnimationType === 'sleeping') {
            // Boca pequena e relaxada
            this.ctx.moveTo(-mouthWidth * 0.6, mouthY);
            this.ctx.lineTo(mouthWidth * 0.6, mouthY);
            this.ctx.stroke();
        }
        // === TRISTE ===
        else if (this.emotion === 'sad') {
            // Boca virada para baixo (arco invertido)
            this.ctx.arc(0, mouthY + mouthWidth * 0.8, mouthWidth * 1.0, Math.PI, Math.PI * 2, false);
            this.ctx.stroke();
        }
        // === NERVOSO ===
        else if (this.emotion === 'nervous') {
            // Boca pequena e tensa
            mouthWidth *= 0.7;
            this.ctx.moveTo(-mouthWidth, mouthY);
            this.ctx.lineTo(mouthWidth, mouthY);
            this.ctx.stroke();
        }
        // === ENTEDIADO ===
        else if (this.emotion === 'bored' || this.idleAnimationType === 'bored') {
            // Boca reta ou levemente caída
            this.ctx.moveTo(-mouthWidth, mouthY - 2);
            this.ctx.lineTo(mouthWidth, mouthY + 2);
            this.ctx.stroke();
        }
        // === CURIOSO ===
        else if (this.emotion === 'curious' || this.idleAnimationType === 'curious') {
            // Boca pequena em "o"
            this.ctx.arc(0, mouthY, mouthWidth * 0.6, 0, Math.PI * 2, false);
            this.ctx.stroke();
        }
        // === FELIZ (padrão) ===
        else {
            // Sorriso largo e amigável
            this.ctx.arc(0, mouthY - mouthWidth * 0.4, mouthWidth * 1.1, 0, Math.PI, false);
            this.ctx.fill();
        }
        
        this.ctx.shadowBlur = 0;
    }

    drawThinkingIdea(w, h) {
        const cycleFrames = 180;
        const t = (this.animationFrame % cycleFrames) / cycleFrames;
        const appear = Math.min(1, t / 0.35);
        const disappear = t > 0.85 ? Math.max(0, 1 - (t - 0.85) / 0.15) : 1;
        const alpha = appear * disappear;
        if (alpha <= 0) return;

        const pulse = (Math.sin(this.animationFrame * 0.2) + 1) / 2;
        const tailBaseX = w * 0.16;
        const tailBaseY = -h * 0.1;
        const cloudX = w * 0.3;
        const cloudY = -h * 0.34 + Math.sin(this.animationFrame * 0.07) * 1.5;
        const cloudScale = (0.82 + pulse * 0.06) * appear;

        // Bolhinhas do balão (ligação cabeça -> nuvem)
        const tailBubbles = [
            { x: tailBaseX, y: tailBaseY, r: w * 0.009, threshold: 0.05 },
            { x: w * 0.2, y: -h * 0.17, r: w * 0.013, threshold: 0.12 },
            { x: w * 0.245, y: -h * 0.245, r: w * 0.017, threshold: 0.2 }
        ];
        this.ctx.save();
        for (const b of tailBubbles) {
            const vis = Math.max(0, Math.min(1, (appear - b.threshold) / 0.2)) * disappear;
            if (vis <= 0) continue;
            this.ctx.beginPath();
            this.ctx.fillStyle = `rgba(0, 255, 0, ${0.14 + vis * 0.38})`;
            this.ctx.shadowColor = '#00ff00';
            this.ctx.shadowBlur = 4 + vis * 6;
            this.ctx.arc(b.x, b.y, b.r * (0.92 + pulse * 0.08), 0, Math.PI * 2);
            this.ctx.fill();
        }
        this.ctx.restore();

        // Nuvem do balão
        const lobes = [
            { x: -w * 0.038, y: 0, r: w * 0.045 },
            { x: 0, y: -h * 0.02, r: w * 0.058 },
            { x: w * 0.045, y: -h * 0.002, r: w * 0.043 },
            { x: w * 0.012, y: h * 0.022, r: w * 0.052 }
        ];

        this.ctx.save();
        this.ctx.translate(cloudX, cloudY);
        this.ctx.scale(cloudScale, cloudScale);
        this.ctx.shadowColor = '#00ff00';
        this.ctx.shadowBlur = 9 + pulse * 5;

        for (const l of lobes) {
            this.ctx.beginPath();
            this.ctx.fillStyle = `rgba(0, 255, 0, ${(0.12 + pulse * 0.05) * alpha})`;
            this.ctx.arc(l.x, l.y, l.r, 0, Math.PI * 2);
            this.ctx.fill();
        }
        for (const l of lobes) {
            this.ctx.beginPath();
            this.ctx.strokeStyle = `rgba(0, 255, 0, ${(0.55 + pulse * 0.25) * alpha})`;
            this.ctx.lineWidth = 1.7 / Math.max(cloudScale, 0.001);
            this.ctx.arc(l.x, l.y, l.r, 0, Math.PI * 2);
            this.ctx.stroke();
        }

        // Lâmpada verde dentro do balão
        const bulbR = w * 0.046 * (0.95 + pulse * 0.1);

        // Fundo interno mais escuro para destacar a lampada dentro da nuvem
        this.ctx.beginPath();
        this.ctx.fillStyle = `rgba(0, 90, 0, ${0.35 * alpha})`;
        this.ctx.arc(0, 0, bulbR * 1.55, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.beginPath();
        this.ctx.fillStyle = `rgba(0, 255, 0, ${(0.3 + pulse * 0.16) * alpha})`;
        this.ctx.arc(0, 0, bulbR * 1.45, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.beginPath();
        this.ctx.shadowColor = '#00ff00';
        this.ctx.shadowBlur = 14 + pulse * 10;
        this.ctx.fillStyle = `rgba(110, 255, 110, ${0.86 * alpha})`;
        this.ctx.strokeStyle = `rgba(180, 255, 180, ${alpha})`;
        this.ctx.lineWidth = 2.5 / Math.max(cloudScale, 0.001);
        this.ctx.ellipse(0, -bulbR * 0.06, bulbR * 0.68, bulbR * 0.8, 0, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.stroke();

        this.ctx.beginPath();
        this.ctx.strokeStyle = `rgba(180, 255, 180, ${alpha})`;
        this.ctx.lineWidth = 2.1 / Math.max(cloudScale, 0.001);
        this.ctx.moveTo(-bulbR * 0.22, bulbR * 0.62);
        this.ctx.lineTo(bulbR * 0.22, bulbR * 0.62);
        this.ctx.moveTo(-bulbR * 0.16, bulbR * 0.82);
        this.ctx.lineTo(bulbR * 0.16, bulbR * 0.82);
        this.ctx.stroke();

        this.ctx.beginPath();
        this.ctx.strokeStyle = `rgba(110, 255, 110, ${alpha})`;
        this.ctx.lineWidth = 1.9 / Math.max(cloudScale, 0.001);
        this.ctx.moveTo(-bulbR * 0.17, bulbR * 0.18);
        this.ctx.lineTo(-bulbR * 0.04, bulbR * 0.32);
        this.ctx.lineTo(bulbR * 0.04, bulbR * 0.18);
        this.ctx.lineTo(bulbR * 0.17, bulbR * 0.32);
        this.ctx.stroke();

        // Brilho interno visivel
        this.ctx.beginPath();
        this.ctx.fillStyle = `rgba(200, 255, 200, ${0.5 * alpha})`;
        this.ctx.arc(-bulbR * 0.18, -bulbR * 0.26, bulbR * 0.17, 0, Math.PI * 2);
        this.ctx.fill();

        const rayCount = 6;
        for (let i = 0; i < rayCount; i++) {
            const angle = (Math.PI * 2 * i) / rayCount + this.animationFrame * 0.035;
            const rayStart = bulbR * 1.08;
            const rayEnd = rayStart + bulbR * (0.34 + pulse * 0.45);
            this.ctx.beginPath();
            this.ctx.strokeStyle = `rgba(0, 255, 0, ${(0.38 + pulse * 0.42) * alpha})`;
            this.ctx.lineWidth = 1.6 / Math.max(cloudScale, 0.001);
            this.ctx.moveTo(Math.cos(angle) * rayStart, Math.sin(angle) * rayStart);
            this.ctx.lineTo(Math.cos(angle) * rayEnd, Math.sin(angle) * rayEnd);
            this.ctx.stroke();
        }

        this.ctx.restore();
    }
    
    drawScanlines(w, h) {
        // CRT scanline effect - otimizado com menos linhas
        this.ctx.strokeStyle = 'rgba(0, 255, 0, 0.03)';
        this.ctx.lineWidth = 1;
        
        const screenX = -w / 2;
        const screenY = -h / 2;
        
        // Desenhar apenas a cada 6px para melhor performance
        for (let y = 0; y < h; y += 6) {
            const actualY = screenY + y + (this.scanlineOffset % 6);
            this.ctx.beginPath();
            this.ctx.moveTo(screenX, actualY);
            this.ctx.lineTo(screenX + w, actualY);
            this.ctx.stroke();
        }
    }
}

// Initialize robot avatar when DOM is ready
let robotAvatar;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        robotAvatar = new RobotAvatar('robot-canvas');
        window.robotAvatar = robotAvatar;
    });
} else {
    robotAvatar = new RobotAvatar('robot-canvas');
    window.robotAvatar = robotAvatar;
}
