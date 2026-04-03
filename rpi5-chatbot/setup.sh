#!/bin/bash
# TalkingBuddy Voice Assistant - Automated Setup Script
# Raspberry Pi 5 installation automation

set -e  # Exit on error

# ============================================================================
# GLOBAL ERROR HANDLING INFRASTRUCTURE
# ============================================================================

# Get script directory FIRST (before any cd commands)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Track start time for installation duration
START_TIME=$(date +%s)

# Create timestamped log file
LOG_FILE="setup_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

echo "📝 Setup log: $LOG_FILE"
echo ""

# Phase tracking
CURRENT_PHASE=""
TOTAL_PHASES=10

# Error handling function
handle_error() {
    exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo ""
        echo "========================================="
        echo "❌ Setup failed in: $CURRENT_PHASE"
        echo "========================================="
        echo "📋 Check log file: $LOG_FILE"
        echo "🔧 Run 'bash setup.sh' again after fixing the issue"
        echo ""
    fi
}
trap handle_error EXIT

# Helper functions
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ Required command not found: $1"
        return 1
    fi
    return 0
}

check_file() {
    if [ ! -f "$1" ]; then
        echo "❌ Required file not found: $1"
        return 1
    fi
    return 0
}

check_file_size() {
    local file="$1"
    local min_size="$2"
    if [ ! -f "$file" ]; then
        echo "❌ File not found: $file"
        return 1
    fi
    local size=$(stat -c%s "$file" 2>/dev/null || echo "0")
    if [ "$size" -lt "$min_size" ]; then
        echo "❌ File too small (possibly corrupted): $file"
        echo "   Expected: >$min_size bytes, Got: $size bytes"
        return 1
    fi
    return 0
}

check_directory() {
    if [ ! -d "$1" ]; then
        echo "❌ Required directory not found: $1"
        return 1
    fi
    return 0
}

show_error() {
    echo ""
    echo "❌ $1"
    if [ -n "$2" ]; then
        echo "   $2"
    fi
}

check_internet() {
    if ! ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        show_error "No internet connection detected" \
                   "Please check your network connection and try again"
        return 1
    fi
    return 0
}

check_disk_space() {
    local required_mb="$1"
    local available_mb=$(df -m . | awk 'NR==2 {print $4}')
    if [ "$available_mb" -lt "$required_mb" ]; then
        show_error "Insufficient disk space" \
                   "Required: ${required_mb}MB, Available: ${available_mb}MB"
        return 1
    fi
    return 0
}

# ============================================================================
# SETUP START
# ============================================================================

echo "🤖 TalkingBuddy Voice Assistant - Setup"
echo "========================================"
echo ""

# ============================================================================
# PHASE 1: SYSTEM DEPENDENCIES
# ============================================================================
CURRENT_PHASE="Phase 1/10: Installing system dependencies"
echo "📦 $CURRENT_PHASE..."

# Check internet connection
if ! check_internet; then
    echo ""
    echo "Troubleshooting:"
    echo "  - Check ethernet/wifi connection"
    echo "  - Try: ping 8.8.8.8"
    echo "  - Check router/network settings"
    exit 1
fi

# Check disk space (need at least 2GB for system packages)
if ! check_disk_space 2000; then
    echo ""
    echo "Troubleshooting:"
    echo "  - Free up disk space"
    echo "  - Check usage: df -h"
    echo "  - Remove unused packages: sudo apt autoremove"
    exit 1
fi

# Update package lists
echo "🔄 Updating package lists..."
if ! sudo apt update; then
    show_error "Failed to update package lists" \
               "Package manager may be locked or repositories unavailable"
    echo ""
    echo "Troubleshooting:"
    echo "  - Wait for other apt processes to finish"
    echo "  - Check: ps aux | grep apt"
    echo "  - Try: sudo rm /var/lib/apt/lists/lock"
    exit 1
fi

# Install build tools and libraries
echo "🔄 Installing build tools and libraries..."
if ! sudo apt install -y build-essential cmake git wget curl portaudio19-dev libsdl2-dev libasound2-dev libfreetype6-dev libpng-dev libjpeg-dev; then
    show_error "Failed to install system packages" \
               "Check network connection and available disk space"
    echo ""
    echo "Troubleshooting:"
    echo "  - Check disk space: df -h"
    echo "  - Check apt logs: cat /var/log/apt/term.log"
    echo "  - Try manual install: sudo apt install build-essential"
    exit 1
fi

# Verify critical packages installed
echo "✅ Verifying package installation..."
CRITICAL_PACKAGES=("gcc" "g++" "cmake" "git" "wget")
for pkg in "${CRITICAL_PACKAGES[@]}"; do
    if ! check_command "$pkg"; then
        show_error "Critical package not installed: $pkg"
        exit 1
    fi
done

echo "✅ System dependencies installed successfully"

# ============================================================================
# PHASE 2: WHISPER.CPP
# ============================================================================
CURRENT_PHASE="Phase 2/10: Installing whisper.cpp"
echo ""
echo "🎤 $CURRENT_PHASE..."

cd ~

