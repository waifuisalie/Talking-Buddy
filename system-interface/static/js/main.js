// ========== MATRIX RAIN EFFECT ==========

// 🔥 OTIMIZAÇÃO: Variável global para limpar interval
let matrixRainInterval = null;

function initMatrixRain() {
    const canvas = document.getElementById('matrix-canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    
    // Configura o tamanho do canvas
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    
    // Caracteres para o efeito
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*';
    const fontSize = 14;
    const columns = canvas.width / fontSize;
    
    // Array para armazenar a posição Y de cada coluna
    const drops = [];
    for (let i = 0; i < columns; i++) {
        drops[i] = Math.random() * -100;
    }
    
    // Função de desenho
    function draw() {
        // Fundo semi-transparente para criar o efeito de trilha
        ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Texto verde
        ctx.fillStyle = '#00ff00';
        ctx.font = fontSize + 'px Courier New';
        
        // Loop pelas colunas
        for (let i = 0; i < drops.length; i++) {
            // Caractere aleatório
            const text = chars[Math.floor(Math.random() * chars.length)];
            
            // Desenha o caractere
            ctx.fillText(text, i * fontSize, drops[i] * fontSize);
            
            // Reseta a posição quando chega ao fim ou aleatoriamente
            if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                drops[i] = 0;
            }
            
            // Incrementa Y
            drops[i]++;
        }
    }
    
    // 🔥 OTIMIZAÇÃO: Limpar interval anterior antes de criar novo
    if (matrixRainInterval) {
        clearInterval(matrixRainInterval);
    }
    
    // Animação
    matrixRainInterval = setInterval(draw, 33);
    
    // Redimensiona o canvas quando a janela muda de tamanho
    window.addEventListener('resize', () => {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    });
}


// ========== VARIÁVEIS GLOBAIS ==========

let currentInput = null;
let currentValue = '';
let isShiftActive = false;


// ========== FUNÇÕES DE INTERNACIONALIZAÇÃO DO TECLADO ==========

/**
 * 🌐 Atualiza todos os textos do teclado virtual com base no idioma atual
 * Chamado ao abrir o teclado e quando o idioma muda
 */
function updateKeyboardLanguage() {
    if (!window.i18n) {
        console.warn('[Keyboard] i18n não disponível ainda');
        return;
    }
    
    console.log('[Keyboard] 🌐 Atualizando idioma do teclado para:', window.i18n.getCurrentLanguage());
    
    // Atualiza todos os elementos com data-i18n-text dentro do teclado
    const keyboardElements = document.querySelectorAll('#virtual-keyboard [data-i18n-text]');
    keyboardElements.forEach(element => {
        const key = element.getAttribute('data-i18n-text');
        if (key) {
            element.textContent = window.i18n.t(key);
        }
    });
}


// ========== POPUP PERSONALIZADO ==========

function showPopup(message) {
    const popup = document.getElementById('custom-popup');
    const messageEl = document.getElementById('popup-message');
    messageEl.textContent = message;
    popup.classList.add('active');
}

function closePopup() {
    const popup = document.getElementById('custom-popup');
    popup.classList.remove('active');
}

// Substituir alert global
window.alert = showPopup;


// ========== INICIALIZAÇÃO ==========

document.addEventListener('DOMContentLoaded', () => {
    initMatrixRain();
    initializeInputs();
    initializeKeyboard();
    
    // 🌐 Listener para mudança de idioma (quando usuário faz login)
    window.addEventListener('languageChanged', () => {
        console.log('[main.js] 🌐 Idioma mudou, atualizando teclado...');
        updateKeyboardLanguage();
    });
});


// ========== GERENCIAMENTO DE INPUTS ==========

function initializeInputs() {
    // Adiciona event listeners em todos os inputs com keyboard-trigger
    const inputs = document.querySelectorAll('input.keyboard-trigger');
    
    inputs.forEach(input => {
        input.addEventListener('click', (e) => {
            e.preventDefault();
            openKeyboard(input);
        });
        
        // Torna readonly para forçar uso do teclado
        input.setAttribute('readonly', 'readonly');
    });
}

