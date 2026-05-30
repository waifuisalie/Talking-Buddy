"""
Sweeps dispatcher classification across model + think-mode combos.

For each combo:
  1. Warmup call (model loads into RAM).
  2. Run 20 PT-BR test cases sequentially (model stays warm, timed).
  3. Send a final unload request with keep_alive="0" so Ollama frees RAM.
  4. Print accuracy + per-call median/p95 latency.

Run on the Pi:
    cd ~/Talking-Buddy/system-interface
    source venv/bin/activate
    python -m tests.benchmark_dispatcher
"""

import os
import sys
import time
import statistics
from pathlib import Path

# Make voice_assistant importable when run as `python -m tests.benchmark_dispatcher`
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voice_assistant import dispatcher  # noqa: E402

# Held-out test set. NOTE: a couple of items (e.g. "tomei meu remédio hoje?")
# are close in form to few-shot items but no test item is verbatim in the few-shot.
SAMPLES_PTBR = [
    ("o que o livro diz sobre regressão linear?", "RAG"),
    ("explica o capítulo 3 do meu material", "RAG"),
    ("resuma o conteúdo do livro", "RAG"),
    ("como funciona gradient descent segundo o livro?", "RAG"),
    ("o que o manual fala sobre normalização?", "RAG"),
    ("tomei losartana 50mg agora", "FACT_STORE"),
    ("acabei de almoçar", "FACT_STORE"),
    ("estou me sentindo cansado hoje", "FACT_STORE"),
    ("acordei às 7 da manhã", "FACT_STORE"),
    ("minha consulta é amanhã às 14h", "FACT_STORE"),
    ("tomei meu remédio hoje?", "FACT_RECALL"),
    ("que horas eu acordei ontem?", "FACT_RECALL"),
    ("quando foi minha última consulta?", "FACT_RECALL"),
    ("o que eu comi no almoço?", "FACT_RECALL"),
    ("já tomei a losartana hoje?", "FACT_RECALL"),
    ("oi, tudo bem?", "CHITCHAT"),
    ("me conta uma piada", "CHITCHAT"),
    ("qual é a capital da França?", "CHITCHAT"),
    ("bom dia!", "CHITCHAT"),
    ("você gosta de música?", "CHITCHAT"),
]

# (label, model, think, system_suffix) — system_suffix appended to dispatcher's
# system prompt. "/no_think" is the prompt-side switch for Qwen3 models;
# the API-level `think: false` is ignored by these models on this Pi.
COMBOS = [
    ("gemma3:1b",               "gemma3:1b",          None,  None),
    ("qwen3.5:0.8b /no_think",  "qwen3.5:0.8b",       None,  "/no_think"),
    ("qwen3.5:2b /no_think",    "qwen3.5:2b",         None,  "/no_think"),
]

# Generous per-call timeout — qwen3:2b with think can chew through a lot of tokens.
PER_CALL_TIMEOUT = float(os.getenv("BENCH_TIMEOUT", "120"))


def _unload(model: str) -> None:
    """Best-effort RAM free: send a tiny request with keep_alive=0."""
    try:
        dispatcher.classify(
            "x",
            language="pt-BR",
            model=model,
            keep_alive="0",
            timeout=30,
        )
        print(f"  [unload] {model} → keep_alive=0 sent")
    except Exception as e:
        print(f"  [unload] {model} non-fatal: {e}")


def _run_combo(label: str, model: str, think, system_suffix=None):
    print(f"\n=== {label}  (model={model}, think={think}, suffix={system_suffix!r}) ===")
    print("  warmup...", end=" ", flush=True)
    t0 = time.time()
    _ = dispatcher.classify("oi", language="pt-BR", model=model, think=think,
                            system_suffix=system_suffix, timeout=PER_CALL_TIMEOUT)
    print(f"loaded in {time.time() - t0:.1f}s")

    correct = 0
    latencies = []
    for msg, expected in SAMPLES_PTBR:
        t0 = time.time()
        got = dispatcher.classify(msg, language="pt-BR", model=model, think=think,
                                  system_suffix=system_suffix, timeout=PER_CALL_TIMEOUT)
        dt = time.time() - t0
        latencies.append(dt)
        ok = got == expected
        correct += int(ok)
        mark = "✓" if ok else "✗"
        print(f"  {mark} [{expected:<11}] -> [{got:<11}] {dt:5.2f}s  {msg}")

    n = len(SAMPLES_PTBR)
    pct = 100.0 * correct / n
    median = statistics.median(latencies)
    p95 = sorted(latencies)[int(0.95 * (n - 1))]
    print(f"  → score: {correct}/{n} ({pct:.0f}%)   median: {median:.2f}s   p95: {p95:.2f}s")

    print(f"  unloading {model}...")
    _unload(model)
    return {"label": label, "score": correct, "n": n, "median": median, "p95": p95}


def main():
    results = []
    for label, model, think, system_suffix in COMBOS:
        try:
            results.append(_run_combo(label, model, think, system_suffix))
        except KeyboardInterrupt:
            print("\n[interrupted]")
            break
        except Exception as e:
            print(f"  [combo failed] {e}")
            results.append({"label": label, "score": -1, "n": len(SAMPLES_PTBR), "median": float("nan"), "p95": float("nan")})

    print("\n" + "=" * 78)
    print(f"{'combo':<38} {'score':>8} {'pct':>6}  {'median':>8} {'p95':>8}")
    print("-" * 78)
    for r in results:
        score = f"{r['score']}/{r['n']}" if r["score"] >= 0 else "ERR"
        pct = f"{100.0 * r['score'] / r['n']:.0f}%" if r["score"] >= 0 else "—"
        print(f"{r['label']:<38} {score:>8} {pct:>6}  {r['median']:>7.2f}s {r['p95']:>7.2f}s")
    print("=" * 78)


if __name__ == "__main__":
    main()