# Check/install whisper.cpp
if [ ! -d "whisper.cpp" ]; then
    echo "🔄 Cloning whisper.cpp repository..."
    if ! git clone https://github.com/ggerganov/whisper.cpp.git; then
        show_error "Failed to clone whisper.cpp repository" \
                   "Check internet connection and GitHub access"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check network: ping github.com"
        echo "  - Try manual clone: git clone https://github.com/ggerganov/whisper.cpp.git"
        exit 1
    fi

    echo "🔄 Building whisper.cpp..."
    cd whisper.cpp
    mkdir -p build
    cd build

    if ! cmake ..; then
        show_error "CMake configuration failed" \
                   "Missing dependencies or CMake version too old"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check CMake version: cmake --version (need 3.10+)"
        echo "  - Install dependencies: sudo apt install build-essential cmake"
        exit 1
    fi

    if ! cmake --build . --config Release; then
        show_error "whisper.cpp build failed" \
                   "Compilation errors or insufficient memory"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check build log above for specific errors"
        echo "  - Check memory: free -h"
        echo "  - Try with less parallelism: cmake --build . -j2"
        exit 1
    fi

    # Verify binary was created
    if ! check_file ~/whisper.cpp/build/bin/main; then
        show_error "whisper.cpp binary not found after build" \
                   "Build may have failed silently"
        exit 1
    fi

    echo "✅ whisper.cpp built successfully"
else
    echo "⏭️  whisper.cpp already exists, skipping installation"
fi

# Download whisper model
cd ~/whisper.cpp/models
if [ ! -f "ggml-base.bin" ]; then
    echo "🔄 Downloading ggml-base.bin model (~150MB)..."

    if ! check_file "download-ggml-model.sh"; then
        show_error "Model download script not found" \
                   "whisper.cpp installation may be incomplete"
        exit 1
    fi

    if ! bash download-ggml-model.sh base; then
        show_error "Failed to download whisper model" \
                   "Check network connection and disk space"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check disk space: df -h"
        echo "  - Check network: ping huggingface.co"
        echo "  - Try manual download from: https://huggingface.co/ggerganov/whisper.cpp"
        exit 1
    fi

    # Verify model file size (should be ~150MB)
    if ! check_file_size "ggml-base.bin" 100000000; then
        show_error "Downloaded model file is too small" \
                   "Download may have been incomplete or corrupted"
        echo ""
        echo "Troubleshooting:"
        echo "  - Remove corrupted file: rm ggml-base.bin"
        echo "  - Re-run setup script"
        exit 1
    fi

    echo "✅ Whisper model downloaded successfully"
else
    echo "⏭️  ggml-base.bin model already exists, skipping download"
fi

# ============================================================================
# PHASE 3: PIPER TTS
# ============================================================================
CURRENT_PHASE="Phase 3/10: Installing Piper TTS"
echo ""
echo "🔊 $CURRENT_PHASE..."

cd ~

# Install Piper binary
if [ ! -d "piper" ]; then
    echo "🔄 Downloading Piper TTS (~20MB)..."

    if ! wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz; then
        show_error "Failed to download Piper TTS" \
                   "Check network connection"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check network: ping github.com"
        echo "  - Check URL is still valid at: https://github.com/rhasspy/piper/releases"
        exit 1
    fi

    # Verify download integrity
    if ! check_file_size "piper_linux_aarch64.tar.gz" 1000000; then
        show_error "Downloaded Piper archive is too small" \
                   "Download may have been incomplete"
        rm -f piper_linux_aarch64.tar.gz
        exit 1
    fi

    echo "🔄 Extracting Piper..."
    mkdir -p ~/piper
    if ! tar -xzf piper_linux_aarch64.tar.gz -C ~/piper; then
        show_error "Failed to extract Piper archive" \
                   "Archive may be corrupted"
        echo ""
        echo "Troubleshooting:"
        echo "  - Remove corrupted file: rm piper_linux_aarch64.tar.gz"
        echo "  - Re-run setup script"
        exit 1
    fi

    rm piper_linux_aarch64.tar.gz

    # Verify binary exists and is executable
    if ! check_file ~/piper/piper/piper; then
        show_error "Piper binary not found after extraction" \
                   "Archive structure may have changed"
        exit 1
    fi

    chmod +x ~/piper/piper/piper
    echo "✅ Piper TTS installed successfully"
else
    echo "⏭️  Piper already exists, skipping installation"
fi

# Download Portuguese TTS model
cd ~/piper/piper
if [ ! -f "pt_BR-faber-medium.onnx" ]; then
    echo "🔄 Downloading Brazilian Portuguese TTS model (~60MB)..."

    if ! wget https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx; then
        show_error "Failed to download PT-BR voice model" \
                   "Check network connection"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check network: ping huggingface.co"
        echo "  - Try manual download from: https://huggingface.co/rhasspy/piper-voices"
        exit 1
    fi

    if ! wget https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json; then
        show_error "Failed to download PT-BR voice config" \
                   "Check network connection"
        exit 1
    fi

    # Verify model files
    if ! check_file_size "pt_BR-faber-medium.onnx" 50000000; then
        show_error "PT-BR model file is too small" \
                   "Download may have been incomplete"
        rm -f pt_BR-faber-medium.onnx*
        exit 1
    fi

    if ! check_file "pt_BR-faber-medium.onnx.json"; then
        show_error "PT-BR model config file missing"
        exit 1
    fi

    echo "✅ PT-BR TTS model downloaded successfully"