function openKeyboard(inputElement) {
    console.log('[Keyboard] 🔓 Abrindo teclado para:', inputElement.id || inputElement.name);
    
    currentInput = inputElement;
    currentValue = inputElement.value || '';
    
    // Mostra o teclado
    const keyboard = document.getElementById('virtual-keyboard');
    keyboard.classList.add('active');
    
    // 🌐 ATUALIZA IDIOMA DO TECLADO antes de mostrar
    updateKeyboardLanguage();
    
    // Atualiza o título do teclado baseado no campo
    updateKeyboardTitle(inputElement);
    
    // 🔥 CORREÇÃO: Atualiza o display DUAS VEZES para garantir
    // Primeira atualização: Imediata
    updateKeyboardDisplay();
    
    // Segunda atualização: Após pequeno delay (garante que DOM está pronto)
    setTimeout(() => {
        console.log('[Keyboard] 🔄 Segunda atualização (fallback safety)');
        updateKeyboardDisplay();
        
        // 🔥 GARANTIA: Verificar se cursor está visível
        const cursorElement = document.querySelector('.cursor');
        if (cursorElement) {
            console.log('[Keyboard] ✅ Cursor encontrado e visível');
        } else {
            console.warn('[Keyboard] ⚠️ Cursor não encontrado no DOM!');
        }
    }, 100);
    
    // Focus no input (visual)
    inputElement.classList.add('active');
}

function closeKeyboard() {
    const keyboard = document.getElementById('virtual-keyboard');
    keyboard.classList.remove('active');
    
    // Remove focus visual
    if (currentInput) {
        currentInput.classList.remove('active');
    }
    
    // Reseta estado
    currentInput = null;
    currentValue = '';
    isShiftActive = false;
    updateShiftKeys();
}

function confirmKeyboard() {
    if (currentInput) {
        currentInput.value = currentValue;
        
        // Dispara evento de mudança
        const event = new Event('change', { bubbles: true });
        currentInput.dispatchEvent(event);
    }
    
    closeKeyboard();
}


// ========== FUNCIONALIDADES DO TECLADO ==========

function initializeKeyboard() {
    // Event listeners para as teclas
    const keys = document.querySelectorAll('.key');
    
    keys.forEach(key => {
        key.addEventListener('click', function() {
            const keyValue = this.getAttribute('data-key');
            
            if (keyValue === 'shift') {
                toggleShift();
            } else if (keyValue === 'backspace') {
                backspace();
            } else if (keyValue === 'space') {
                typeKey(' ');
            } else {
                typeKey(keyValue);
            }
        });
    });
}

function typeKey(char) {
    if (isShiftActive) {
        char = char.toUpperCase();
        toggleShift(); // Desativa shift após usar
    }
    
    currentValue += char;
    console.log('[Keyboard] ⌨️ Tecla digitada:', char, '| Total:', currentValue.length, 'chars');
    updateKeyboardDisplay();
}

function backspace() {
    currentValue = currentValue.slice(0, -1);
    updateKeyboardDisplay();
}

function toggleShift() {
    isShiftActive = !isShiftActive;
    updateShiftKeys();
}

function updateShiftKeys() {
    const shiftKeys = document.querySelectorAll('.key[data-key="shift"]');
    
    shiftKeys.forEach(key => {
        if (isShiftActive) {
            key.style.background = '#ffffff';
            key.style.color = '#000000';
        } else {
            key.style.background = '';
            key.style.color = '';
        }
    });
}

