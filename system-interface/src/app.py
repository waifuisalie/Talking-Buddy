#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Cadastro de Usuários RFID - Servidor Web
Interface touch otimizada para tela sensível ao toque
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g, send_from_directory, Response, stream_with_context
from functools import wraps
from datetime import datetime
import os
import time
import subprocess
import sys
import signal
import secrets
import threading
import fcntl  # 🔥 OTIMIZAÇÃO: File locking para RFID
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env
load_dotenv()

# Adiciona o diretório pai ao path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Adiciona rpi5-chatbot/src ao path para usar módulos existentes (Whisper STT)
rpi5_chatbot_src = os.path.join(os.path.dirname(parent_dir), 'rpi5-chatbot', 'src')
sys.path.insert(0, rpi5_chatbot_src)

from database import Database, RESPONSE_STYLES, GENDERS, LANGUAGES
import atexit

# Importa módulo de voz
try:
    from voice_assistant import (VoiceConfig, OllamaClient, HardwareAudioPlayer,
                                  ConversationHistory, SupertonicTTSClient, SentenceDetector,
                                  StreamingTTSProcessor, PersonalityManager)
    from voice_assistant.supertonic_tts_client import PERSONALITY_VOICES
    VOICE_ENABLED = True
    print("✅ Módulo de voz carregado")
except ImportError as e:
    VOICE_ENABLED = False
    print(f"⚠️  Módulo de voz desabilitado: {e}")

try:
    from openwakeword_manager import OpenWakeWordManager
    OWW_AVAILABLE = True
except ImportError as e:
    OWW_AVAILABLE = False
    print(f"⚠️  OpenWakeWordManager não disponível: {e}")

try:
    from battery_monitor import BatteryMonitor
    battery_monitor = BatteryMonitor()
    BATTERY_AVAILABLE = True
    print("🔋 Battery monitor loaded")
except Exception as e:
    battery_monitor = None
    BATTERY_AVAILABLE = False
    print(f"⚠️  Battery monitor disabled: {e}")

WAKE_WORD_ENABLED = os.getenv('WAKE_WORD_ENABLED', 'true').lower() == 'true'
DEBUG_LOGS = os.getenv('DEBUG_LOGS', 'false').lower() == 'true'

# Inicialização do Flask
app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
            static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))
app.secret_key = secrets.token_hex(32)

# Suppress noisy polling routes from Werkzeug access log unless DEBUG_LOGS=true
if not DEBUG_LOGS:
    import logging

    _POLL_PATHS = ('/api/wake_word_status', '/usuarios/rfid/poll', '/api/system/battery')

    class _SuppressPollLogs(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            return not any(p in msg for p in _POLL_PATHS)

    logging.getLogger('werkzeug').addFilter(_SuppressPollLogs())

# Configuração do banco de dados (na raiz do projeto)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assistant.db')

# Controle do processo do leitor RFID
rfid_process = None
RFID_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'last_rfid.txt')

# Verifica se o banco existe
if not os.path.exists(DB_PATH):
    print("=" * 70)
    print("⚠️  BANCO DE DADOS NÃO ENCONTRADO!")
    print("=" * 70)
    print()
    print("Execute primeiro o script de inicialização:")
    print("  python3 init_system.py")
    print()
    print("Ou crie manualmente:")
    print("  python3 -c 'from database import Database; db = Database(\"assistant.db\"); db.upsert_admin(\"admin\", \"senha123\"); db.close()'")
    print()
    print("=" * 70)
    import sys
    sys.exit(1)


# ========== GERENCIAMENTO DE BANCO (THREAD-SAFE) ==========

def get_db():
    """Obtém conexão do banco para a requisição atual (thread-safe)"""
    if 'db' not in g:
        g.db = Database(DB_PATH)
    return g.db