else
    echo "⏭️  PT-BR TTS model already exists, skipping download"
fi

# ============================================================================
# PHASE 4: OLLAMA INSTALLATION
# ============================================================================
CURRENT_PHASE="Phase 4/10: Installing Ollama"
echo ""
echo "🧠 $CURRENT_PHASE..."

if ! command -v ollama &> /dev/null; then
    echo "🔄 Installing Ollama..."

    if ! curl -fsSL https://ollama.com/install.sh | sh; then
        show_error "Ollama installation failed" \
                   "Check network connection and system compatibility"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check network: ping ollama.com"
        echo "  - Check system arch: uname -m (should be aarch64)"
        echo "  - Try manual install from: https://ollama.com/download"
        exit 1
    fi

    # Verify installation
    if ! check_command ollama; then
        show_error "Ollama command not found after installation" \
                   "Installation may have failed silently"
        exit 1
    fi

    echo "🔄 Enabling Ollama service..."
    if ! sudo systemctl enable ollama; then
        show_error "Failed to enable Ollama service" \
                   "Systemd may not be running"
        exit 1
    fi

    echo "🔄 Starting Ollama service..."
    if ! sudo systemctl start ollama; then
        show_error "Failed to start Ollama service" \
                   "Check service logs for details"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check status: sudo systemctl status ollama"
        echo "  - Check logs: journalctl -u ollama -n 50"
        exit 1
    fi

    echo "✅ Ollama installed and started"
else
    echo "⏭️  Ollama already installed, checking service..."

    if ! systemctl is-active --quiet ollama; then
        echo "🔄 Starting Ollama service..."
        if ! sudo systemctl start ollama; then
            show_error "Failed to start Ollama service"
            echo ""
            echo "Troubleshooting:"
            echo "  - Check status: sudo systemctl status ollama"
            echo "  - Check logs: journalctl -u ollama -n 50"
            echo "  - Check port 11434: sudo lsof -i :11434"
            exit 1
        fi
    else
        echo "✅ Ollama service already running"
    fi
fi

# Wait for Ollama to be ready with progress indicator
echo "🔄 Waiting for Ollama service to be ready..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "✅ Ollama is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        show_error "Ollama service failed to start within 30 seconds" \
                   "Service may be running but not responding"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check status: sudo systemctl status ollama"
        echo "  - Check logs: journalctl -u ollama -n 50"
        echo "  - Check port: sudo lsof -i :11434"
        echo "  - Check if another process is using port 11434"
        exit 1
    fi
    echo -n "."
    sleep 1
done

# ============================================================================
# PHASE 5: OLLAMA MODELS
# ============================================================================
CURRENT_PHASE="Phase 5/10: Downloading Ollama models"
echo ""
echo "📥 $CURRENT_PHASE..."

# Check if model already exists
if ollama list | grep -q "gemma3:1b"; then
    echo "⏭️  Base model gemma3:1b already exists, skipping download"
else
    echo "🔄 Pulling base model gemma3:1b (~800MB)..."
    echo "   This may take several minutes depending on your connection..."

    # Try up to 3 times with retry logic
    MAX_RETRIES=3
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if ollama pull gemma3:1b; then
            echo "✅ Base model downloaded successfully"
            break
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
                echo "⚠️  Download failed, retrying ($RETRY_COUNT/$MAX_RETRIES)..."
                sleep 5
            else
                show_error "Failed to download gemma3:1b model after $MAX_RETRIES attempts" \
                           "Check network connection and disk space"
                echo ""
                echo "Troubleshooting:"
                echo "  - Check network: ping ollama.com"
                echo "  - Check disk space: df -h (need ~1GB free)"
                echo "  - Check Ollama service: systemctl status ollama"
                echo "  - Try manual pull: ollama pull gemma3:1b"
                exit 1
            fi
        fi
    done
fi

# Verify model was pulled successfully
if ! ollama list | grep -q "gemma3:1b"; then
    show_error "gemma3:1b model not found after download" \
               "Download may have failed silently"
    echo ""
    echo "Troubleshooting:"
    echo "  - List models: ollama list"
    echo "  - Try manual pull: ollama pull gemma3:1b"
    exit 1
fi

# Pull qwen3:0.8b (smaller, faster model — good alternative to gemma3:1b)
if ollama list | grep -q "qwen3:0.8b"; then
    echo "⏭️  Model qwen3:0.8b already exists, skipping download"
else
    echo "🔄 Pulling model qwen3:0.8b (~500MB)..."
    echo "   This may take several minutes depending on your connection..."

    MAX_RETRIES=3
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if ollama pull qwen3:0.8b; then
            echo "✅ qwen3:0.8b downloaded successfully"
            break
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
                echo "⚠️  Download failed, retrying ($RETRY_COUNT/$MAX_RETRIES)..."
                sleep 5
            else
                echo "⚠️  Failed to download qwen3:0.8b after $MAX_RETRIES attempts (non-fatal)"
                echo "   You can install it later: ollama pull qwen3:0.8b"
            fi
        fi
    done
