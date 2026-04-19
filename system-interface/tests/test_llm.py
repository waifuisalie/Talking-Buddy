#!/usr/bin/env python3
"""
Teste de Caixa Branca 2: LLM — Gemma 3:1B via Ollama
Mede TTFT (Tempo para Primeiro Token), velocidade de geração (tokens/s)
e delta de memória RAM entre cold start e warm inference.

Uso (dentro de system-interface/, com venv ativo):
    python3 tests/test_llm.py
"""

import json
import os
import sys
import time

import requests

OLLAMA_BASE  = "http://localhost:11434"
OLLAMA_CHAT  = f"{OLLAMA_BASE}/api/chat"
OLLAMA_GEN   = f"{OLLAMA_BASE}/api/generate"
MODEL        = os.getenv("OLLAMA_MODEL", "gemma3:1b")
TIMEOUT      = 180
RESULTS_FILE = os.path.join(os.path.dirname(__file__), "results_llm.json")

# RAM target for delta between cold-loaded and warm states
RAM_DELTA_TARGET_MB = 150

TEST_PROMPT = "Explique em duas frases o que é inteligência artificial."
SYSTEM_PROMPT = "Você é um assistente objetivo. Responda sempre em português."


# ── Utilitários ───────────────────────────────────────────────────────────────

def read_mem_mb() -> float:
    """Lê memória RSS total de todos os processos Ollama em /proc."""
    total = 0
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            status_path = f"/proc/{pid}/status"
            try:
                with open(status_path) as f:
                    for line in f:
                        if line.startswith("Name:") and "ollama" not in line.lower():
                            break
                        if line.startswith("VmRSS:"):
                            total += int(line.split()[1])
                            break
            except (PermissionError, FileNotFoundError):
                continue
    except Exception:
        pass
    return total / 1024  # kB → MB


def get_system_mem_free_mb() -> float:
    """Retorna memória disponível do sistema via /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass
    return 0.0


def unload_model() -> bool:
    """Remove o modelo da RAM do Ollama (keep_alive=0)."""
    try:
        r = requests.post(
            OLLAMA_GEN,
            json={"model": MODEL, "keep_alive": 0},
            timeout=15
        )
        return r.status_code == 200
    except Exception as e:
        print(f"  ⚠️  Falha ao descarregar modelo: {e}")
        return False


def chat_blocking(prompt: str) -> dict:
    """
    Requisição blocking para /api/chat.
    Retorna dict com texto, tempo total, eval_count, eval_duration.
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 200},
    }
    t0 = time.perf_counter()
    r = requests.post(OLLAMA_CHAT, json=payload, timeout=TIMEOUT)
    elapsed = time.perf_counter() - t0
    data = r.json()
    text = data.get("message", {}).get("content", "").strip()
    eval_count = data.get("eval_count", 0)
    eval_duration_ns = data.get("eval_duration", 0)
    tokens_per_sec = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else 0
    return {
        "text": text,
        "total_time_s": round(elapsed, 3),
        "eval_count": eval_count,
        "tokens_per_sec": round(tokens_per_sec, 2),
    }


