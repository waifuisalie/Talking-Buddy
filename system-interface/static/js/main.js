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
    currentInput = inputElement;
    currentValue = inputElement.value || '';
    
    // Mostra o teclado
    const keyboard = document.getElementById('virtual-keyboard');
    keyboard.classList.add('active');
    
    // Atualiza o título do teclado baseado no campo
    updateKeyboardTitle(inputElement);
    
    // Atualiza o display
    updateKeyboardDisplay();
    
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
    if (textElement) {
        textElement.textContent = currentValue;
    }
}

function updateKeyboardTitle(inputElement) {
    const titleElement = document.getElementById('keyboard-title');
    
    // Mapeamento de campos para mensagens específicas
    const fieldMessages = {
        'username': 'Digite seu usuário administrador',
        'password': 'Digite sua senha administradora',
        'current_password': 'Digite sua senha administradora atual',
        'new_password': 'Digite sua nova senha administradora',
        'confirm_password': 'Digite a confirmação da senha',
        'name': 'Digite o nome do usuário',
        'rfid': 'Digite o RFID'
    };
    
    // Verifica se há mensagem personalizada para este campo
    if (fieldMessages[inputElement.id]) {
        titleElement.textContent = fieldMessages[inputElement.id];
    } else if (fieldMessages[inputElement.name]) {
        titleElement.textContent = fieldMessages[inputElement.name];
    } else {
        // Fallback: tenta usar o label
        const label = document.querySelector(`label[for="${inputElement.id}"]`);
        
        if (label && label.textContent) {
            const labelText = label.textContent.trim().replace(':', '');
            titleElement.textContent = `Digite ${labelText.toLowerCase()}`;
        } else {
            titleElement.textContent = 'Digite:';
        }
    }
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