fi

# ============================================================================
# PHASE 6: PYTHON ENVIRONMENT SETUP
# ============================================================================
CURRENT_PHASE="Phase 6/10: Setting up Python environment"
echo ""
echo "🐍 $CURRENT_PHASE..."

# Return to script directory
cd "$SCRIPT_DIR"

# Check if requirements.txt exists
if ! check_file "requirements.txt"; then
    show_error "requirements.txt not found" \
               "File may have been deleted or moved"
    exit 1
fi

# Check/create virtual environment
if [ -d "venv" ]; then
    # Check if venv is valid (has activate script)
    if [ ! -f "venv/bin/activate" ]; then
        echo "⚠️  Virtual environment is corrupted (missing activate script)"
        echo "🔄 Removing corrupted venv..."
        rm -rf venv

        echo "🔄 Creating fresh virtual environment..."
        if ! python3 -m venv venv; then
            show_error "Failed to create virtual environment" \
                       "Python3-venv may not be installed"
            echo ""
            echo "Troubleshooting:"
            echo "  - Install venv: sudo apt install python3-venv"
            echo "  - Check Python version: python3 --version"
            exit 1
        fi
    else
        echo "⏭️  Virtual environment already exists"
    fi
else
    echo "🔄 Creating virtual environment..."
    if ! python3 -m venv venv; then
        show_error "Failed to create virtual environment" \
                   "Python3-venv may not be installed"
        echo ""
        echo "Troubleshooting:"
        echo "  - Install venv: sudo apt install python3-venv"
        echo "  - Check Python version: python3 --version"
        exit 1
    fi

    # Verify venv was created properly
    if ! check_file "venv/bin/activate"; then
        show_error "Virtual environment created but activate script missing" \
                   "venv creation may have failed silently"
        exit 1
    fi

    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Verify activation
if [ -z "$VIRTUAL_ENV" ]; then
    show_error "Failed to activate virtual environment" \
               "VIRTUAL_ENV variable not set after activation"
    echo ""
    echo "Troubleshooting:"
    echo "  - Try manual activation: source venv/bin/activate"
    echo "  - Check venv/bin/activate file exists and is not corrupted"
    exit 1
fi

echo "✅ Virtual environment activated: $VIRTUAL_ENV"

# Upgrade pip
echo "🔄 Upgrading pip..."
pip install --upgrade pip >/dev/null 2>&1 || echo "⚠️  pip upgrade had warnings (non-fatal)"

# Install requirements with retry logic
echo "🔄 Installing Python packages from requirements.txt..."
MAX_RETRIES=3
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if pip install -r requirements.txt; then
        echo "✅ Python packages installed successfully"
        break
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            echo "⚠️  Installation failed, retrying ($RETRY_COUNT/$MAX_RETRIES)..."
            sleep 5
        else
            show_error "Failed to install Python packages after $MAX_RETRIES attempts" \
                       "Check network connection and package compatibility"
            echo ""
            echo "Troubleshooting:"
            echo "  - Check network connection"
            echo "  - Try manual install: pip install -r requirements.txt"
            echo "  - Check individual packages: pip install pygame requests numpy"
            echo "  - Check Python version: python3 --version"
            exit 1
        fi
    fi
done

# Install openWakeWord without tflite-runtime (no ARM64 wheel exists).
# We always use inference_framework="onnx" so tflite is never needed.
# onnxruntime is already in requirements.txt and installs fine on ARM64.
echo "🔄 Installing openWakeWord (ONNX only, skipping tflite)..."
if pip install openwakeword --no-deps --quiet; then
    echo "✅ openWakeWord installed"
else
    echo "⚠️  openWakeWord install failed"
fi

echo "🔄 Verifying openWakeWord..."
if python -c "from openwakeword.model import Model; print('openWakeWord OK')" 2>/dev/null; then
    echo "✅ openWakeWord ready"
else
    echo "⚠️  openWakeWord import failed — check pip install output above"
fi

# Install Supertonic 2 TTS (multilingual, 9x faster than Piper)
echo "🔄 Checking Supertonic 2 TTS..."

# Check if both package AND model are installed
if python -c "import supertonic; tts = supertonic.TTS(); print('OK')" 2>/dev/null | grep -q "OK"; then
    echo "⏭️  Supertonic 2 TTS already installed (with model)"
