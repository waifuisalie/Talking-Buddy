/**
 * Sistema de Internacionalização (i18n)
 * Suporta: pt-BR, en-US, es-ES
 * 
 * Uso:
 *   i18n.setLanguage('en-US');
 *   i18n.t('buttons.send');  // "SEND"
 *   i18n.t('messages.welcome_with_name', {name: 'John'});  // "Hello, John!..."
 */

const i18n = (function() {
    'use strict';
    
    // Estado interno
    let currentLanguage = 'pt-BR';
    
    // Dicionário completo de traduções
    const translations = {
        'pt-BR': {
            // Botões e tooltips
            buttons: {
                admin: 'Painel Administrativo',
                logout: 'Sair',
                close_chat: 'Fechar Chat',
                mic: 'Gravar mensagem de voz',
                send: 'ENVIAR'
            },
            
            // Labels
            labels: {
                logged_in: 'Logado'
            },
            
            // Placeholders
            placeholders: {
                type_message: 'Digite sua mensagem...',
                wait_response: 'Aguarde a resposta...',
                recording: 'Gravando... Fale agora!',
                not_understood: 'Não consegui entender. Tente novamente.',
                recording_error: 'Erro ao gravar. Tente novamente.'
            },
            
            // Mensagens
            messages: {
                welcome_no_name: 'Olá! Sou seu assistente virtual. Como posso ajudá-lo(a) hoje?',
                welcome_with_name: 'Olá, {name}!\n\nSou seu assistente virtual. Como posso ajudá-lo(a) hoje?',
                thinking: 'Pensando...'
            },
            
            // Teclado Virtual
            keyboard: {
                title: 'Digite:',
                backspace: 'APAGAR',
                shift: 'SHIFT',
                space: 'ESPAÇO',
                cancel: 'CANCELAR',
                confirm: 'CONFIRMAR',
                // Títulos contextuais
                title_username: 'Digite seu usuário administrador',
                title_password: 'Digite sua senha administradora',
                title_name: 'Digite o nome do usuário',
                title_rfid: 'Digite o RFID',
                title_default: 'Digite:'
            }
        },
        
        'en-US': {
            // Buttons and tooltips
            buttons: {
                admin: 'Admin Panel',
                logout: 'Logout',
                close_chat: 'Close Chat',
                mic: 'Record voice message',
                send: 'SEND'
            },
            
            // Labels
            labels: {
                logged_in: 'Logged in'
            },
            
            // Placeholders
            placeholders: {
                type_message: 'Type your message...',
                wait_response: 'Wait for response...',
                recording: 'Recording... Speak now!',
                not_understood: 'Could not understand. Try again.',
                recording_error: 'Recording error. Try again.'
            },
            
            // Messages
            messages: {
                welcome_no_name: 'Hello! I\'m your virtual assistant. How can I help you today?',
                welcome_with_name: 'Hello, {name}!\n\nI\'m your virtual assistant. How can I help you today?',
                thinking: 'Thinking...'
            },
            
            // Virtual Keyboard
            keyboard: {
                title: 'Type:',
                backspace: 'DELETE',
                shift: 'SHIFT',
                space: 'SPACE',
                cancel: 'CANCEL',
                confirm: 'CONFIRM',
                // Contextual titles
                title_username: 'Enter admin username',
                title_password: 'Enter admin password',
                title_name: 'Enter user name',
                title_rfid: 'Enter RFID',
                title_default: 'Type:'
            }
        },
        
        'es-ES': {
            // Botones y tooltips
            buttons: {
                admin: 'Panel Administrativo',
                logout: 'Salir',
                close_chat: 'Cerrar Chat',
                mic: 'Grabar mensaje de voz',
                send: 'ENVIAR'
            },
            
            // Labels
            labels: {
                logged_in: 'Conectado'
            },
            
            // Placeholders
            placeholders: {
                type_message: 'Escribe tu mensaje...',
                wait_response: 'Espera la respuesta...',
                recording: '¡Grabando... Habla ahora!',
                not_understood: 'No pude entender. Intenta de nuevo.',
                recording_error: 'Error al grabar. Intenta de nuevo.'
            },
            
            // Mensajes
            messages: {
                welcome_no_name: '¡Hola! Soy tu asistente virtual. ¿Cómo puedo ayudarte hoy?',
                welcome_with_name: '¡Hola, {name}!\n\nSoy tu asistente virtual. ¿Cómo puedo ayudarte hoy?',
                thinking: 'Pensando...'
            },
            
            // Teclado Virtual
            keyboard: {
                title: 'Escribe:',
                backspace: 'BORRAR',
                shift: 'MAYÚS',
                space: 'ESPACIO',
                cancel: 'CANCELAR',
                confirm: 'CONFIRMAR',
                // Títulos contextuales
                title_username: 'Ingresa usuario administrador',
                title_password: 'Ingresa contraseña administrador',
                title_name: 'Ingresa nombre de usuario',
                title_rfid: 'Ingresa RFID',
                title_default: 'Escribe:'
            }
        }
    };
    
    /**
     * Obtém tradução por chave
     * @param {string} key - Chave da tradução (ex: 'buttons.send')
     * @param {object} params - Parâmetros para interpolação (ex: {name: 'John'})
     * @param {string} lang - Idioma (opcional, usa currentLanguage por padrão)
     * @returns {string} Texto traduzido
     */
    function t(key, params = {}, lang = null) {
        const targetLang = lang || currentLanguage;
        
        // Navegar pelo objeto de traduções usando dot notation
        const keys = key.split('.');
        let value = translations[targetLang];
        
        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                // Fallback para pt-BR se não encontrar no idioma alvo
                if (targetLang !== 'pt-BR') {
                    console.warn(`[i18n] Key "${key}" not found in ${targetLang}, trying pt-BR fallback`);
                    return t(key, params, 'pt-BR');
                }
                
                // Se nem em pt-BR encontrou, retorna a própria chave
                console.error(`[i18n] Key "${key}" not found in any language`);
                return `[${key}]`;
            }
        }
        
        // Se não é string, retornar chave
        if (typeof value !== 'string') {
            console.error(`[i18n] Key "${key}" does not resolve to a string`);
            return `[${key}]`;
        }
        
        // Interpolação de parâmetros {name}, {count}, etc.
        return value.replace(/\{(\w+)\}/g, (match, paramKey) => {
            return params[paramKey] !== undefined ? params[paramKey] : match;
        });
    }
    
    /**
     * Define o idioma atual
     * @param {string} lang - Código do idioma (pt-BR, en-US, es-ES)
     */
    function setLanguage(lang) {
        if (!translations[lang]) {
            console.warn(`[i18n] Language "${lang}" not supported, using pt-BR`);
            lang = 'pt-BR';
        }
        
        const oldLang = currentLanguage;
        currentLanguage = lang;
        
        console.log(`[i18n] Language changed: ${oldLang} → ${currentLanguage}`);
        
        // Dispara evento customizado para componentes reagirem
        window.dispatchEvent(new CustomEvent('languageChanged', {
            detail: { oldLanguage: oldLang, newLanguage: currentLanguage }
        }));
    }
    
    /**
     * Retorna o idioma atual
     * @returns {string} Código do idioma
     */
    function getCurrentLanguage() {
        return currentLanguage;
    }
    
    /**
     * Verifica se um idioma é suportado
     * @param {string} lang - Código do idioma
     * @returns {boolean}
     */
    function isLanguageSupported(lang) {
        return lang in translations;
    }
    
    /**
     * Lista todos os idiomas suportados
     * @returns {string[]} Array de códigos de idioma
     */
    function getSupportedLanguages() {
        return Object.keys(translations);
    }
    
    // API pública
    return {
        t,
        setLanguage,
        getCurrentLanguage,
        isLanguageSupported,
        getSupportedLanguages
    };
})();

// Expor globalmente para uso em outros scripts
window.i18n = i18n;