@app.teardown_appcontext
def close_db(error):
    """Fecha conexão do banco ao fim da requisição"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def cleanup_rfid_process():
    """Para o processo do leitor RFID se estiver rodando"""
    global rfid_process
    if rfid_process and rfid_process.poll() is None:
        try:
            rfid_process.terminate()
            rfid_process.wait(timeout=2)
        except Exception:
            pass


def killall_rfid_processes():
    """🔥 CRÍTICO: Mata TODOS os processos RFID para evitar conflitos de hardware"""
    try:
        print("[RFID Killall] 🔍 Procurando processos rfid_manager.py...", flush=True)
        
        # Método 1: pkill (mais rápido e seguro)
        try:
            result = subprocess.run(
                ['sudo', 'pkill', '-9', '-f', 'rfid_manager.py'],
                timeout=5,
                check=False,
                capture_output=True
            )
            print(f"[RFID Killall] pkill executado (retorno: {result.returncode})", flush=True)
        except Exception as e:
            print(f"[RFID Killall] ⚠️  pkill falhou: {e}", flush=True)
        
        # Método 2: ps + grep + kill (backup para garantir)
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            killed_count = 0
            for line in result.stdout.split('\n'):
                if 'rfid_manager.py' in line and 'grep' not in line and 'sudo' not in line:
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        try:
                            subprocess.run(['sudo', 'kill', '-9', pid], timeout=2, check=False)
                            killed_count += 1
                            print(f"[RFID Killall] ⚔️  Matou PID {pid}", flush=True)
                        except:
                            pass
            
            if killed_count > 0:
                print(f"[RFID Killall] ✅ Total: {killed_count} processo(s) encerrado(s)", flush=True)
            else:
                print("[RFID Killall] ℹ️  Nenhum processo encontrado", flush=True)
                
        except Exception as e:
            print(f"[RFID Killall] ⚠️  Método backup falhou: {e}", flush=True)
        
        # Aguardar processos morrerem completamente
        time.sleep(0.5)
        print("[RFID Killall] ✅ Limpeza concluída", flush=True)
        
    except Exception as e:
        print(f"[RFID Killall] ❌ ERRO: {e}", flush=True)
        import traceback
        traceback.print_exc()


def cleanup_wake_word_manager():
    """Para o gerenciador de wake word se estiver rodando"""
    global wake_word_manager
    if wake_word_manager:
        try:
            wake_word_manager.stop()
        except Exception:
            pass

import atexit

# Registra limpeza ao encerrar
atexit.register(cleanup_rfid_process)
atexit.register(cleanup_wake_word_manager)

if BATTERY_AVAILABLE and battery_monitor:
    atexit.register(battery_monitor.close)


def shutdown_gracefully(signum=None, frame=None):
    """Encerra o sistema de forma limpa ao receber SIGINT ou SIGTERM"""
    print("\n\n🛑 Encerrando TalkingBuddy...", flush=True)

    cleanup_rfid_process()
    cleanup_wake_word_manager()

    if BATTERY_AVAILABLE and battery_monitor:
        try:
            battery_monitor.close()
            print("✅ Battery monitor encerrado", flush=True)
        except Exception:
            pass

    if audio_player:
        try:
            audio_player.stop()
            print("✅ AudioPlayer encerrado", flush=True)
        except Exception:
            pass

    if whisper_stt:
        try:
            whisper_stt.stop()
            print("✅ Whisper STT encerrado", flush=True)
        except Exception:
            pass

    print("👋 Sistema encerrado.", flush=True)
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_gracefully)
signal.signal(signal.SIGTERM, shutdown_gracefully)


# 🔥 KILLALL de processos RFID ao iniciar servidor (previne processos órfãos)
print("\n" + "="*60)
print("🚀 INICIANDO SERVIDOR - Limpando processos RFID órfãos...")
print("="*60 + "\n")
killall_rfid_processes()
print()


# ========== SESSION TELEMETRY ==========
from telemetry import setup_session_log, TelemetryMonitor, ilog as _ilog

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
_session_log_path = setup_session_log(_LOG_DIR)
print(f"📋 Log de sessão: {_session_log_path}")


def ilog(component: str, msg: str):
    _ilog(component, msg)


# ========== SSE MANAGER ==========
from sse_manager import SSEManager
sse_manager = SSEManager()

# ========== VOICE ASSISTANT INITIALIZATION ==========

voice_config = None
ollama_client = None
supertonic_tts_client = None
personality_manager = None    # Personality system
audio_player = None
whisper_stt = None  # Whisper STT (reconhecimento de voz)
_last_activity_time: float = 0.0  # updated on every user interaction


def _update_activity():
    global _last_activity_time
    _last_activity_time = time.time()


# Wake Word Manager
wake_word_manager = None

if VOICE_ENABLED:
    try:
        voice_config = VoiceConfig.from_env()
        
        # DETECTAR AUTOMATICAMENTE DISPOSITIVO DE ÁUDIO USB
        print("\n🔊 Detectando dispositivo de áudio...")
        voice_config.auto_detect_audio_device()
        
        is_valid, errors = voice_config.validate()
        
        if is_valid:
            ollama_client = OllamaClient(voice_config)

            # Inicializa Audio Player no processo correto:
            # - com reloader ativo: apenas no processo filho (WERKZEUG_RUN_MAIN=true)
            # - sem reloader (use_reloader=False): sempre inicializa
            import os
            _is_main_process = (os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or
                                 os.environ.get('WERKZEUG_RUN_MAIN') is None)
            if _is_main_process:
                audio_player = HardwareAudioPlayer(voice_config)
            else:
                print("ℹ️ [AudioPlayer] Aguardando processo reloader...")
            
            # Inicializa Whisper STT se habilitado
            if voice_config.whisper_enabled:
                try:
                    # Importa módulos do rpi5-chatbot
                    from whisper_stt import WhisperSTT
                    import config as rpi5_config
                    
                    # Cria configuração compatível
                    whisper_config = rpi5_config.WhisperConfig()
                    whisper_config.capture_device_name = voice_config.microphone_device
                    whisper_config.capture_device = -1  # avoid stale PyAudio index fallback
                    whisper_config.model_path = os.path.join(voice_config.whisper_model_path, voice_config.whisper_model)
                    whisper_config.cli_binary = voice_config.whisper_binary
                    whisper_config.language = voice_config.whisper_language
                    whisper_config.threads = voice_config.whisper_threads
                    whisper_config.silence_threshold = voice_config.silence_threshold
                    whisper_config.silence_duration = voice_config.silence_duration
                    whisper_config.min_audio_length = voice_config.min_audio_length
                    whisper_config.debug_mode = os.getenv("VAD_DEBUG", "0") == "1"
                    
                    # Cria instância do Whisper STT (sem callbacks ainda)
                    whisper_stt = WhisperSTT(whisper_config, callback=None)

                    # Apply VAD threshold pre-calibrated by start.sh if available
                    _vad_env = os.getenv('VAD_THRESHOLD', '')
                    if _vad_env.isdigit():
                        whisper_config.silence_threshold = int(_vad_env)
                        whisper_stt.silence_threshold = int(_vad_env)
                        print(f"   🎚️  Threshold pré-calibrado aplicado: {int(_vad_env)}")

                    print("✅ Whisper STT carregado (inativo - ativa sob demanda)")
                    
                except Exception as e:
                    print(f"⚠️  Whisper STT não disponível: {e}")
                    whisper_stt = None
            
            print("✅ Sistema de voz inicializado")
            
            # Pré-carrega modelo Ollama em background (primeira carga é lenta)
            print("")
            print("=" * 70)
            print("PRÉ-CARREGANDO SISTEMA DE VOZ")
            print("=" * 70)
            
            # Warmup Ollama
            print("\n1️⃣  Carregando modelo de IA...")
            if ollama_client.warmup():
                print("   ✅ Modelo de IA carregado e pronto")
            else:
                print("   ⚠️  Warmup Ollama falhou - primeira resposta pode ser lenta")
            
            # Initialize Supertonic TTS
            print("\n2️⃣  Testando sintetizador de voz (Supertonic)...")
            try:
                supertonic_tts_client = SupertonicTTSClient(voice_config)
                if supertonic_tts_client.is_available():
                    print("   ✅ Supertonic TTS disponível e configurado")
                else:
                    print("   ⚠️  Supertonic TTS não disponível - áudio pode não funcionar")
                    supertonic_tts_client = None
            except Exception as e:
                print(f"   ⚠️  Supertonic TTS falhou: {e}")
                supertonic_tts_client = None

            # Verify whisper CLI binary and model are present
            print("\n3️⃣  Verificando whisper CLI...")
            if whisper_stt and whisper_stt.is_available():
                print("   ✅ whisper-cli encontrado e pronto")
            else:
                print("   ⚠️  whisper-cli não encontrado - STT pode não funcionar")

            # Start background VAD recalibration thread (every 60s when idle 30s+)
            def _vad_recalibration_loop():
                while True:
                    time.sleep(60)
                    if not whisper_stt:
                        continue
                    idle_secs = time.time() - _last_activity_time
                    if idle_secs >= 30:
                        oww = wake_word_manager
                        if oww and hasattr(oww, 'pause'):
                            oww.pause()
                        try:
                            new_thresh = whisper_stt.calibrate_vad(duration=2.0)
                            if new_thresh:
                                print(f"🎚️  [VAD] Auto-recalibrado: threshold={new_thresh:.0f} (idle {idle_secs:.0f}s)")
                        finally:
                            if oww and hasattr(oww, 'resume'):
                                oww.resume()

            threading.Thread(target=_vad_recalibration_loop, daemon=True, name="VADRecalibration").start()

            # Initialize Personality Manager
            try:
                personality_manager = PersonalityManager()
                count = len(personality_manager.personalities)
                print(f"   ✅ Personality Manager: {count} personalidades carregadas")
            except Exception as e:
                print(f"   ⚠️  Personality Manager falhou: {e}")
                personality_manager = None

            # Summary of TTS state
            print("\n" + "-" * 50)
            print(f"🎤 [TTS SUMMARY] supertonic_tts_client = {'INITIALIZED' if supertonic_tts_client else 'None'}")
            print("-" * 50)

            print("\n" + "=" * 70)
            print("✅ SISTEMA PRONTO PARA USO!")
            print("=" * 70)
            print("")
        else:
            print("⚠️  Erros na configuração de voz:")
            for error in errors:
                print(f"   - {error}")
            print("   Sistema funcionará apenas com texto")
    except Exception as e:
        print(f"⚠️  Erro ao inicializar voz: {e}")
        print("   Sistema funcionará apenas com texto")


# ========== WAKE WORD INITIALIZATION (openWakeWord) ==========

_is_main_process = (os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or
                     os.environ.get('WERKZEUG_RUN_MAIN') is None)
if _is_main_process:
    if WAKE_WORD_ENABLED and OWW_AVAILABLE:
        try:
            print("\n" + "=" * 70)
            print("INICIALIZANDO OPENWAKEWORD DETECTION")
            print("=" * 70)

            debounce = float(os.getenv('WAKE_WORD_DEBOUNCE_TIME', '2.0'))

            def on_wake_word():
                print(f"⏱️  [TIMING] wake_word_callback t={time.monotonic():.3f}")
                print("🔔 [CALLBACK] Wake word detectado!")

            wake_word_manager = OpenWakeWordManager(debounce_time=debounce)
            wake_word_manager.register_wake_callback(on_wake_word)
            wake_word_manager.start()

            print("✅ OpenWakeWord Manager ativado")
            print("=" * 70)
            print()

        except Exception as e:
            print(f"⚠️  Erro ao inicializar OpenWakeWord: {e}")
            print("   Sistema funcionará sem wake word detection")
            wake_word_manager = None

    elif not WAKE_WORD_ENABLED:
        print("\nℹ️  Wake Word desabilitado (.env: WAKE_WORD_ENABLED=false)")
        wake_word_manager = None

    else:
        print(f"\n⚠️  OpenWakeWord não disponível")
        print(f"   Execute: pip install openwakeword onnxruntime")
        wake_word_manager = None

else:
    print("\nℹ️  Wake Word aguardando processo reloader...")
    wake_word_manager = None


# Verifica se tem admin (usando conexão temporária)
temp_db = Database(DB_PATH)
if not temp_db.has_any_admin():
    temp_db.close()
    print("=" * 70)
    print("⚠️  NENHUM ADMINISTRADOR CONFIGURADO!")
    print("=" * 70)
    print()
    print("Execute o script de inicialização:")
    print("  python3 init_system.py")
    print()
    print("=" * 70)
    import sys
    sys.exit(1)
temp_db.close()

# ========== START TELEMETRY MONITOR ==========
_telemetry_monitor = TelemetryMonitor(
    battery_monitor=battery_monitor if BATTERY_AVAILABLE else None
)
_telemetry_monitor.start()
ilog("SESSION", f"Ollama: {os.getenv('OLLAMA_MODEL', 'gemma3:1b')} | Whisper: {os.getenv('WHISPER_MODEL', 'ggml-base.bin')} | TTS: supertonic")

# ========== DECORATORS ==========

def login_required(f):
    """Decorator para proteger rotas que exigem autenticação"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ========== ROTAS DE AUTENTICAÇÃO ==========