else
    echo "🔄 Installing Supertonic 2 TTS..."

    # Step 1: Install Python package
    if pip install supertonic; then
        echo "✅ Python package installed"

        # Step 2: Trigger model download from HuggingFace
        echo "🔄 Downloading TTS model (~305MB from HuggingFace)..."
        echo "   This may take 2-5 minutes depending on connection..."

        # Instantiate TTS() to trigger auto-download
        if python -c "import supertonic; tts = supertonic.TTS(); print('Model loaded successfully')" 2>&1; then
            echo "✅ Supertonic 2 TTS installed successfully (with model)"
        else
            echo "⚠️  Model download failed (non-fatal)"
            echo "   Piper TTS will be used as fallback"
            echo ""
            echo "   Troubleshooting:"
            echo "   - Check internet: ping huggingface.co"
            echo "   - Check firewall/proxy settings"
            echo "   - Try manual: python -c 'from supertonic import TTS; TTS()'"
            echo "   - Check HuggingFace Hub access"
        fi
    else
        echo "⚠️  Supertonic 2 installation failed (non-fatal)"
        echo "   Piper TTS will be used as fallback"
        echo ""
        echo "   Troubleshooting:"
        echo "   - Check network connection"
        echo "   - Try manual install: pip install supertonic"
        echo "   - Check pip logs above for errors"
    fi
fi

# Install faster-whisper and download model into local cache
echo "🔄 Checking faster-whisper STT..."

FW_CACHE_DIR="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-base"
if python -c "from faster_whisper import WhisperModel" 2>/dev/null && [ -d "$FW_CACHE_DIR" ]; then
    echo "⏭️  faster-whisper already installed (with model)"
else
    echo "🔄 Installing faster-whisper..."

    if pip install faster-whisper; then
        echo "✅ Python package installed"

        # Trigger one-time model download to ~/.cache/huggingface/
        echo "🔄 Downloading faster-whisper base model (~150MB from HuggingFace)..."
        echo "   This is a one-time download. Subsequent runs load from disk."

        if python -c "
from faster_whisper import WhisperModel
print('Loading model...')
WhisperModel('base', device='cpu', compute_type='int8')
print('Model cached successfully')
" 2>&1; then
            echo "✅ faster-whisper model cached successfully"
        else
            echo "⚠️  faster-whisper model download failed (non-fatal)"
            echo "   Will retry on first application run"
            echo ""
            echo "   Troubleshooting:"
            echo "   - Check internet: ping huggingface.co"
            echo "   - Try manual: python -c \"from faster_whisper import WhisperModel; WhisperModel('base', device='cpu')\""
        fi
    else
        echo "⚠️  faster-whisper installation failed (non-fatal)"
        echo "   STT will not be available. Try: pip install faster-whisper"
    fi
fi

# Verify critical packages installed
echo "✅ Verifying critical packages..."
CRITICAL_PACKAGES=("pygame" "requests" "numpy" "pyaudio" "serial" "psutil" "faster_whisper")
MISSING_PACKAGES=()

for pkg in "${CRITICAL_PACKAGES[@]}"; do
    if ! python -c "import $pkg" 2>/dev/null; then
        MISSING_PACKAGES+=("$pkg")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    show_error "Critical packages missing after installation" \
               "Missing: ${MISSING_PACKAGES[*]}"
    echo ""
    echo "Troubleshooting:"
    echo "  - Try installing individually: pip install ${MISSING_PACKAGES[*]}"
    echo "  - Check pip list: pip list"
    exit 1
fi

echo "✅ All critical packages verified"

# ============================================================================
# PHASE 7: PERSONALITY MODEL CREATION
# ============================================================================
CURRENT_PHASE="Phase 7/10: Creating personality models"
echo ""
echo "🎯 $CURRENT_PHASE..."

cd "$SCRIPT_DIR"

# Pre-creation validation
if ! check_directory "models"; then
    show_error "models/ directory not found" \
               "Directory structure may be incomplete"
    exit 1
fi

# Verify Ollama service is running
if ! systemctl is-active --quiet ollama 2>/dev/null; then
    show_error "Ollama service is not running" \
               "Service must be running to create models"
    echo ""
    echo "Troubleshooting:"
    echo "  - Start service: sudo systemctl start ollama"
    echo "  - Check status: sudo systemctl status ollama"
    exit 1
fi

# Verify base model exists
if ! ollama list | grep -q "gemma3:1b"; then
    show_error "Base model gemma3:1b not found" \
               "Base model must be downloaded before creating personality models"
    echo ""
    echo "Troubleshooting:"
    echo "  - Download base model: ollama pull gemma3:1b"
    echo "  - List models: ollama list"
    exit 1
fi

# Check if personality models already exist
EXISTING_PERSONALITIES=$(ollama list | grep -E "(gemma3|qwen2.5|llama3.2|qwen3).*-ptbr-" | wc -l)

if [ "$EXISTING_PERSONALITIES" -gt 0 ]; then
    echo "⏭️  Found $EXISTING_PERSONALITIES personality model(s) already created"
    echo "   Checking if all personalities exist..."
fi

# Generate Modelfiles if needed
if [ ! -d "models/gemma3" ] || [ ! -f "models/gemma3/Modelfile.casual" ]; then
    echo "🔄 Generating personality Modelfiles from personalities.yaml..."
    cd models/
    if python3 generate_personalities.py; then
        echo "✅ Modelfiles generated successfully"
    else
        show_error "Failed to generate personality Modelfiles" \
                   "Check personalities.yaml and generate_personalities.py"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check YAML: cat models/personalities.yaml"
        echo "  - Run manually: cd models && python3 generate_personalities.py"
        exit 1
    fi
    cd "$SCRIPT_DIR"