function updateKeyboardDisplay() {
    const textElement = document.getElementById('keyboard-text');
    
    // 🔥 DEBUG: Log para rastrear problema
    if (!textElement) {
        console.error('[Keyboard] ❌ keyboard-text element not found! Tentando fallback...');
        
        // Tentar recuperar forçando querySelector
        const textElementBackup = document.querySelector('#keyboard-text');
        if (textElementBackup) {
            console.log('[Keyboard] ✅ Elemento encontrado via querySelector (fallback)');
            textElementBackup.textContent = currentValue;
            return;
        }
        
        // Se ainda falhar, mostrar erro crítico
        console.error('[Keyboard] ❌ CRÍTICO: Não foi possível atualizar display! DOM pode não estar pronto.');
        console.error('[Keyboard] currentValue:', currentValue);
        return;
    }
    
    // Atualização normal
    textElement.textContent = currentValue;
    console.log('[Keyboard] ✅ Display atualizado:', currentValue.length, 'caracteres');
}

function updateKeyboardTitle(inputElement) {
    const titleElement = document.getElementById('keyboard-title');
    if (!titleElement) return;

    // 🌐 Mapeamento de campos para chaves de tradução i18n
    const fieldI18nKeys = {
        'username': 'keyboard.title_username',
        'password': 'keyboard.title_password',
        'current_password': 'keyboard.title_password',
        'new_password': 'keyboard.title_password',
        'confirm_password': 'keyboard.title_password',
        'name': 'keyboard.title_name',
        'rfid': 'keyboard.title_rfid'
    };

    // Fallback estatico (PT-BR) caso i18n nao esteja carregado
    const fallbackTitles = {
        'keyboard.title_username': 'Digite seu usuário administrador',
        'keyboard.title_password': 'Digite sua senha administradora',
        'keyboard.title_name': 'Digite o nome do usuário',
        'keyboard.title_rfid': 'Digite o RFID',
        'keyboard.title_default': 'Digite:'
    };

    // Verifica se há mensagem personalizada para este campo
    const i18nKey = fieldI18nKeys[inputElement.id] || fieldI18nKeys[inputElement.name] || 'keyboard.title_default';

    let translated;
    try {
        if (window.i18n && typeof window.i18n.t === 'function') {
            translated = window.i18n.t(i18nKey);
        }
    } catch (err) {
        console.warn('[Keyboard] i18n.t falhou, usando fallback:', err);
    }

    titleElement.textContent = translated || fallbackTitles[i18nKey] || 'Digite:';
}


// ========== RFID SCANNER ==========

let scannerActive = false;
let scannerBuffer = '';
let scannerTimeout = null;

function initializeRFIDScanner() {
    document.addEventListener('keypress', handleRFIDScan);
}

function handleRFIDScan(event) {
    // Ignora se o teclado virtual estiver aberto
    if (document.getElementById('virtual-keyboard').classList.contains('active')) {
        return;
    }
    
    // Detecta leitura do RFID (termina com Enter)
    if (event.key === 'Enter') {
        if (scannerBuffer.length > 0) {
            processRFIDScan(scannerBuffer);
            scannerBuffer = '';
        }
    } else {
        scannerBuffer += event.key;
        
        // Reset do buffer após 100ms de inatividade
        clearTimeout(scannerTimeout);
        scannerTimeout = setTimeout(() => {
            scannerBuffer = '';
        }, 100);
    }
}

function processRFIDScan(rfidCode) {
    // Envia para o servidor
    fetch('/api/rfid-scan', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ rfid: rfidCode })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Preenche o campo RFID se existir
            const rfidInput = document.getElementById('rfid');
            if (rfidInput) {
                rfidInput.value = rfidCode;
            }
            
            showMessage('RFID Lido', `Código: ${rfidCode}`, 'success');
        } else {
            showMessage('Erro', data.message || 'RFID inválido', 'error');
        }
    })
    .catch(error => {
        console.error('Erro ao processar RFID:', error);
        showMessage('Erro', 'Erro ao processar RFID', 'error');
    });
}


// ========== MENSAGENS E ALERTAS ==========