@app.route('/favicon.ico')
def favicon():
    """Retorna 204 No Content para favicon"""
    return '', 204


@app.route('/')
def index():
    """Página principal - Robô de chat"""
    return render_template('robot_chat.html')


@app.route('/test-rfid')
def test_rfid():
    """Página de teste de RFID"""
    return app.send_static_file('../test_rfid.html')


@app.route('/admin')
def admin_index():
    """Redireciona para login ou menu de usuários (antiga rota /)""" 
    if 'admin_logged_in' in session:
        return redirect(url_for('menu_usuarios'))
    return redirect(url_for('login'))


# ========== ROTAS DE API - CHAT ==========

@app.route('/api/user/profile/<rfid>', methods=['GET'])
def get_user_profile_by_rfid(rfid):
    """Retorna perfil do usuário por RFID (para chat)"""
    user = get_db().get_user_by_rfid(rfid)
    
    if user:
        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'name': user['name'],
                'response_style': user['response_style'],
                'persona_gender': user['persona_gender'],
                'language': user['language']
            }
        })
    
    return jsonify({
        'success': False,
        'message': 'Usuário não encontrado'
    }), 404


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Tela de login do administrador"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        # Validação básica
        if not username or not password:
            return render_template('login.html', error='Preencha todos os campos!')
        
        # Verificar credenciais
        if get_db().verify_admin(username, password):
            # Login bem-sucedido
            session.clear()
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('menu_usuarios'))
        else:
            # Login falhou
            return render_template('login.html', 
                                 error='Usuário ou senha inválidos!')
    
    return render_template('login.html')


@app.route('/logout', methods=['GET'])
@login_required
def confirmar_logout():
    """Tela de confirmação de logout"""
    return render_template('confirmar_logout.html')


@app.route('/logout/confirmar', methods=['POST'])
def logout():
    """Logout do sistema"""
    session.clear()
    return redirect(url_for('index'))


@app.route('/admin/alterar-senha', methods=['GET', 'POST'])
@login_required
def alterar_senha():
    """Tela para alterar senha do administrador"""
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # Validações
        if not new_password or not confirm_password:
            return render_template('alterar_senha.html', 
                                 error='Preencha todos os campos!')
        
        if len(new_password) < 6:
            return render_template('alterar_senha.html', 
                                 error='A nova senha deve ter pelo menos 6 caracteres!')
        
        if new_password != confirm_password:
            return render_template('alterar_senha.html', 
                                 error='As senhas não coincidem!')
        
        # Alterar senha
        username = session.get('admin_username')
        get_db().upsert_admin(username, new_password)
        
        return render_template('alterar_senha.html', 
                             success='Senha alterada com sucesso!')
    
    return render_template('alterar_senha.html')


# ========== ROTAS PRINCIPAIS ==========

@app.route('/usuarios')
@login_required
def menu_usuarios():
    """Menu de gerenciamento de usuários"""
    return render_template('menu_usuarios.html')


@app.route('/usuarios/lista')
@login_required
def lista_usuarios():
    """Lista todos os usuários"""
    usuarios = get_db().list_users()
    corpora = get_db().list_corpora(only_enabled=False)
    spec_names = {c['id']: c['display_name'] for c in corpora}
    return render_template('lista_usuarios.html', users=usuarios, spec_names=spec_names)


@app.route('/usuarios/aguardar-rfid')
@login_required
def aguardar_rfid():
    """Tela de aguardar leitura do RFID"""
    return render_template('aguardar_rfid.html')


@app.route('/usuarios/rfid/start', methods=['POST'])
def rfid_start():
    """Inicia o processo do leitor RFID"""
    global rfid_process
    
    try:
        # 🔥 CRÍTICO: Matar TODOS os processos RFID primeiro
        print("\n[RFID Start] 🧹 Limpando processos anteriores...")
        killall_rfid_processes()
        
        # Resetar variável global
        rfid_process = None
        
        # Garantir que o arquivo existe e está limpo
        os.makedirs(os.path.dirname(RFID_FILE), exist_ok=True)
        with open(RFID_FILE, 'w') as f:
            f.write('')
        print("[RFID Start] 📄 Arquivo RFID limpo")
        
        # Verificar se o script existe
        script_path = os.path.join(os.path.dirname(__file__), 'rfid_manager.py')
        if not os.path.exists(script_path):
            error_msg = f"Script RFID não encontrado: {script_path}"
            print(f"[RFID Start] ❌ ERRO: {error_msg}")
            return jsonify({'success': False, 'error': error_msg})
        
        # Inicia novo processo COM SUDO (essencial para acesso SPI/GPIO)
        # Usa o mesmo Python do venv (garante spidev disponível) e captura
        # stderr para que erros apareçam no log de sessão via tee.
        env = os.environ.copy()
        venv_python = sys.executable  # python do venv ativo

        print(f"[RFID Start] 🚀 Iniciando novo processo: {script_path}")
        print(f"[RFID Start] 🐍 Python: {venv_python}")
        rfid_process = subprocess.Popen(
            ['sudo', venv_python, '-u', script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(__file__),
            env=env
        )

        # Thread que encaminha saída do subprocess para o log de sessão
        def _forward_rfid_output(proc):
            for raw in proc.stdout:
                line = raw.decode('utf-8', errors='replace').rstrip()
                if line:
                    print(f"[RFID] {line}", flush=True)
        threading.Thread(target=_forward_rfid_output, args=(rfid_process,),
                         daemon=True, name="RFIDOutputForwarder").start()

        print(f"[RFID Start] ✅ Processo iniciado com PID: {rfid_process.pid}")

        # Verificar se o processo iniciou corretamente
        time.sleep(1)  # Dar mais tempo para inicializar
        if rfid_process.poll() is not None:
            # Processo terminou imediatamente - erro fatal
            error_msg = f"Processo RFID terminou imediatamente (exit code: {rfid_process.returncode})"
            print(f"[RFID Start] ❌ ERRO: {error_msg}")
            print(f"[RFID Start] 🔍 Verifique: SPI habilitado, permissões GPIO, biblioteca MFRC522")
            return jsonify({'success': False, 'error': error_msg})
        
        print(f"[RFID Start] 🎉 Sistema RFID funcionando - PID {rfid_process.pid}\n")
        return jsonify({'success': True, 'pid': rfid_process.pid})
        
    except Exception as e:
        error_msg = str(e)
        print(f"[RFID Start] ❌ ERRO: {error_msg}")
        import traceback
        traceback.print_exc()
        rfid_process = None
        return jsonify({'success': False, 'error': error_msg})



@app.route('/usuarios/rfid/poll', methods=['GET'])
def rfid_poll():
    """
    Verifica se há um RFID lido
    
    Response JSON:
        {
            "success": true,
            "rfid": "ABC123..." ou null
        }
    """
    try:
        if not os.path.exists(RFID_FILE):
            return jsonify({'success': True, 'rfid': None})
        
        # 🔥 OTIMIZAÇÃO: File locking para evitar race conditions
        rfid = None
        try:
            with open(RFID_FILE, 'r+') as f:
                # Adquirir lock exclusivo para ler E limpar atomicamente
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    content = f.read().strip()
                    if content:
                        rfid = content
                        print(f"[RFID Poll] RFID detectado: {rfid}")
                        
                        # Limpar arquivo imediatamente (dentro do lock)
                        f.seek(0)
                        f.truncate()
                        print(f"[RFID Poll] Arquivo limpo atomicamente")
                finally:
                    # Liberar lock
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError) as e:
            print(f"[RFID Poll] Erro ao ler arquivo: {e}")
            return jsonify({'success': True, 'rfid': None})
        
        if rfid:
            return jsonify({'success': True, 'rfid': rfid})
        
        return jsonify({'success': True, 'rfid': None})
        
    except Exception as e:
        print(f"[RFID Poll] ERRO: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/usuarios/rfid/stop', methods=['POST'])
@login_required
def rfid_stop():
    """Para o processo do leitor RFID"""
    global rfid_process
    
    try:
        print("\n[RFID Stop] 🛑 Parando sistema RFID...")
        
        # Usar killall para garantir que TODOS os processos sejam encerrados
        killall_rfid_processes()
        
        # Resetar variável global
        rfid_process = None
        
        # Limpar arquivo RFID
        if os.path.exists(RFID_FILE):
            with open(RFID_FILE, 'w') as f:
                f.write('')
            print("[RFID Stop] 📄 Arquivo RFID limpo")
        
        print("[RFID Stop] ✅ Sistema RFID parado\n")
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"[RFID Stop] ❌ ERRO: {str(e)}")
        rfid_process = None
        return jsonify({'success': False, 'error': str(e)})