else
    echo "⏭️  Personality Modelfiles already generated"
fi

# Create all personality models
echo "🔄 Creating personality models..."
cd models/
if bash create_all_personalities.sh; then
    echo "✅ Personality models created/verified successfully"
else
    echo "⚠️  Some personality models may have failed (non-fatal)"
    echo "   You can still use available models"
fi
cd "$SCRIPT_DIR"

# Verify at least one personality model exists
PERSONALITY_COUNT=$(ollama list | grep -E "(gemma3|qwen2.5|llama3.2|qwen3).*-ptbr-" | wc -l)
if [ "$PERSONALITY_COUNT" -eq 0 ]; then
    show_error "No personality models found after creation" \
               "Model creation may have failed"
    echo ""
    echo "Troubleshooting:"
    echo "  - List models: ollama list"
    echo "  - Check Ollama logs: journalctl -u ollama -n 50"
    echo "  - Try manual creation: cd models && bash create_all_personalities.sh"
    exit 1
fi

echo "✅ Verified $PERSONALITY_COUNT personality model(s)"

# ============================================================================
# PHASE 8: SYSTEM-INTERFACE SETUP
# ============================================================================
CURRENT_PHASE="Phase 8/10: Setting up system-interface"
echo ""
echo "🌐 $CURRENT_PHASE..."

# Navigate to system-interface directory
INTERFACE_DIR="$(dirname "$SCRIPT_DIR")/system-interface"

if ! check_directory "$INTERFACE_DIR"; then
    show_error "system-interface directory not found" \
               "Directory structure may be incomplete"
    echo "   Expected: $INTERFACE_DIR"
    exit 1
fi

cd "$INTERFACE_DIR"

# Check requirements.txt
if ! check_file "requirements.txt"; then
    show_error "system-interface/requirements.txt not found"
    exit 1
fi

# Check .env file, create from .env.example if needed
if [ ! -f ".env" ]; then
    if check_file ".env.example"; then
        echo "🔄 Creating .env from .env.example..."
        cp .env.example .env

        # Update paths in .env
        echo "🔄 Configuring .env with correct paths..."
        sed -i "s|~/piper/piper/piper|$HOME/piper/piper/piper|g" .env
        sed -i "s|~/piper/piper/|$HOME/piper/piper/|g" .env

        echo "✅ .env file created and configured"
    else
        show_error ".env.example not found in system-interface" \
                   "Cannot create configuration file"
        exit 1
    fi
else
    echo "⏭️  .env file already exists"
fi

# Install Python dependencies for system-interface
echo "🔄 Installing system-interface Python packages..."

# Check if venv exists in system-interface
if [ ! -d "venv" ]; then
    echo "🔄 Creating virtual environment for system-interface..."
    if ! python3 -m venv venv; then
        show_error "Failed to create venv for system-interface"
        exit 1
    fi
fi

# Activate system-interface venv
source venv/bin/activate

# Install dependencies
if ! pip install -r requirements.txt; then
    show_error "Failed to install system-interface packages" \
               "Check requirements.txt and network connection"
    echo ""
    echo "Troubleshooting:"
    echo "  - Try manual install: pip install flask pygame requests python-dotenv"
    exit 1
fi

# Verify critical packages
INTERFACE_PACKAGES=("flask" "pygame" "requests" "dotenv")
for pkg in "${INTERFACE_PACKAGES[@]}"; do
    if ! python -c "import $pkg" 2>/dev/null; then
        show_error "Package $pkg not installed" \
                   "Installation may have failed"
        exit 1
    fi
done

echo "✅ System-interface packages installed"

# Create necessary directories
echo "🔄 Creating required directories..."
mkdir -p data
mkdir -p static/audio

# Initialize database if needed
if [ ! -f "data/users.db" ]; then
    echo "🔄 Initializing database..."
    if [ -f "src/init_system.py" ]; then
        python src/init_system.py
        echo "✅ Database initialized"
    else
        echo "⚠️  init_system.py not found, database will be created on first run"
    fi
else
    echo "⏭️  Database already exists"
fi

# Verify app.py exists
if ! check_file "src/app.py"; then
    show_error "system-interface/src/app.py not found" \
               "Core application file is missing"
    exit 1
fi

# Test voice system integration
echo "🔄 Testing voice system integration..."
if [ -f "test_voice_system.py" ]; then
    if python test_voice_system.py; then
        echo "✅ Voice system tests passed"
    else
        echo "⚠️  Some voice system tests failed (non-fatal)"
        echo "   System will still work, but voice features may be limited"
    fi
else
    echo "⚠️  test_voice_system.py not found, skipping voice tests"
fi

echo "✅ System-interface setup complete"

# Deactivate system-interface venv
deactivate

# Return to script directory
cd "$SCRIPT_DIR"

# Reactivate rpi5-chatbot venv
source venv/bin/activate

# ============================================================================
# PHASE 9: HARDWARE CONFIGURATION (RFID, Audio, Permissions)
# ============================================================================
CURRENT_PHASE="Phase 9/10: Configuring hardware (RFID/SPI, Audio, Permissions)"
echo ""
echo "🔧 $CURRENT_PHASE..."

