# Modelfile Guide for Voice Chatbot

This guide explains the custom Modelfiles for forcing Brazilian Portuguese responses in the voice chatbot.

## Overview

We've created custom Modelfiles for each recommended LLM model to ensure consistent Brazilian Portuguese responses. These Modelfiles add a system instruction that forces Portuguese output regardless of the input language.

## Available Models

### Native Portuguese Models (No Forcing Needed)
These models have excellent native Brazilian Portuguese support and don't require Modelfiles:

- `qwen2.5:1.5b` - **Recommended** (4.50/5 quality, 3.42s avg response)
- `gemma3:1b` - **Fastest** (4.25/5 quality, 2.05s avg response)
- `gemma3:1b-it-qat` - **Instruction-Tuned** (4.25/5 quality, 2.91s avg response)
- `llama3.2:1b` - **Best Quality** (4.00/5 quality, 3.49s avg response)

### Portuguese-Forced Models (Using Modelfiles)
These are custom models created from Modelfiles that explicitly force Portuguese responses:

- `qwen2.5-ptbr` - Qwen2.5 with forced Portuguese
- `gemma3-ptbr` - Gemma3 with forced Portuguese
- `gemma3-it-qat-ptbr` - Gemma3 instruction-tuned with forced Portuguese
- `llama3.2-ptbr` - Llama3.2 with forced Portuguese
- `mistral-ptbr` - Mistral 7B with forced Portuguese (desktop only)

## Building Custom Modelfiles

### Already Built Models
All 5 custom `-ptbr` models have already been built and are ready to use. You can skip directly to the "Using the Models" section.

### Rebuilding a Model (If Needed)
If you ever need to rebuild one of the custom models:

```bash
cd ~/fucking_with_AI/chatbot/

# Rebuild a specific model
ollama create qwen2.5-ptbr -f Modelfile.qwen2.5-ptbr
ollama create gemma3-ptbr -f Modelfile.gemma3-ptbr
ollama create gemma3-it-qat-ptbr -f Modelfile.gemma3-it-qat-ptbr
ollama create llama3.2-ptbr -f Modelfile.llama3.2-ptbr
ollama create mistral-ptbr -f Modelfile.mistral-ptbr
```

### Verify Installation
To verify which models are available:

```bash
ollama list
```

You should see both native and `-ptbr` variants listed.

## Using the Models

### Default Behavior
The chatbot uses the native Qwen2.5 model by default with native Portuguese support:

```bash
python run_chatbot.py
```

### Switching Models

#### Use Native Model (Native Portuguese Support)
```bash
# Use Gemma3 (fastest)
python run_chatbot.py --model "gemma3:1b"

# Use Llama3.2 (best quality)
python run_chatbot.py --model "llama3.2:1b"

# Use Gemma3 instruction-tuned
python run_chatbot.py --model "gemma3:1b-it-qat"
```

#### Use Forced Portuguese Variant (Modelfile)
```bash
# Use Qwen2.5 with forced Portuguese
python run_chatbot.py --model "qwen2.5:1.5b" --language pt-br

# Use Gemma3 with forced Portuguese
python run_chatbot.py --model "gemma3:1b" --language pt-br

# Use Llama3.2 with forced Portuguese
python run_chatbot.py --model "llama3.2:1b" --language pt-br
```

## When to Use Each Mode

### Native Portuguese Mode (Recommended)
**Use when:**
- You want the model to choose Portuguese naturally based on the input
- You want maximum flexibility in language mixing
- Slightly faster response times (no system instruction overhead)

**Example:**
```bash
python run_chatbot.py --model "qwen2.5:1.5b" --language native
```

### Forced Portuguese Mode (Modelfile)
**Use when:**
- You need guaranteed Portuguese responses
- You're testing non-Portuguese input to ensure PT-BR output
- You want explicit control over response language

**Example:**
```bash
python run_chatbot.py --model "qwen2.5:1.5b" --language pt-br
```

## Modelfile System Instructions

All `-ptbr` Modelfiles use this system instruction:

```
Você é um assistente útil e prestativo. Sempre responda em português brasileiro, independentemente do idioma da pergunta. Seja claro, conciso e natural em suas respostas.
```

Translation: "You are a helpful and supportive assistant. Always respond in Brazilian Portuguese, regardless of the input language. Be clear, concise, and natural in your responses."

## Technical Details

### How Modelfiles Work
1. Based on a native model (e.g., `qwen2.5:1.5b`)
2. Adds a system instruction forcing Portuguese
3. Sets optimized parameters (temperature 0.7, top_p 0.9)
4. Creates a new model variant (e.g., `qwen2.5-ptbr`)

### Why Safe to Use
- Using `/api/chat` endpoint (proper role separation)
- All models are instruction-tuned (understand role boundaries)
- Tested: No system prompt echoing occurs
- Native models also have excellent Portuguese support as fallback

## Quick Reference Table

| Model | Mode | Command | Speed | Quality | RAM |
|-------|------|---------|-------|---------|-----|
| Qwen2.5 | Native | `--model "qwen2.5:1.5b"` | Medium (3.4s) | ⭐⭐⭐⭐⭐ | 1.5-2.0 GB |
| Qwen2.5 | Forced | `--model "qwen2.5:1.5b" --language pt-br` | Medium (3.4s) | ⭐⭐⭐⭐⭐ | 1.5-2.0 GB |
| Gemma3 | Native | `--model "gemma3:1b"` | Fast (2.0s) | ⭐⭐⭐⭐ | 1.0 GB |
| Gemma3 | Forced | `--model "gemma3:1b" --language pt-br` | Fast (2.0s) | ⭐⭐⭐⭐ | 1.0 GB |
| Gemma3-IT | Native | `--model "gemma3:1b-it-qat"` | Med-Fast (2.9s) | ⭐⭐⭐⭐ | 1.0 GB |
| Gemma3-IT | Forced | `--model "gemma3:1b-it-qat" --language pt-br` | Med-Fast (2.9s) | ⭐⭐⭐⭐ | 1.0 GB |
| Llama3.2 | Native | `--model "llama3.2:1b"` | Medium (3.5s) | ⭐⭐⭐⭐ | 1.5 GB |
| Llama3.2 | Forced | `--model "llama3.2:1b" --language pt-br` | Medium (3.5s) | ⭐⭐⭐⭐ | 1.5 GB |

## Troubleshooting

### "Model not found" Error
If you get a model not found error, ensure Ollama has the base model:

```bash
# For example, if getting error for qwen2.5-ptbr:
ollama pull qwen2.5:1.5b

# Then rebuild the custom model
ollama create qwen2.5-ptbr -f Modelfile.qwen2.5-ptbr
```

### Empty Responses
If a model returns empty responses, check:
1. Ollama is running: `ollama serve` (in another terminal)
2. Model is available: `ollama list`
3. Check token limits in `config.py` (should be 250+)

### Slow Responses
If responses are slow on Raspberry Pi 5:
1. Reduce system load (close other applications)
2. Switch to faster model: `--model "gemma3:1b"`
3. Reduce `max_tokens` in `config.py` (trade quality for speed)
4. Check available RAM with `free -h`

## Model Comparison Reference

For detailed performance comparison, see:
- `MODEL_COMPARISON.md` - Detailed descriptions and sample responses
- `LLM_COMPARISON_RESULTS.md` - Benchmark results and testing methodology
- `QUICK_START.md` - Quick reference for common use cases

## See Also

- `config.py` - Full configuration options
- `run_chatbot.py` - Runner script and CLI options
- `ollama_llm.py` - LLM integration code
