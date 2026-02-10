#!/bin/bash
# TalkingBuddy Voice Assistant - Enhanced Wrapper Script
# Handles pre-flight checks, process cleanup, and graceful error handling

# ============================================================================
# SCRIPT SETUP
# ============================================================================

# Get script directory and change to it
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Exit codes
EXIT_SUCCESS=0
EXIT_VENV_MISSING=1
EXIT_WHISPER_MISSING=2
EXIT_PIPER_MISSING=3
EXIT_OLLAMA_MISSING=4
EXIT_CLEANUP_FAILED=5

# ============================================================================
# ENVIRONMENT VARIABLE OVERRIDES
# ============================================================================

SKIP_CHECKS="${SKIP_CHECKS:-0}"
SKIP_CLEANUP="${SKIP_CLEANUP:-0}"
DEBUG="${DEBUG:-0}"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

check_file() {
    if [ ! -f "$1" ]; then
        return 1
    fi
    return 0
}

check_file_size() {
    local file="$1"
    local min_size="$2"
    if [ ! -f "$file" ]; then
        return 1
    fi
    local size=$(stat -c%s "$file" 2>/dev/null || echo "0")
    if [ "$size" -lt "$min_size" ]; then
        return 1
    fi
    return 0
}

show_error() {
    echo ""
    echo "❌ $1"
    if [ -n "$2" ]; then
        echo ""
        echo "   $2"
    fi
}

debug_log() {
    if [ "$DEBUG" = "1" ]; then
        echo "[DEBUG] $1"
    fi
}

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

run_preflight_checks() {
    echo "🔍 Checking system requirements..."

    local all_checks_passed=1

    # ========================================================================
    # CHECK 1: Virtual Environment (FATAL)
    # ========================================================================
    debug_log "Checking virtual environment..."
    if [ ! -d "venv" ] || [ ! -f "venv/bin/activate" ]; then
        show_error "Virtual environment not found" \
                   "The Python virtual environment is missing or incomplete."
        echo ""
        echo "   How to fix:"
        echo "   1. Run setup script: bash setup.sh"
        echo "   2. Wait for completion (15-30 minutes)"
        echo ""
        echo "   💡 Tip: The venv/ directory should exist in $SCRIPT_DIR"
        return $EXIT_VENV_MISSING
    fi
    echo "✅ Virtual environment"

    # ========================================================================
    # CHECK 2: Whisper Binary (FATAL)
    # ========================================================================
    debug_log "Checking Whisper binary..."
    local whisper_binary="$HOME/whisper.cpp/build/bin/whisper-cli"
    if ! check_file "$whisper_binary"; then
        show_error "Whisper binary not found" \
                   "The whisper-cli executable is missing."
        echo ""
        echo "   Expected location: $whisper_binary"
        echo ""
        echo "   Possible causes:"
        echo "   • Whisper.cpp not installed"
        echo "   • Build failed during setup"
        echo "   • Binary was deleted or moved"
        echo ""
        echo "   How to fix:"
        echo "   1. Check installation: ls -la ~/whisper.cpp/build/bin/"
        echo "   2. Re-run setup if missing: bash setup.sh"
        echo "   3. Manual build: cd ~/whisper.cpp/build && cmake --build ."
        echo ""
        echo "   💡 Tip: The setup script should have built this automatically"
        return $EXIT_WHISPER_MISSING
    fi
    echo "✅ Whisper binary"

    # ========================================================================
    # CHECK 3: Whisper Model (FATAL)
    # ========================================================================
    debug_log "Checking Whisper model..."
    local whisper_model="$HOME/whisper.cpp/models/ggml-base.bin"
    if ! check_file_size "$whisper_model" 100000000; then
        show_error "Whisper model not found or corrupted" \
                   "The ggml-base.bin model file is missing or incomplete."
        echo ""
        echo "   Expected location: $whisper_model"
        echo "   Expected size: >100MB (~140MB)"
        echo ""
        echo "   Possible causes:"
        echo "   • Model not downloaded"
        echo "   • Download was interrupted"
        echo "   • File was corrupted or deleted"
        echo ""
        echo "   How to fix:"
        echo "   1. Check if file exists: ls -lh ~/whisper.cpp/models/ggml-base.bin"
        echo "   2. Remove if corrupted: rm ~/whisper.cpp/models/ggml-base.bin"
        echo "   3. Re-download: cd ~/whisper.cpp/models && bash download-ggml-model.sh base"
        echo "   4. Or re-run setup: bash setup.sh"
        echo ""
        echo "   💡 Tip: Download takes 2-5 minutes depending on connection speed"
        return $EXIT_WHISPER_MISSING
    fi
    echo "✅ Whisper model"

    # ========================================================================
    # CHECK 4: TTS Engines (WARNING ONLY - Non-fatal)
    # ========================================================================
    debug_log "Checking TTS engines..."

    # Check Piper TTS
    local piper_binary="$HOME/piper/piper/piper"
    local piper_model="$HOME/piper/piper/pt_BR-faber-medium.onnx"
    local piper_available=0

    if check_file "$piper_binary" && check_file_size "$piper_model" 50000000; then
        echo "✅ Piper TTS (Portuguese)"
        piper_available=1
    else
        echo "⚠️  Piper TTS not found (Portuguese TTS unavailable)"
        debug_log "Piper binary: $piper_binary"
        debug_log "Piper model: $piper_model"
    fi

    # Check Supertonic TTS
    local supertonic_available=0
    if python -c "import supertonic" 2>/dev/null; then
        echo "✅ Supertonic 2 TTS (Multilingual: pt, en, es)"
        supertonic_available=1
    else
        echo "⚠️  Supertonic 2 TTS not installed (multilingual TTS unavailable)"
    fi

    # At least one TTS engine must be available
    if [ $piper_available -eq 0 ] && [ $supertonic_available -eq 0 ]; then
        show_error "No TTS engines found" \
                   "At least one TTS engine (Piper or Supertonic) must be installed."
        echo ""
        echo "   How to fix:"
        echo "   1. Re-run setup: bash setup.sh"
        echo "   2. Or install Supertonic manually: pip install supertonic"
        echo ""
        echo "   💡 Tip: Supertonic is 9x faster and supports multiple languages"
        return $EXIT_PIPER_MISSING
    fi

    if [ $supertonic_available -eq 1 ]; then
        echo "   💡 Tip: Use --tts-engine supertonic for 9x faster, multilingual TTS"
    fi

    # ========================================================================
    # CHECK 6: Ollama Service (FATAL)
    # ========================================================================
    debug_log "Checking Ollama service..."
    local ollama_accessible=0
    local max_retries=3
    local retry_delay=2

    for i in $(seq 1 $max_retries); do
        debug_log "Ollama check attempt $i/$max_retries..."
        if curl -s -f --max-time 5 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            ollama_accessible=1
            break
        fi
        if [ $i -lt $max_retries ]; then
            debug_log "Retry in ${retry_delay}s..."
            sleep $retry_delay
        fi
    done

    if [ $ollama_accessible -eq 0 ]; then
        show_error "Ollama service not accessible" \
                   "Cannot connect to Ollama API at http://127.0.0.1:11434"
        echo ""
        echo "   Possible causes:"
        echo "   • Service not running"
        echo "   • Port 11434 blocked or in use by another process"
        echo "   • Service still starting up (initial startup takes 30s)"
        echo "   • Service crashed or failed to start"
        echo ""
        echo "   How to fix:"
        echo "   1. Check status: sudo systemctl status ollama"
        echo "   2. Start service: sudo systemctl start ollama"
        echo "   3. Check logs: journalctl -u ollama -n 50"
        echo "   4. Test manually: curl http://127.0.0.1:11434/api/tags"
        echo ""
        echo "   💡 Tip: Wait 30 seconds after starting Ollama for full initialization"
        return $EXIT_OLLAMA_MISSING
    fi
    echo "✅ Ollama service"

    # ========================================================================
    # CHECK 7: Serial Port (WARNING ONLY - Non-fatal)
    # ========================================================================
    debug_log "Checking serial port..."
    if [ ! -e "/dev/ttyACM0" ]; then
        echo "⚠️  Serial port not found (/dev/ttyACM0)"
        echo "    💡 Use --wake-mode keyboard if ESP32 is not connected"
    else
        echo "✅ Serial port"
    fi

    echo ""
    return 0
}