def chat_streaming_ttft(prompt: str) -> dict:
    """
    Requisição streaming para /api/chat.
    Mede TTFT e velocidade total de geração.
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "options": {"temperature": 0.5, "num_predict": 200},
    }
    t_start = time.perf_counter()
    ttft = None
    full_text = ""
    total_tokens = 0

    with requests.post(OLLAMA_CHAT, json=payload, timeout=TIMEOUT, stream=True) as resp:
        for line in resp.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            chunk = data.get("message", {}).get("content", "")
            if chunk and ttft is None:
                ttft = time.perf_counter() - t_start
            full_text += chunk
            if data.get("done"):
                total_tokens = data.get("eval_count", 0)
                eval_dur_ns  = data.get("eval_duration", 0)
                tokens_per_sec = (total_tokens / (eval_dur_ns / 1e9)) if eval_dur_ns else 0
                break

    total_time = time.perf_counter() - t_start
    return {
        "text": full_text.strip(),
        "ttft_s": round(ttft or 0, 3),
        "total_time_s": round(total_time, 3),
        "tokens_per_sec": round(tokens_per_sec, 2),
        "token_count": total_tokens,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"TESTE 2: LLM — Gemma via Ollama  (modelo: {MODEL})")
    print("=" * 60)

    # Verify Ollama is reachable
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"✅ Ollama acessível | modelos disponíveis: {', '.join(models) or 'nenhum'}")
    except Exception as e:
        print(f"❌ Ollama não acessível: {e}")
        sys.exit(1)

    results = {}

    # ── 1. Cold Start ──────────────────────────────────────────────────────────
    print("\n[1/3] Cold Start — descarregando modelo da RAM...")
    mem_before = get_system_mem_free_mb()
    unloaded = unload_model()
    time.sleep(2)  # aguardar descarga completa

    print(f"  💾 RAM livre antes do load: {mem_before:.0f} MB")
    print(f"  🔄 Enviando requisição (cold start)...")
    cold = chat_streaming_ttft(TEST_PROMPT)
    mem_after = get_system_mem_free_mb()
    ram_delta = mem_before - mem_after  # positivo = memória consumida pelo modelo

    print(f"  ✅ TTFT: {cold['ttft_s']}s")
    print(f"  ✅ Tempo total: {cold['total_time_s']}s")
    print(f"  ✅ Velocidade: {cold['tokens_per_sec']} tokens/s")
    print(f"  💾 RAM consumida pelo modelo: {ram_delta:.0f} MB  (alvo < {RAM_DELTA_TARGET_MB} MB)")
    if ram_delta <= RAM_DELTA_TARGET_MB:
        print(f"  ✅ Delta RAM dentro do alvo")
    else:
        print(f"  ⚠️  Delta RAM acima do alvo — considere ajustar o target no relatório")
    print(f"  📝 Resposta: \"{cold['text'][:120]}\"")

    results["cold_start"] = {
        "ttft_s": cold["ttft_s"],
        "total_time_s": cold["total_time_s"],
        "tokens_per_sec": cold["tokens_per_sec"],
        "token_count": cold["token_count"],
        "ram_delta_mb": round(ram_delta, 1),
        "ram_target_ok": ram_delta <= RAM_DELTA_TARGET_MB,
    }

    # ── 2. Warm Inference (3 repetições) ──────────────────────────────────────
    print("\n[2/3] Warm Inference — modelo já carregado na RAM (3 repetições)...")
    warm_runs = []
    for k in range(3):
        w = chat_streaming_ttft(TEST_PROMPT)
        warm_runs.append(w)
        print(f"  Run {k+1}: TTFT={w['ttft_s']}s | total={w['total_time_s']}s | {w['tokens_per_sec']} tok/s")

    avg_ttft = sum(r["ttft_s"] for r in warm_runs) / len(warm_runs)
    avg_tps  = sum(r["tokens_per_sec"] for r in warm_runs) / len(warm_runs)
    print(f"\n  📊 Médias warm — TTFT: {avg_ttft:.3f}s | velocidade: {avg_tps:.1f} tok/s")
    print(f"  📊 Melhoria TTFT vs cold start: {cold['ttft_s'] - avg_ttft:.3f}s mais rápido")

    results["warm_inference"] = {
        "runs": warm_runs,
        "avg_ttft_s": round(avg_ttft, 3),
        "avg_tokens_per_sec": round(avg_tps, 2),
    }

    # ── 3. Blocking mode (para referência) ────────────────────────────────────
    print("\n[3/3] Blocking mode — referência sem streaming...")
    block = chat_blocking(TEST_PROMPT)
    print(f"  ✅ Tempo total: {block['total_time_s']}s | {block['tokens_per_sec']} tok/s")
    results["blocking_reference"] = block

    # ── Resumo ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"  Cold Start TTFT:       {cold['ttft_s']}s")
    print(f"  Warm Inference TTFT:   {avg_ttft:.3f}s (média)")
    print(f"  Velocidade geração:    {avg_tps:.1f} tok/s (warm)")
    print(f"  Delta RAM (modelo):    {ram_delta:.0f} MB  {'✅' if ram_delta <= RAM_DELTA_TARGET_MB else '⚠️ acima do alvo inicial'}")

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResultados salvos em: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
