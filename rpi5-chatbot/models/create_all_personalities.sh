#!/bin/bash
# Create all personality variants for TalkingBuddy models

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🎭 TalkingBuddy Personality Model Creator"
echo "=========================================="
echo ""

# Check if ollama is running
if ! systemctl is-active --quiet ollama 2>/dev/null; then
    echo "⚠️  Ollama service is not running"
    echo "   Attempting to start..."
    sudo systemctl start ollama || {
        echo "❌ Failed to start Ollama service"
        exit 1
    }
    sleep 2
fi

# Base models that must exist
BASE_MODELS=("gemma3:1b" "qwen2.5:1.5b" "llama3.2:1b" "qwen3.5:0.8b")

# Check which base models are available
echo "📦 Checking base models..."
AVAILABLE_MODELS=()
for model in "${BASE_MODELS[@]}"; do
    if ollama list | grep -q "$model"; then
        echo "   ✅ $model found"
        AVAILABLE_MODELS+=("$model")
    else
        echo "   ⚠️  $model not found (skipping personalities for this model)"
    fi
done

if [ ${#AVAILABLE_MODELS[@]} -eq 0 ]; then
    echo ""
    echo "❌ No base models found!"
    echo "   Please install at least one:"
    echo "   - ollama pull gemma3:1b"
    echo "   - ollama pull qwen2.5:1.5b"
    echo "   - ollama pull llama3.2:1b"
    exit 1
fi

# Map base model names to directory names
declare -A MODEL_TO_DIR=(
    ["gemma3:1b"]="gemma3"
    ["qwen2.5:1.5b"]="qwen2.5"
    ["llama3.2:1b"]="llama3.2"
    ["qwen3.5:0.8b"]="qwen3.5"
)

# Build list of directories to process
DIRS_TO_PROCESS=()
for model in "${AVAILABLE_MODELS[@]}"; do
    dir="${MODEL_TO_DIR[$model]}"
    if [ -n "$dir" ]; then
        DIRS_TO_PROCESS+=("$dir")
    fi
done

echo ""
echo "📂 Will process directories: ${DIRS_TO_PROCESS[*]}"

echo ""
echo "🔨 Generating Modelfiles from personalities.yaml..."
python3 generate_personalities.py || {
    echo "❌ Failed to generate Modelfiles"
    exit 1
}

echo ""
echo "📝 Creating personality models in Ollama..."
echo "   ⏱️  Each model takes ~5-10 seconds to create"
echo ""

# Function to create a model
create_model() {
    local modelfile="$1"
    local base_model="$2"
    local personality="$3"
    local model_name="${base_model}-ptbr-${personality}"

    # Check if model already exists
    if ollama list | grep -q "^${model_name}"; then
        echo "   ⏭️  $model_name already exists (skipping)"
        return 0
    fi

    echo "   🔧 Creating $model_name..."
    # Create model and capture output
    if output=$(ollama create "$model_name" -f "$modelfile" 2>&1); then
        echo "   ✅ $model_name created successfully"
        return 0
    else
        echo "   ❌ Failed to create $model_name"
        echo "      Error: $output"
        return 1
    fi
}

# Create all personality models
CREATED=0
SKIPPED=0
FAILED=0

# Temporarily disable exit on error for the creation loop
# (we want to continue even if one model fails)
set +e

# Iterate through base model directories (only those with installed models)
for base_dir in "${DIRS_TO_PROCESS[@]}"; do
    if [ ! -d "$base_dir" ]; then
        echo "   ⚠️  Directory $base_dir not found (skipping)"
        continue
    fi

    # Count modelfiles for progress indication
    modelfile_count=$(find "$base_dir" -name "Modelfile.*" -type f | wc -l)
    current=0

    echo ""
    echo "📦 Processing $base_dir models ($modelfile_count personalities)..."

    # Debug: Check if files exist
    if [ "$modelfile_count" -eq 0 ]; then
        echo "   ⚠️  No Modelfiles found in $base_dir/"
        continue
    fi

    for modelfile in "$base_dir"/Modelfile.*; do
        if [ -f "$modelfile" ]; then
            current=$((current + 1))
            # Extract personality from filename (e.g., Modelfile.casual -> casual)
            personality=$(basename "$modelfile" | sed 's/^Modelfile\.//')

            echo "   [$current/$modelfile_count] Processing: $personality"

            if create_model "$modelfile" "$base_dir" "$personality"; then
                if ollama list | grep -q "${base_dir}-ptbr-${personality}"; then
                    CREATED=$((CREATED + 1))
                else
                    SKIPPED=$((SKIPPED + 1))
                fi
            else
                FAILED=$((FAILED + 1))
            fi
        fi
    done
done

# Re-enable exit on error
set -e

echo ""
echo "=========================================="
echo "✨ Personality Model Creation Complete!"
echo "=========================================="
echo "   Created: $CREATED models"
echo "   Skipped: $SKIPPED models (already existed)"
echo "   Failed:  $FAILED models"
echo ""

if [ $CREATED -gt 0 ] || [ $SKIPPED -gt 0 ]; then
    echo "📊 Available personality models:"
    ollama list | grep -E "(gemma3|qwen2\.5|llama3\.2|qwen3\.5).*-ptbr-" || echo "   (none yet)"
    echo ""
    echo "🎯 Usage examples:"
    echo "   python src/run_chatbot.py --personality casual"
    echo "   python src/run_chatbot.py --personality humorous --model gemma3"
    echo "   python src/run_chatbot.py --personality detailed --model qwen2.5"
fi