function showMessage(title, content, type = 'info') {
    // Remove mensagem existente
    const existingMessage = document.querySelector('.message');
    if (existingMessage) {
        existingMessage.remove();
    }
    
    const existingOverlay = document.querySelector('.overlay');
    if (existingOverlay) {
        existingOverlay.remove();
    }
    
    // Cria overlay
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    document.body.appendChild(overlay);
    
    // Cria mensagem
    const message = document.createElement('div');
    message.className = `message ${type}`;
    message.innerHTML = `
        <div class="message-title">${title}</div>
        <div class="message-content">${content}</div>
        <button class="btn" onclick="closeMessage()">OK</button>
    `;
    
    document.body.appendChild(message);
    
    // Auto-fecha após 3 segundos para mensagens de sucesso
    if (type === 'success') {
        setTimeout(closeMessage, 3000);
    }
}

function closeMessage() {
    const message = document.querySelector('.message');
    const overlay = document.querySelector('.overlay');
    
    if (message) message.remove();
    if (overlay) overlay.remove();
}


// ========== FORMULÁRIOS ==========

function submitForm(formId, url, method = 'POST') {
    const form = document.getElementById(formId);
    const formData = new FormData(form);
    
    // Converte para JSON
    const data = {};
    formData.forEach((value, key) => {
        data[key] = value;
    });
    
    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            showMessage('Sucesso', result.message, 'success');
            
            // Redireciona após 1 segundo
            setTimeout(() => {
                if (result.redirect) {
                    window.location.href = result.redirect;
                }
            }, 1000);
        } else {
            showMessage('Erro', result.message || 'Erro ao processar', 'error');
        }
    })
    .catch(error => {
        console.error('Erro:', error);
        showMessage('Erro', 'Erro ao processar requisição', 'error');
    });
}


// ========== NAVEGAÇÃO ==========

function navigateTo(url) {
    window.location.href = url;
}

function goBack() {
    window.history.back();
}


// ========== CONFIRMAÇÕES ==========

function confirmAction(message, callback) {
    showConfirm(message, callback);
}

function showConfirm(message, callback) {
    // Remove confirmação existente
    const existingMessage = document.querySelector('.message');
    if (existingMessage) {
        existingMessage.remove();
    }
    
    const existingOverlay = document.querySelector('.overlay');
    if (existingOverlay) {
        existingOverlay.remove();
    }
    
    // Cria overlay
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    document.body.appendChild(overlay);
    
    // Cria confirmação
    const confirm = document.createElement('div');
    confirm.className = 'message';
    confirm.innerHTML = `
        <div class="message-title">Confirmação</div>
        <div class="message-content">${message}</div>
        <div style="display: flex; gap: 1rem;">
            <button class="btn" onclick="closeConfirm(false)">Cancelar</button>
            <button class="btn btn-primary" onclick="closeConfirm(true)">Confirmar</button>
        </div>
    `;
    
    document.body.appendChild(confirm);
    
    // Guarda callback
    window._confirmCallback = callback;
}

function closeConfirm(confirmed) {
    const message = document.querySelector('.message');
    const overlay = document.querySelector('.overlay');
    
    if (message) message.remove();
    if (overlay) overlay.remove();
    
    if (confirmed && window._confirmCallback) {
        window._confirmCallback();
    }
    
    window._confirmCallback = null;
}


// ========== LISTA DE USUÁRIOS ==========

function deleteUser(userId, userName) {
    confirmAction(
        `Tem certeza que deseja remover o usuário "${userName}"?`,
        () => {
            fetch(`/usuarios/remover/${userId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    showMessage('Sucesso', 'Usuário removido com sucesso', 'success');
                    
                    // Recarrega a página após 1 segundo
                    setTimeout(() => {
                        window.location.reload();
                    }, 1000);
                } else {
                    showMessage('Erro', result.message || 'Erro ao remover usuário', 'error');
                }
            })
            .catch(error => {
                console.error('Erro:', error);
                showMessage('Erro', 'Erro ao remover usuário', 'error');
            });
        }
    );
}


// ========== UTILITÁRIOS ==========

function formatDate(dateString) {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    return date.toLocaleDateString('pt-BR');
}

function formatTime(dateString) {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    return date.toLocaleTimeString('pt-BR');
}