@app.route('/usuarios/rfid/status', methods=['GET'])
@login_required
def rfid_status():
    """🔍 Retorna status do sistema RFID (útil para debug)"""
    global rfid_process
    
    try:
        # Verificar processo global
        is_running = False
        pid = None
        
        if rfid_process:
            is_running = rfid_process.poll() is None
            if is_running:
                pid = rfid_process.pid
        
        # Verificar se há processos órfãos
        orphan_count = 0
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=3
            )
            for line in result.stdout.split('\n'):
                if 'rfid_manager.py' in line and 'grep' not in line:
                    orphan_count += 1
        except:
            pass
        
        return jsonify({
            'success': True,
            'running': is_running,
            'pid': pid,
            'orphan_processes': orphan_count,
            'warning': '⚠️ Processos órfãos detectados!' if orphan_count > 1 else None
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



@app.route('/usuarios/selecionar-response-style')
@login_required
def selecionar_response_style():
    """Tela de seleção de estilo de resposta"""
    return render_template('selecionar_response_style.html')


@app.route('/usuarios/selecionar-persona-gender')
@login_required
def selecionar_persona_gender():
    """Tela de seleção de gênero da persona"""
    return render_template('selecionar_persona_gender.html')


@app.route('/usuarios/selecionar-language')
@login_required
def selecionar_language():
    """Tela de seleção de idioma"""
    return render_template('selecionar_language.html')


@app.route('/usuarios/selecionar-especializacao')
@login_required
def selecionar_especializacao():
    """Tela de seleção de especialização (RAG corpus)"""
    return render_template('selecionar_specialization.html')


@app.route('/api/specializations', methods=['GET'])
@login_required
def api_specializations():
    """Lista os corpora habilitados para popular o seletor de especialização."""
    rows = get_db().list_corpora(only_enabled=True)
    return jsonify([
        {
            'id': r['id'],
            'slug': r['slug'],
            'display_name': r['display_name'],
            'description': r['description'] or '',
            'language': r['language'] or '',
            'document_count': r['document_count'],
            'chunk_count': r['chunk_count'],
        }
        for r in rows
    ])


def _parse_specialization_id(raw):
    """Aceita None, '', 'null', ou string numérica; retorna int ou None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in ('null', 'none', '0'):
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


@app.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
def novo_usuario():
    """Formulário de cadastro de novo usuário"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            name = data.get('name', '').strip()
            rfid = data.get('rfid', '').strip()
            response_style = data.get('response_style', '').strip()
            persona_gender = data.get('persona_gender', '').strip()
            language = data.get('language', '').strip()
            specialization_id = _parse_specialization_id(data.get('specialization_id'))

            # Validação (specialization é OPCIONAL — None = "Nenhuma")
            if not name or not rfid or not response_style or not persona_gender or not language:
                return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios!'})

            # Verifica se nome já existe
            if get_db().user_exists_by_name(name):
                return jsonify({'success': False, 'message': 'Já existe um usuário com este nome!'})

            # Verifica se RFID já existe
            if get_db().user_exists_by_rfid(rfid):
                return jsonify({'success': False, 'message': 'Este RFID já está cadastrado!'})

            # Adiciona usuário
            get_db().add_user(name, rfid, response_style, persona_gender, language, specialization_id)
            return jsonify({'success': True, 'message': 'Usuário cadastrado com sucesso!', 'redirect': '/usuarios/lista'})

        except Exception as e:
            error_msg = str(e)
            if 'UNIQUE' in error_msg and 'rfid' in error_msg.lower():
                return jsonify({'success': False, 'message': 'Este RFID já está cadastrado'})
            return jsonify({'success': False, 'message': f'Erro ao cadastrar: {error_msg}'})

    corpora = get_db().list_corpora(only_enabled=True)
    return render_template('form_usuario.html', user=None,
                         response_styles=RESPONSE_STYLES,
                         genders=GENDERS,
                         languages=LANGUAGES,
                         corpora=corpora)


@app.route('/usuarios/editar/<int:user_id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(user_id):
    """Formulário de edição de usuário"""
    usuario = get_db().get_user(user_id)
    if not usuario:
        return redirect(url_for('lista_usuarios'))

    if request.method == 'POST':
        try:
            data = request.get_json()
            name = data.get('name', '').strip()
            rfid = data.get('rfid', '').strip()
            response_style = data.get('response_style', '').strip()
            persona_gender = data.get('persona_gender', '').strip()
            language = data.get('language', '').strip()
            specialization_id = _parse_specialization_id(data.get('specialization_id'))

            # Validação (specialization é OPCIONAL — None = "Nenhuma")
            if not name or not rfid or not response_style or not persona_gender or not language:
                return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios!'})

            # Verifica se nome já existe (excluindo o próprio usuário)
            if get_db().user_exists_by_name(name, exclude_id=user_id):
                return jsonify({'success': False, 'message': 'Já existe outro usuário com este nome!'})

            # Verifica se RFID já existe (excluindo o próprio usuário)
            if get_db().user_exists_by_rfid(rfid, exclude_id=user_id):
                return jsonify({'success': False, 'message': 'Este RFID já está cadastrado para outro usuário!'})

            # Atualiza
            get_db().update_user(user_id, name, rfid, response_style, persona_gender, language, specialization_id)
            return jsonify({'success': True, 'message': 'Usuário atualizado com sucesso!', 'redirect': '/usuarios/lista'})

        except Exception as e:
            error_msg = str(e)
            if 'UNIQUE' in error_msg and 'rfid' in error_msg.lower():
                return jsonify({'success': False, 'message': 'Este RFID já está cadastrado para outro usuário'})
            return jsonify({'success': False, 'message': f'Erro ao atualizar: {error_msg}'})

    corpora = get_db().list_corpora(only_enabled=True)
    return render_template('form_usuario.html', user=usuario,
                         response_styles=RESPONSE_STYLES,
                         genders=GENDERS,
                         languages=LANGUAGES,
                         corpora=corpora)


@app.route('/usuarios/confirmar-remocao/<int:user_id>', methods=['GET'])
@login_required
def confirmar_remocao(user_id):
    """Tela de confirmação para remover usuário"""
    usuario = get_db().get_user(user_id)
    if not usuario:
        return redirect(url_for('lista_usuarios'))
    return render_template('confirmar_remocao.html', user=usuario)


@app.route('/usuarios/remover/<int:user_id>', methods=['POST'])
@login_required
def remover_usuario(user_id):
    """Remove um usuário"""
    try:
        usuario = get_db().get_user(user_id)
        if usuario:
            get_db().delete_user(user_id)
            return redirect(url_for('lista_usuarios'))
        return redirect(url_for('lista_usuarios'))
    except Exception as e:
        return redirect(url_for('lista_usuarios'))


# ========== API PARA RFID ==========

@app.route('/api/rfid-scan', methods=['POST'])
@login_required
def api_rfid_scan():
    """Processa leitura de RFID do scanner"""
    try:
        data = request.get_json()
        rfid_code = data.get('rfid', '').strip()
        
        if not rfid_code:
            return jsonify({'success': False, 'message': 'Código RFID vazio'})
        
        # Retorna o código para preencher o campo
        return jsonify({'success': True, 'rfid': rfid_code})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao processar RFID: {str(e)}'})


# ========== VOICE ASSISTANT API ==========

@app.route('/api/chat/send', methods=['POST'])
def api_chat_send():
    """
    Processa mensagem com streaming SSE — retorna session_id para EventSource

    Request JSON:  { "message": "...", "rfid": "..." }
    Response JSON: { "success": true, "session_id": "uuid" }

    Frontend then connects to GET /api/chat/stream/<session_id> for SSE events:
      text_chunk        — {text: "..."}           (LLM token)
      sentence_playing  — {text: "...", index: N}  (audio chunk started on hardware)
      response_done     — {}                       (all audio finished)
      error             — {error: "..."}
    """
    if not VOICE_ENABLED or not ollama_client or not supertonic_tts_client:
        return jsonify({
            'success': False,
            'error': 'Sistema de voz não disponível'
        }), 503

    try:
        _update_activity()
        data = request.get_json()
        user_message = data.get('message', '').strip()
        rfid = data.get('rfid', '')

        if not user_message:
            return jsonify({'success': False, 'error': 'Mensagem vazia'}), 400

        # --- Resolve user & context (same logic as before) ---
        is_anonymous = (not rfid or rfid == 'anonymous')

        if is_anonymous:
            print(f"🤖 [API] Modo anônimo ativado")
            user = None
            user_id = None
            conversation_context = []
            system_prompt = """Você é um assistente virtual amigável e prestativo.
IMPORTANTE: Responda SEMPRE com no máximo 2-3 frases curtas (menos de 150 caracteres).
Seja direto, objetivo e conciso."""
        else:
            db = get_db()
            user = db.get_user_by_rfid(rfid)

            if not user:
                return jsonify({'success': False, 'error': 'Usuário não encontrado'}), 404

            user_id = user['id']

            history_manager = ConversationHistory(db)
            history_manager.add_message(user_id, 'user', user_message)
            _t_ctx_start = time.perf_counter()
            conversation_context = history_manager.get_context_for_llm(user_id, max_messages=8)
            _t_ctx_ms = (time.perf_counter() - _t_ctx_start) * 1000
            ilog("DB", f"Contexto recuperado: {len(conversation_context)} msgs em {_t_ctx_ms:.2f}ms")
            system_prompt = _build_system_prompt(user)

        # --- Create SSE session ---
        session_id = sse_manager.create_session()

        # --- Resolve personality for TTS voice + Ollama model ---
        personality_id = _resolve_personality_for_user(user)

        # Per-request TTS parameters (no shared-state mutation)
        _LANG_MAP = {"pt-BR": "pt", "en-US": "en", "es-ES": "es"}
        _tts_personality = personality_id
        _tts_language = _LANG_MAP.get(user["language"], "pt") if user else "pt"
        _tts_gender = user["persona_gender"] if user else "male"

        user_name = user["name"] if user else "anonymous"
        print(f"🎤 [TTS-WIRE] User='{user_name}' | personality='{_tts_personality}' | gender='{_tts_gender}' | language='{_tts_language}'")

        tts = supertonic_tts_client
        print(f"🎤 [TTS-WIRE] Engine: ✅ SUPERTONIC selected")

        # Resolve Ollama model name (personality model if available)
        if personality_manager and not is_anonymous:
            ollama_model = personality_manager.resolve_model_name(
                voice_config.ollama_model, personality_id
            )
        else:
            ollama_model = voice_config.ollama_model

        # --- Background streaming pipeline ---
        # Capture variables for the thread closure
        _user_message = user_message
        _system_prompt = system_prompt
        _conversation_context = list(conversation_context) if conversation_context else []
        _user = dict(user) if user else None
        _user_id = user_id
        _is_anonymous = is_anonymous
        _db_path = DB_PATH
        _ollama_model = ollama_model

        def streaming_pipeline():
            nonlocal _system_prompt
            try:
                user_name = _user['name'] if _user else 'Visitante'
                print(f"🤖 [SSE] Streaming resposta para {user_name}...")

                # Set up audio queue
                if audio_player and audio_player.is_available():
                    sentence_index = [0]  # mutable counter for closure

                    def on_chunk_start(metadata):
                        text = metadata.get('text', '')
                        sentence_index[0] += 1
                        sse_manager.push_event(session_id, 'sentence_playing', {
                            'text': text,
                            'index': sentence_index[0]
                        })

                    def on_chunk_end(metadata):
                        sse_manager.push_event(session_id, 'sentence_done', {})

                    def on_queue_complete():
                        print(f"🎵 [SSE] All audio played for session {session_id[:8]}...")
                        sse_manager.push_event(session_id, 'response_done', {})

                    audio_player.on_chunk_start = on_chunk_start
                    audio_player.on_chunk_end = on_chunk_end
                    audio_player.on_queue_complete = on_queue_complete
                    audio_player.start_queue_playback()

                # Sentence detector for chunked TTS
                sentence_detector = SentenceDetector(min_length=20, max_length=80)
                full_response = ""

                # TTS worker: synthesizes sentences in parallel with LLM streaming.
                # The LLM loop feeds a queue; this thread drains it so TTS and LLM
                # run concurrently instead of blocking each other.
                import queue as _queue
                tts_sentence_queue = _queue.Queue()

                def _wav_duration(path):
                    import wave
                    try:
                        with wave.open(path) as wf:
                            return wf.getnframes() / wf.getframerate()
                    except Exception:
                        return 0.0

                _tts_sentence_counter = [0]

                def tts_worker():
                    while True:
                        sentence = tts_sentence_queue.get()
                        if sentence is None:  # sentinel — stop worker
                            break
                        try:
                            _tts_sentence_counter[0] += 1
                            _idx = _tts_sentence_counter[0]
                            _t0 = time.perf_counter()
                            audio_file = tts.synthesize_to_temp(
                                sentence,
                                personality_id=_tts_personality,
                                language=_tts_language,
                                gender=_tts_gender,
                            )
                            synth_time = time.perf_counter() - _t0
                            audio_dur = _wav_duration(audio_file) if audio_file else 0.0
                            rtf = synth_time / audio_dur if audio_dur > 0 else 0.0
                            ilog("TTS", f"Frase {_idx}: {synth_time:.2f}s | RTF={rtf:.3f} | \"{sentence[:50]}\"")
                            if audio_file and audio_player and audio_player.is_available():
                                audio_player.enqueue_audio(audio_file, {
                                    'text': sentence,
                                    'cleanup': True
                                })
                        except Exception as e:
                            print(f"❌ [SSE] TTS error: {e}")

                tts_thread = threading.Thread(target=tts_worker, daemon=True, name="TTSWorker")
                tts_thread.start()

                # Append a per-message language reminder to reinforce the system prompt.
                # Small models (gemma3:1b) mirror the user's input language and can
                # override the system prompt instruction — placing the reminder in the
                # user message itself keeps it in the immediate context where it has
                # much stronger weight.
                _LANGUAGE_REMINDERS = {
                    'pt': '[Responda sempre em português brasileiro]',
                    'en': '[Always respond in English, no matter what language I write in]',
                    'es': '[Responde siempre en español, sin importar el idioma que use]',
                }
                _reminder = _LANGUAGE_REMINDERS.get(_tts_language, '')
                _prompted_message = f"{_user_message}\n{_reminder}" if _reminder else _user_message

                # Dispatcher: classify intent and augment system prompt
                _intent = "CHITCHAT"
                try:
                    from voice_assistant import dispatcher as _disp
                    from voice_assistant import rag as _rag_mod
                    from voice_assistant import memory as _mem_mod
                    _intent = _disp.classify(_user_message, language=_tts_language)
                    # Safety net: questions don't store facts. Bridges the common
                    # dispatcher mis-classification where "tomei meu remédio hoje?"
                    # is labeled FACT_STORE and pollutes user_memories with the
                    # question itself + a hallucinated extracted_value.
                    if _intent == "FACT_STORE" and _user_message.rstrip().endswith("?"):
                        ilog("DISPATCH", "FACT_STORE on a question → reclassified as FACT_RECALL")
                        _intent = "FACT_RECALL"
                    ilog("DISPATCH", f"Intent: {_intent}")

                    if _intent == "RAG" and not _is_anonymous and _user and _user.get("specialization_id"):
                        from database import Database as _DBAug
                        _db_aug = _DBAug(_db_path)
                        try:
                            _snippet = _rag_mod.retrieve_context(
                                _db_aug, _user["specialization_id"], _user_message, k=3
                            )
                            if _snippet:
                                _system_prompt += (
                                    "\n\n[Contexto relevante da especialização do assistente"
                                    " — cite quando responder]:\n" + _snippet
                                )
                        finally:
                            _db_aug.close()

                    elif _intent == "FACT_RECALL" and not _is_anonymous and _user_id:
                        from database import Database as _DBAug
                        _db_aug = _DBAug(_db_path)
                        try:
                            _facts = _mem_mod.recall(_db_aug, _user_id, _user_message, limit=5)
                            if _facts:
                                _system_prompt += (
                                    "\n\n[Fatos pessoais relevantes do usuário]:\n" + _facts
                                )
                            else:
                                _prompted_message += (
                                    "\n[Sistema: não há nenhum registro pessoal relacionado a "
                                    "esta pergunta. Responda dizendo que você não tem essa "
                                    "informação registrada. NÃO invente nem suponha fatos.]"
                                )
                        finally:
                            _db_aug.close()
                except Exception as _dispatch_err:
                    print(f"[DISPATCH] non-fatal: {_dispatch_err}")

                # Stream from Ollama — no longer blocked by TTS synthesis
                user_name = _user['name'] if _user else 'Visitante'
                ilog("LLM", f"Geração iniciada (model={_ollama_model}, user={user_name})")
                _llm_t0 = time.perf_counter()
                _llm_ttft = None

                for chunk in ollama_client.generate_streaming_response(
                    prompt=_prompted_message,
                    system_prompt=_system_prompt,
                    conversation_context=_conversation_context,
                    model=_ollama_model
                ):
                    if not chunk:
                        continue

                    if _llm_ttft is None:
                        _llm_ttft = time.perf_counter() - _llm_t0
                        ilog("LLM", f"Primeiro token: {_llm_ttft:.2f}s")

                    full_response += chunk

                    # Push text chunk to browser
                    sse_manager.push_event(session_id, 'text_chunk', {'text': chunk})

                    # Detect sentences and hand off to TTS worker
                    sentences = sentence_detector.add_chunk(chunk)
                    for sentence in sentences:
                        tts_sentence_queue.put(sentence)

                _llm_total = time.perf_counter() - _llm_t0
                ilog("LLM", f"Concluído: {_llm_total:.2f}s | {len(full_response)} chars")

                # Flush remaining text into TTS worker
                final_sentence = sentence_detector.flush()
                if final_sentence:
                    tts_sentence_queue.put(final_sentence)

                # Stop TTS worker and wait for all synthesis to finish
                tts_sentence_queue.put(None)
                tts_thread.join()

                # Signal generation complete
                if audio_player and audio_player.is_available():
                    audio_player.signal_generation_complete()
                else:
                    # No audio player — send response_done immediately
                    sse_manager.push_event(session_id, 'response_done', {})

                # Async FACT_STORE: extract and persist personal fact post-stream
                if _intent == "FACT_STORE" and not _is_anonymous and _user_id:
                    _msg_snap = _user_message
                    _uid_snap = _user_id
                    def _extract_async():
                        try:
                            from database import Database as _DBAsync
                            from voice_assistant import memory as _mem_async
                            _db_x = _DBAsync(_db_path)
                            _mem_async.extract_and_store(_db_x, _uid_snap, _msg_snap, ollama_client)
                            _db_x.close()
                        except Exception as _ex:
                            print(f"[MEMORY] extract failed (non-fatal): {_ex}")
                    threading.Thread(target=_extract_async, daemon=True, name="MemExtract").start()

                # Save assistant response to DB
                if not _is_anonymous and _user_id:
                    try:
                        from database import Database
                        db_thread = Database(_db_path)
                        history = ConversationHistory(db_thread)
                        history.add_message(_user_id, 'assistant', full_response)
                        db_thread.close()
                    except Exception as e:
                        print(f"⚠️  [SSE] Erro ao salvar resposta: {e}")

                print(f"✅ [SSE] Pipeline completa ({len(full_response)} chars)")

            except Exception as e:
                print(f"❌ [SSE] Erro na pipeline: {e}")
                import traceback
                traceback.print_exc()
                sse_manager.push_event(session_id, 'error', {'error': str(e)})

        pipeline_thread = threading.Thread(target=streaming_pipeline, daemon=True, name="StreamingPipeline")
        pipeline_thread.start()

        return jsonify({
            'success': True,
            'session_id': session_id
        })

    except Exception as e:
        print(f"❌ [API] Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/chat/stream/<session_id>')
def api_chat_stream(session_id):
    """SSE stream endpoint — browser connects here with EventSource"""
    return Response(
        stream_with_context(sse_manager.stream_events(session_id)),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/chat/send_sync', methods=['POST'])
def api_chat_send_sync():
    """
    FALLBACK: Blocking chat endpoint (original behavior)
    Kept for backward compatibility during development.
    """
    if not VOICE_ENABLED or not ollama_client or not supertonic_tts_client:
        return jsonify({
            'success': False,
            'error': 'Sistema de voz não disponível'
        }), 503

    try:
        _update_activity()
        data = request.get_json()
        user_message = data.get('message', '').strip()
        rfid = data.get('rfid', '')

        if not user_message:
            return jsonify({'success': False, 'error': 'Mensagem vazia'}), 400

        is_anonymous = (not rfid or rfid == 'anonymous')

        if is_anonymous:
            user = None
            user_id = None
            conversation_context = []
            system_prompt = """Você é um assistente virtual amigável e prestativo.
IMPORTANTE: Responda SEMPRE com no máximo 2-3 frases curtas (menos de 150 caracteres).
Seja direto, objetivo e conciso."""
        else:
            db = get_db()
            user = db.get_user_by_rfid(rfid)

            if not user:
                return jsonify({'success': False, 'error': 'Usuário não encontrado'}), 404

            user_id = user['id']
            history_manager = ConversationHistory(db)
            history_manager.add_message(user_id, 'user', user_message)
            _t_ctx_start = time.perf_counter()
            conversation_context = history_manager.get_context_for_llm(user_id, max_messages=8)
            _t_ctx_ms = (time.perf_counter() - _t_ctx_start) * 1000
            ilog("DB", f"Contexto recuperado: {len(conversation_context)} msgs em {_t_ctx_ms:.2f}ms")
            system_prompt = _build_system_prompt(user)

        user_name = user['name'] if user else 'Visitante'
        print(f"🤖 [API/sync] Gerando resposta para {user_name}...")
        response_text = ollama_client.generate_response(
            prompt=user_message,
            system_prompt=system_prompt,
            conversation_context=conversation_context
        )

        if not response_text:
            return jsonify({'success': False, 'error': 'Erro ao gerar resposta'}), 500

        if not is_anonymous and user_id:
            history_manager.add_message(user_id, 'assistant', response_text)

        audio_url = supertonic_tts_client.synthesize(response_text)

        if not audio_url:
            user_info = {
                'id': user['id'], 'name': user['name'],
                'response_style': user['response_style'], 'language': user['language']
            } if user else {'id': 0, 'name': 'Visitante', 'response_style': 'friendly', 'language': 'pt-BR'}

            return jsonify({
                'success': True, 'response_text': response_text,
                'audio_url': None, 'audio_duration': 0, 'tts_error': True, 'user': user_info
            })

        audio_duration = supertonic_tts_client._estimate_audio_duration(response_text)

        if audio_player and audio_player.is_available():
            audio_file_path = os.path.join(voice_config.audio_static_dir, audio_url.replace('audio/', ''))
            threading.Thread(target=lambda: audio_player.play(audio_file_path, blocking=True), daemon=True).start()

        user_info = {
            'id': user['id'], 'name': user['name'],
            'response_style': user['response_style'], 'language': user['language']
        } if user else {'id': 0, 'name': 'Visitante', 'response_style': 'friendly', 'language': 'pt-BR'}

        return jsonify({
            'success': True, 'response_text': response_text,
            'audio_url': f'/static/{audio_url}', 'audio_duration': audio_duration, 'user': user_info
        })

    except Exception as e:
        print(f"❌ [API/sync] Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/chat/history/<rfid>', methods=['GET'])
def api_chat_history(rfid):
    """
    Recupera histórico de conversa de um usuário
    
    Query params:
        - limit: número de mensagens (padrão: 20)
    
    Response JSON:
        {
            "success": true,
            "history": [
                {"role": "user", "content": "...", "timestamp": "..."},
                {"role": "assistant", "content": "...", "timestamp": "..."}
            ]
        }
    """
    try:
        db = get_db()
        user = db.get_user_by_rfid(rfid)
        
        if not user:
            return jsonify({'success': False, 'error': 'Usuário não encontrado'}), 404
        
        limit = request.args.get('limit', 20, type=int)
        
        history_manager = ConversationHistory(db)
        history = history_manager.get_full_history(user['id'], limit=limit)
        
        return jsonify({
            'success': True,
            'history': history,
            'user': {
                'id': user['id'],
                'name': user['name']
            }
        })
        
    except Exception as e:
        print(f"❌ [API] Erro ao recuperar histórico: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/chat/save', methods=['POST'])
def api_chat_save():
    """
    Salva mensagem no histórico do banco de dados
    
    Request JSON:
        {
            "user_id": 1,
            "role": "user" ou "assistant",
            "content": "texto da mensagem"
        }
    
    Response JSON:
        {
            "success": true,
            "message_id": 123
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Dados não fornecidos'}), 400
        
        user_id = data.get('user_id')
        role = data.get('role')
        content = data.get('content')
        
        # Validações
        if not user_id or not role or not content:
            return jsonify({'success': False, 'error': 'user_id, role e content são obrigatórios'}), 400
        
        if role not in ['user', 'assistant']:
            return jsonify({'success': False, 'error': 'role deve ser "user" ou "assistant"'}), 400
        
        db = get_db()
        history_manager = ConversationHistory(db)
        
        # 🔥 OTIMIZAÇÃO: Removida query duplicada - history_manager já verifica duplicatas
        # A classe ConversationHistory tem lógica interna para evitar duplicatas
        
        # Adiciona a mensagem (com verificação interna de duplicatas)
        message_id = history_manager.add_message(user_id, role, content)
        
        # 🔥 OTIMIZAÇÃO: clear_history() após add_message() para evitar race condition
        # Limita a 10 mensagens - remove as mais antigas
        history_manager.clear_history(user_id, keep_last=10)
        
        return jsonify({
            'success': True,
            'message_id': message_id
        })
        
    except Exception as e:
        print(f"❌ [API] Erro ao salvar mensagem: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/chat/clear/<rfid>', methods=['POST'])
def api_chat_clear(rfid):
    """Limpa histórico de conversa de um usuário"""
    try:
        db = get_db()
        user = db.get_user_by_rfid(rfid)
        
        if not user:
            return jsonify({'success': False, 'error': 'Usuário não encontrado'}), 404
        
        history_manager = ConversationHistory(db)
        removed = history_manager.clear_history(user['id'])
        
        print(f"🧹 [API] Histórico limpo: {removed} mensagens removidas")
        
        return jsonify({
            'success': True,
            'removed': removed
        })
        
    except Exception as e:
        print(f"❌ [API] Erro ao limpar histórico: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/voice/status', methods=['GET'])
def api_voice_status():
    """Retorna status do sistema de voz"""
    status = {
        'voice_enabled': VOICE_ENABLED,
        'ollama_available': False,
        'tts_available': False,
        'audio_player_available': False,
        'whisper_available': False
    }
    
    if VOICE_ENABLED:
        if ollama_client:
            status['ollama_available'] = ollama_client.is_available()
            status['ollama_model'] = voice_config.ollama_model if voice_config else 'unknown'
        
        if supertonic_tts_client:
            status['tts_available'] = supertonic_tts_client.is_available()
            status['tts_model'] = 'supertonic'
        
        if audio_player:
            status['audio_player_available'] = audio_player.is_available()
        
        if whisper_stt:
            status['whisper_available'] = whisper_stt.is_available()
            status['whisper_model'] = voice_config.whisper_model if voice_config else 'unknown'
    
    return jsonify(status)


@app.route('/api/system/battery', methods=['GET'])
def api_system_battery():
    """Retorna status da bateria do UPS HAT"""
    if not BATTERY_AVAILABLE or not battery_monitor:
        return jsonify({'available': False})
    return jsonify(battery_monitor.read())


@app.route('/api/voice/record_and_transcribe', methods=['POST'])
def api_voice_record_and_transcribe():
    """
    Grava áudio do microfone e transcreve com Whisper
    
    Request JSON:
        duration: int (opcional) - duração máxima em segundos (padrão: 5)
    
    Response JSON:
        success: bool
        text: str - texto transcrito
        error: str (se falhar)
    """
    t0 = time.monotonic()
    def tlog(phase):
        print(f"⏱️  [TIMING] record_and_transcribe {phase} T+{time.monotonic() - t0:.3f}s")
    tlog("entry")
    try:
        _update_activity()
        if not VOICE_ENABLED or not whisper_stt:
            return jsonify({
                'success': False,
                'error': 'Whisper STT não disponível'
            }), 503

        data = request.get_json() or {}
        max_duration = data.get('max_duration', 15)

        # Map DB language codes to whisper language codes; fall back to 'pt' (default for anonymous users)
        _WHISPER_LANG_MAP = {'pt-BR': 'pt', 'en-US': 'en', 'es-ES': 'es'}
        raw_lang = data.get('language', '')
        whisper_lang = _WHISPER_LANG_MAP.get(raw_lang, 'pt')
        whisper_stt.config.language = whisper_lang
        print(f"🌐 [API] Whisper language: {whisper_lang} (from '{raw_lang}')")

        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False, dir='/tmp')
        temp_path = temp_file.name
        temp_file.close()

        # Toca o beep de abertura de forma BLOQUEANTE antes de abrir o mic.
        # Garante que o áudio do beep já saiu do ALSA (e do ar) quando começarmos
        # a gravar, eliminando a necessidade do descarte inicial de 700ms no VAD.
        tlog("beep_sync_start")
        print(f"🔊 [API] Tocando beep (sync) antes de gravar...")
        play_audio_feedback_sync('chat_open')
        tlog("beep_sync_end")
        # Pequena folga para a reverberação acústica da sala decair
        time.sleep(0.1)
        tlog("after_beep_sleep")

        # Libera o mic para o Whisper (openWakeWord usa o mesmo dispositivo)
        if wake_word_manager and hasattr(wake_word_manager, 'pause'):
            tlog("oww_pause_start")
            wake_word_manager.pause()
            tlog("oww_pause_end")
        ilog("STT", f"Gravação iniciada (lang={whisper_lang}, max={max_duration}s)")
        try:
            print(f"🎤 [API] Recording with VAD (max {max_duration}s)...")
            tlog("record_utterance_start")
            speech_captured = whisper_stt.record_utterance_to_file(temp_path, max_duration=max_duration)
            tlog(f"record_utterance_end captured={speech_captured}")
        finally:
            if wake_word_manager and hasattr(wake_word_manager, 'resume'):
                tlog("oww_resume_start")
                wake_word_manager.resume()
                tlog("oww_resume_end")

        if not speech_captured:
            try:
                os.remove(temp_path)
            except Exception:
                pass
            tlog("return_no_speech")
            return jsonify({
                'success': False,
                'error': 'Nenhum som detectado. Fale mais alto.'
            }), 400

        # Transcreve com Whisper
        print(f"🔄 [API] Transcrevendo com Whisper...")
        tlog("whisper_transcribe_start")
        _stt_t0 = time.perf_counter()

        text = whisper_stt._transcribe_audio_file(temp_path)
        tlog("whisper_transcribe_end")

        # Remove arquivo temporário
        try:
            os.remove(temp_path)
        except:
            pass

        import re
        cleaned = re.sub(r'\[.*?\]', '', text or '').strip()
        if cleaned:
            _stt_elapsed = time.perf_counter() - _stt_t0
            ilog("STT", f"Transcrição concluída em {_stt_elapsed:.2f}s → \"{cleaned}\"")
            print(f"✅ [API] Transcrito: '{cleaned}'")
            tlog("return_success")
            return jsonify({
                'success': True,
                'text': cleaned
            })
        else:
            print(f"⚠️  [API] Nenhuma fala detectada (raw: '{text}')")
            tlog("return_empty_transcription")
            return jsonify({
                'success': False,
                'error': 'Não consegui entender. Tente novamente.'
            }), 400
            
    except Exception as e:
        import traceback
        print(f"❌ [API] Erro ao processar áudio: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def play_audio_feedback(sound_name: str):
    """
    Toca som de feedback no hardware (não-bloqueante)

    Args:
        sound_name: Nome do arquivo sem extensão (ex: 'chat_open', 'message_sent')
    """
    if not audio_player or not audio_player.is_available():
        return False

    try:
        sound_path = os.path.join('static', 'sounds', f'{sound_name}.wav')
        if os.path.exists(sound_path):
            # Define volume máximo (100%) para sons de feedback
            audio_player.set_volume(1.0)
            # Toca de forma não-bloqueante
            threading.Thread(target=lambda: audio_player.play(sound_path, blocking=True), daemon=True).start()
            return True
        else:
            print(f"⚠️  Som não encontrado: {sound_path}")
            return False
    except Exception as e:
        print(f"❌ Erro ao tocar som: {e}")
        return False


def play_audio_feedback_sync(sound_name: str):
    """Toca som de feedback e só retorna quando o áudio terminou de tocar."""
    if not audio_player or not audio_player.is_available():
        return False
    try:
        sound_path = os.path.join('static', 'sounds', f'{sound_name}.wav')
        if not os.path.exists(sound_path):
            print(f"⚠️  Som não encontrado: {sound_path}")
            return False
        audio_player.set_volume(1.0)
        audio_player.play(sound_path, blocking=True)
        return True
    except Exception as e:
        print(f"❌ Erro ao tocar som (sync): {e}")
        return False


@app.route('/api/feedback/play/<sound_name>', methods=['POST'])
def api_play_feedback(sound_name):
    """Toca som de feedback"""
    success = play_audio_feedback(sound_name)
    return jsonify({'success': success})


@app.route('/api/wake_word_status', methods=['GET'])
def api_wake_word_status():
    """
    Verifica se wake word foi detectado (openWakeWord).
    Consumo único - flag é limpa após leitura.

    Response JSON:
        {
            "wake_detected": true/false,
            "timestamp": "2024-02-06T12:34:56",
            "connected": true/false,
            "mode": "openwakeword"
        }
    """
    global wake_word_manager
    
    wake_detected = False
    connected = False
    
    if wake_word_manager:
        wake_detected = wake_word_manager.check_and_clear_wake()
        connected = wake_word_manager.running  # É uma propriedade, não método

    if wake_detected:
        print(f"⏱️  [TIMING] wake_word_status wake_detected=True t={time.monotonic():.3f}")

    return jsonify({
        'wake_detected': wake_detected,
        'timestamp': datetime.now().isoformat(),
        'connected': connected,
        'mode': 'openwakeword'
    })


# Mapping from DB response_style values to personality IDs
RESPONSE_STYLE_TO_PERSONALITY = {
    'short (objective)': 'short',
    'neutral (balanced)': 'neutral',
    'detailed (explanatory)': 'detailed',
    'formal (business)': 'formal',
    'casual (chatty)': 'casual',
}


def _localize_system_prompt(prompt: str, language_code: str) -> str:
    """
    Appends the appropriate language instruction to a personality prompt
    based on the user's chosen language.
    """
    LANGUAGE_INSTRUCTIONS = {
        'pt-BR': 'Sempre responda em português brasileiro, independentemente do idioma da pergunta.',
        'en-US': 'Always respond in English, regardless of the language of the question.',
        'es-ES': 'Siempre responde en español, independientemente del idioma de la pregunta.',
    }
    instruction = LANGUAGE_INSTRUCTIONS.get(language_code, LANGUAGE_INSTRUCTIONS['pt-BR'])
    return prompt.rstrip() + ' ' + instruction


def _build_system_prompt(user) -> str:
    """
    Constrói system prompt baseado nas preferências do usuário.
    Uses personality system if available, falls back to hardcoded prompts.

    Args:
        user: Row do banco com dados do usuário

    Returns:
        System prompt customizado
    """
    # Try personality system first
    personality_id = RESPONSE_STYLE_TO_PERSONALITY.get(user['response_style'], 'neutral')

    if personality_manager:
        personality = personality_manager.get_personality(personality_id)
        if personality and 'system_prompt' in personality:
            prompt = personality['system_prompt'].strip()
            return _localize_system_prompt(prompt, user['language'])

    # Fallback: hardcoded prompts (same as before)
    style_instructions = {
        'short (objective)': 'Seja breve e objetivo. Respostas curtas e diretas.',
        'neutral (balanced)': 'Mantenha equilíbrio entre brevidade e explicação.',
        'detailed (explanatory)': 'Forneça explicações detalhadas e completas.',
        'formal (business)': 'Use linguagem formal e profissional.',
        'casual (chatty)': 'Use linguagem casual e amigável, como em uma conversa.'
    }

    language_map = {
        'pt-BR': 'português brasileiro',
        'en-US': 'inglês',
        'es-ES': 'espanhol'
    }

    style = style_instructions.get(user['response_style'], style_instructions['neutral (balanced)'])
    language = language_map.get(user['language'], 'português brasileiro')

    return f"""Você é um assistente virtual útil e prestativo.
Sempre responda em {language}.
{style}
Seja natural e mantenha o contexto da conversa."""


def _resolve_personality_for_user(user) -> str:
    """Resolve personality ID from user's response_style."""
    return RESPONSE_STYLE_TO_PERSONALITY.get(
        user['response_style'] if user else 'neutral (balanced)',
        'neutral'
    )


# ========== ERRO 404 ==========

@app.errorhandler(404)
def page_not_found(e):
    """Página não encontrada"""
    return redirect(url_for('index'))


# ========== INICIALIZAÇÃO ==========

if __name__ == '__main__':
    print("=" * 70)
    print("SISTEMA DE CADASTRO DE USUÁRIOS RFID")
    print("=" * 70)
    print()
    print("Servidor iniciado em:")
    print("  → http://localhost:5000")
    print("  → http://127.0.0.1:5000")
    print()
    print("Sistema rodando 100% OFFLINE (sem internet)")
    print()
    print("Pressione Ctrl+C para parar o servidor")
    print("=" * 70)
    print()
    
    # Servidor local (offline)
    # host='127.0.0.1' = apenas localhost (máxima segurança)
    app.run(
        debug=True,
        use_reloader=False,  # Desativa reloader para que SIGINT chegue ao processo correto
        host='127.0.0.1',  # Apenas localhost (offline)
        port=5000,
        threaded=True
    )
