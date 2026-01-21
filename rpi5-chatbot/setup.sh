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
TOTAL_PHASES=8

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
CURRENT_PHASE="Phase 1/8: Installing system dependencies"
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
if ! sudo apt install -y build-essential cmake git wget curl portaudio19-dev libsdl2-dev libasound2-dev; then
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
CURRENT_PHASE="Phase 2/8: Installing whisper.cpp"
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
CURRENT_PHASE="Phase 3/8: Installing Piper TTS"
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
CURRENT_PHASE="Phase 4/8: Installing Ollama"
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
CURRENT_PHASE="Phase 5/8: Downloading Ollama models"
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

# ============================================================================
# PHASE 6: PYTHON ENVIRONMENT SETUP
# ============================================================================
CURRENT_PHASE="Phase 6/8: Setting up Python environment"
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

# Verify critical packages installed
echo "✅ Verifying critical packages..."
CRITICAL_PACKAGES=("pygame" "requests" "numpy" "pyaudio" "serial" "psutil")
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
# PHASE 7: CUSTOM MODEL CREATION
# ============================================================================
CURRENT_PHASE="Phase 7/8: Creating custom Portuguese model"
echo ""
echo "🎯 $CURRENT_PHASE..."

cd "$SCRIPT_DIR"

# Pre-creation validation
if ! check_directory "models"; then
    show_error "models/ directory not found" \
               "Directory structure may be incomplete"
    exit 1
fi

if ! check_file "models/Modelfile.gemma3-ptbr"; then
    show_error "Modelfile.gemma3-ptbr not found" \
               "Model configuration file is missing"
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
               "Base model must be downloaded before creating custom model"
    echo ""
    echo "Troubleshooting:"
    echo "  - Download base model: ollama pull gemma3:1b"
    echo "  - List models: ollama list"
    exit 1
fi

# Check if custom model already exists (non-interactive check)
if ollama list | grep -q "gemma3-ptbr"; then
    echo "⏭️  Model gemma3-ptbr already exists, skipping creation"
else
    echo "🔄 Creating custom model gemma3-ptbr..."
    echo "   This will take 1-2 minutes..."

    # Create model directly (non-interactive)
    cd models/
    if ! ollama create gemma3-ptbr -f Modelfile.gemma3-ptbr; then
        show_error "Failed to create gemma3-ptbr model" \
                   "Model creation command failed"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check Modelfile: cat models/Modelfile.gemma3-ptbr"
        echo "  - Check Ollama logs: journalctl -u ollama -n 50"
        echo "  - Try manual creation: cd models && ollama create gemma3-ptbr -f Modelfile.gemma3-ptbr"
        exit 1
    fi

    cd "$SCRIPT_DIR"
    echo "✅ Custom model created successfully"
fi

# Verify model creation
if ! ollama list | grep -q "gemma3-ptbr"; then
    show_error "gemma3-ptbr model not found after creation" \
               "Model creation may have failed silently"
    echo ""
    echo "Troubleshooting:"
    echo "  - List models: ollama list"
    echo "  - Check Ollama logs: journalctl -u ollama -n 50"
    exit 1
fi

echo "✅ Model gemma3-ptbr verified"

# ============================================================================
# PHASE 8: VERIFY INSTALLATION
# ============================================================================
CURRENT_PHASE="Phase 8/8: Verifying installation"
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
echo "   └─ Model: ggml-base.bin"
echo "   └─ Location: ~/whisper.cpp"
echo "✅ Piper TTS (text-to-speech)"
echo "   └─ Model: pt_BR-faber-medium"
echo "   └─ Location: ~/piper/piper"
echo "✅ Ollama (LLM service)"
echo "   └─ Service: Active"
echo "   └─ Models: gemma3:1b, gemma3-ptbr"
echo "✅ Python environment"
echo "   └─ Location: ./venv"
echo "   └─ Packages: pygame, requests, numpy, pyaudio, pyserial, psutil"
echo ""
echo "Next Steps:"
echo "1. Start the chatbot:"
echo "   cd rpi5-chatbot"
echo "   source venv/bin/activate"
echo "   python src/run_chatbot.py --wake-mode keyboard --model gemma3-ptbr"
echo ""
echo "2. For production with ESP32 wake word:"
echo "   python src/run_chatbot.py --wake-mode serial --model gemma3-ptbr"
echo ""
echo "3. View available commands:"
echo "   python src/run_chatbot.py --help"
echo ""
echo "Troubleshooting:"
echo "  - Setup log: $LOG_FILE"
echo "  - Test system: python src/run_chatbot.py --test"
echo "  - Check Ollama: systemctl status ollama"
echo "  - Check models: ollama list"
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