# ============================================================================
# PROCESS CLEANUP
# ============================================================================

cleanup_existing_processes() {
    debug_log "Looking for existing run_chatbot.py processes..."

    # Find all run_chatbot.py processes
    local pids=$(pgrep -f "python.*run_chatbot.py" 2>/dev/null)

    if [ -z "$pids" ]; then
        debug_log "No existing processes found"
        return 0
    fi

    echo "🧹 Cleaning up existing processes..."
    local pid_count=$(echo "$pids" | wc -w)
    debug_log "Found $pid_count process(es): $pids"

    # Send SIGTERM for graceful shutdown
    debug_log "Sending SIGTERM..."
    kill -TERM $pids 2>/dev/null || true

    # Wait up to 5 seconds for graceful termination
    local waited=0
    local max_wait=5
    while [ $waited -lt $max_wait ]; do
        sleep 0.5
        waited=$((waited + 1))

        # Check if processes are still running
        if ! pgrep -f "python.*run_chatbot.py" >/dev/null 2>&1; then
            debug_log "Processes terminated gracefully after ${waited}*0.5s"
            echo "✅ Terminated $pid_count existing instance(s)"
            return 0
        fi
    done

    # Force kill if still running after timeout
    debug_log "Processes still running after ${max_wait}s, sending SIGKILL..."
    local remaining_pids=$(pgrep -f "python.*run_chatbot.py" 2>/dev/null)
    if [ -n "$remaining_pids" ]; then
        kill -9 $remaining_pids 2>/dev/null || true
        sleep 0.5

        # Final check
        if pgrep -f "python.*run_chatbot.py" >/dev/null 2>&1; then
            show_error "Failed to terminate existing processes" \
                       "Some processes may be stuck. Try manually: pkill -9 -f run_chatbot.py"
            return $EXIT_CLEANUP_FAILED
        fi
        echo "✅ Force-terminated $pid_count existing instance(s)"
    fi

    return 0
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    # Run pre-flight checks (unless skipped)
    if [ "$SKIP_CHECKS" != "1" ]; then
        if ! run_preflight_checks; then
            exit $?
        fi
    else
        echo "⏭️  Skipping pre-flight checks (SKIP_CHECKS=1)"
        echo ""
    fi

    # Cleanup existing processes (unless skipped)
    if [ "$SKIP_CLEANUP" != "1" ]; then
        if ! cleanup_existing_processes; then
            exit $?
        fi
    else
        echo "⏭️  Skipping process cleanup (SKIP_CLEANUP=1)"
        echo ""
    fi

    # Activate virtual environment
    debug_log "Activating virtual environment..."
    source venv/bin/activate

    # Launch chatbot with all arguments
    echo "🚀 Starting TalkingBuddy Voice Chatbot..."
    echo ""

    # Execute Python script and propagate exit code
    python src/run_chatbot.py "$@"
    exit_code=$?

    debug_log "Python script exited with code: $exit_code"
    exit $exit_code
}

# Run main function
main "$@"