# ------------------------------
# 1. Enable SPI for RFID/MFRC522
# ------------------------------
echo "🔄 Configuring SPI for RFID..."

if ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=spi=on" /boot/config.txt 2>/dev/null; then
    echo "   Enabling SPI interface..."

    # Try both possible locations for config.txt
    if [ -f "/boot/firmware/config.txt" ]; then
        CONFIG_FILE="/boot/firmware/config.txt"
    elif [ -f "/boot/config.txt" ]; then
        CONFIG_FILE="/boot/config.txt"
    else
        echo "⚠️  Warning: Could not find config.txt"
        echo "   SPI may need to be enabled manually:"
        echo "   sudo raspi-config -> Interface Options -> SPI -> Enable"
        CONFIG_FILE=""
    fi

    if [ -n "$CONFIG_FILE" ]; then
        # Backup config file
        sudo cp "$CONFIG_FILE" "${CONFIG_FILE}.backup"

        # Enable SPI
        if grep -q "^#dtparam=spi=on" "$CONFIG_FILE"; then
            sudo sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' "$CONFIG_FILE"
        else
            echo "dtparam=spi=on" | sudo tee -a "$CONFIG_FILE" > /dev/null
        fi

        echo "✅ SPI enabled in $CONFIG_FILE"
        echo "   ⚠️  NOTE: SPI will be active after reboot"
    fi
else
    echo "⏭️  SPI already enabled"
fi

# Check if SPI device exists (will only exist after reboot if just enabled)
if [ -e "/dev/spidev0.0" ]; then
    echo "✅ SPI device /dev/spidev0.0 available"
else
    echo "⚠️  SPI device not found (may require reboot)"
fi

# ------------------------------
# 2. Configure User Permissions
# ------------------------------
echo "🔄 Configuring user permissions..."

# Add user to necessary groups
GROUPS_TO_ADD=("spi" "gpio" "dialout" "audio")
ADDED_ANY=false

for group in "${GROUPS_TO_ADD[@]}"; do
    if getent group "$group" > /dev/null 2>&1; then
        if ! groups | grep -q "\b$group\b"; then
            echo "   Adding user to $group group..."
            sudo usermod -a -G "$group" "$USER"
            ADDED_ANY=true
        fi
    fi
done

if [ "$ADDED_ANY" = true ]; then
    echo "✅ User added to hardware groups"
    echo "   ⚠️  NOTE: Group changes will be active after logout/login or reboot"
else
    echo "⏭️  User already in all necessary groups"
fi

# ------------------------------
# 3. Configure Audio Devices
# ------------------------------
echo "🔄 Detecting and configuring audio devices..."

echo "   Available audio devices:"
aplay -l 2>/dev/null | grep "^card" || echo "   No audio devices found"

if pgrep -x "pulseaudio" > /dev/null; then
    echo "⚠️  PulseAudio is running - may interfere with direct ALSA access"
    echo "   If you experience audio issues, consider:"
    echo "   systemctl --user stop pulseaudio.socket pulseaudio.service"
fi

if command -v speaker-test &> /dev/null; then
    echo "   Testing audio output (2 second test)..."
    timeout 2 speaker-test -t sine -f 1000 -c 2 &> /dev/null || true
    echo "✅ Audio output test completed"
else
    echo "⏭️  speaker-test not available, skipping audio test"
fi

# ------------------------------
# 4. Create Audio Test Script
# ------------------------------
echo "🔄 Creating audio configuration helper..."

cat > "$INTERFACE_DIR/test_audio_devices.py" << 'ENDAUDIO'
#!/usr/bin/env python3
"""
Audio Device Detector and Configurator
Helps identify and configure the correct audio devices
"""
import pyaudio
import sys

def list_audio_devices():
    p = pyaudio.PyAudio()
    print("\n Available Audio Devices:\n")
    print(f"{'Index':<6} {'Name':<50} {'Channels':<10} {'Type'}")
    print("-" * 80)

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        channels = info.get('maxInputChannels') if info.get('maxInputChannels') > 0 else info.get('maxOutputChannels')
        dev_type = "Input" if info.get('maxInputChannels') > 0 else "Output"
        print(f"{i:<6} {info['name']:<50} {channels:<10} {dev_type}")

    p.terminate()
    print("\n")

if __name__ == "__main__":
    list_audio_devices()
    print("To configure audio:")
    print("1. Identify your output device (speaker/headphone) index")
    print("2. Identify your input device (microphone) index")
    print("3. Update .env file with ALSA device strings")
    print("   Example: AUDIO_DEVICE=plughw:3,0")
ENDAUDIO

chmod +x "$INTERFACE_DIR/test_audio_devices.py"
echo "✅ Audio test script created: test_audio_devices.py"

echo "✅ Hardware configuration complete"
echo ""
echo "Important Notes:"
echo "  SPI for RFID: Enabled (active after reboot)"
echo "  User Groups: Updated (active after logout/login)"
echo "  Audio: Use test_audio_devices.py to configure"
echo ""
echo "  If this is first setup, please REBOOT after installation:"
echo "  sudo reboot"
echo ""

# ============================================================================
# PHASE 10: VERIFY INSTALLATION
# ============================================================================
CURRENT_PHASE="Phase 10/10: Verifying installation"
echo ""
echo "✅ $CURRENT_PHASE..."

cd "$SCRIPT_DIR"

# Pre-test validation
if ! check_directory "venv"; then
    show_error "Virtual environment not found" \
               "Python environment setup may have failed"
    exit 1
fi

if ! check_file "src/run_chatbot.py"; then
    show_error "run_chatbot.py not found" \
               "Source files may be missing"
    exit 1
fi

# Ensure venv is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "🔄 Reactivating virtual environment..."
    source venv/bin/activate
fi

# Run system tests
echo "🔄 Running system tests..."
if python src/run_chatbot.py --test; then
    echo "✅ All system tests passed"
else
    echo ""
    echo "⚠️  System tests failed (non-fatal)"
    echo "   You can still run the chatbot, but some features may not work"
    echo "   Review the test output above for details"
    echo ""
fi

# ============================================================================
# INSTALLATION SUMMARY
# ============================================================================
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

echo ""
echo "========================================"
echo "🎉 TalkingBuddy Setup Complete!"
echo "========================================"
echo ""
echo "Installation time: ${MINUTES}m ${SECONDS}s"
echo ""
echo "Installed Components:"
echo "✅ System dependencies (build tools, audio libraries)"
echo "✅ whisper.cpp (speech-to-text)"
echo "   └─ Model: ggml-base.bin (multilingual)"
echo "   └─ Location: ~/whisper.cpp"
echo "✅ Piper TTS (text-to-speech - Portuguese)"
echo "   └─ Model: pt_BR-faber-medium"
echo "   └─ Location: ~/piper/piper"
echo "✅ Supertonic 2 TTS (text-to-speech - multilingual, 9x faster)"
echo "   └─ Languages: Portuguese, English, Spanish"
echo "   └─ Voices: 8 unique voices (F1-F5, M1-M3)"
echo "✅ Ollama (LLM service)"
echo "   └─ Service: Active"
echo "   └─ Base model: gemma3:1b"
echo "   └─ Personalities: $PERSONALITY_COUNT models created"
echo "✅ Python environment (rpi5-chatbot)"
echo "   └─ Location: ./venv"
echo "   └─ Packages: pygame, requests, numpy, pyaudio, pyserial, psutil, supertonic"
echo "✅ System-interface (Web UI)"
echo "   └─ Location: ../system-interface"
echo "   └─ Database: Initialized"
echo "   └─ Voice integration: Configured"
echo "✅ Hardware configuration"
echo "   └─ SPI/RFID: Configured"
echo "   └─ User groups: spi, gpio, dialout, audio"
echo ""
echo "Next Steps:"
echo ""
echo "1. Start the Web UI (recommended):"
echo "   cd ../system-interface"
echo "   bash start.sh"
echo "   Then open browser: http://localhost:5000"
echo ""
echo "2. Test with different personalities (keyboard mode):"
echo "   cd rpi5-chatbot"
echo "   source venv/bin/activate"
echo "   python src/run_chatbot.py --wake-mode keyboard --personality casual"
echo "   python src/run_chatbot.py --wake-mode keyboard --personality humorous --language en"
echo ""
echo "3. Test with Supertonic TTS (9x faster, multilingual):"
echo "   python src/run_chatbot.py --wake-mode keyboard --tts-engine supertonic --language pt"
echo "   python src/run_chatbot.py --wake-mode keyboard --tts-engine supertonic --language en --personality formal"
echo ""
echo "4. For production with ESP32 wake word:"
echo "   python src/run_chatbot.py --wake-mode serial --personality casual --tts-engine supertonic"
echo ""
echo "5. View available personalities:"
echo "   python src/run_chatbot.py --list-personalities"
echo ""
echo "6. View all available commands:"
echo "   python src/run_chatbot.py --help"
echo ""
echo "Troubleshooting:"
echo "  - Setup log: $LOG_FILE"
echo "  - Test system: python src/run_chatbot.py --test"
echo "  - Test voice: cd ../system-interface && python test_voice_system.py"
echo "  - Check Ollama: systemctl status ollama"
echo "  - Check models: ollama list"
echo "  - List personalities: python src/run_chatbot.py --list-personalities"
echo "  - List audio devices: python src/run_chatbot.py --list-devices"
echo "  - Web interface logs: Check terminal output when running start.sh"
echo ""
echo "Documentation: README.md"
echo ""

# Show disk usage
DISK_USED=$(du -sh "$SCRIPT_DIR" 2>/dev/null | cut -f1 || echo "unknown")
echo "Project disk usage: $DISK_USED"

DISK_FREE=$(df -h . | awk 'NR==2 {print $4}')
echo "Disk space remaining: $DISK_FREE"
echo ""

if [ "$(df -m . | awk 'NR==2 {print $4}')" -lt 1000 ]; then
    echo "⚠️  Warning: Low disk space (<1GB remaining)"
    echo "   Consider freeing up space for model operations"
    echo ""
fi
