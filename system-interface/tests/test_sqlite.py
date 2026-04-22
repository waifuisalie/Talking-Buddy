#!/usr/bin/env python3
"""
Teste de Caixa Branca 5: SQLite — Latência de Recuperação de Contexto
Mede o tempo para buscar os últimos 8 turnos de conversa do banco SQLite.
Alvo: < 50 ms (P95), para que o histórico não atrase o início da inferência.

Uso (dentro de system-interface/, com venv ativo):
    python3 tests/test_sqlite.py
"""

import json
import os
import statistics
import sys
import tempfile
import time

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_BASE, 'src'))  # database.py
sys.path.insert(0, _BASE)                        # voice_assistant package

from database import Database
from voice_assistant.conversation_history import ConversationHistory

# ── Configuração ──────────────────────────────────────────────────────────────
TARGET_P95_MS = 50
RUNS          = 50  # repetições por cenário
MSG_COUNTS    = [8, 20, 50, 100, 200]  # tamanhos de histórico a testar
RESULTS_FILE  = os.path.join(os.path.dirname(__file__), "results_sqlite.json")

SAMPLE_MESSAGES = [
    ("user",      "Olá, como você está hoje?"),
    ("assistant", "Estou ótimo! Como posso ajudar você?"),
    ("user",      "Quero saber sobre o tempo em São Paulo."),
    ("assistant", "Em São Paulo hoje está ensolarado, 25°C."),
    ("user",      "Me fale mais sobre o projeto TalkingBuddy."),
    ("assistant", "TalkingBuddy é um assistente de voz 100% local para Raspberry Pi 5."),
    ("user",      "Qual a diferença entre Supertonic e Piper?"),
    ("assistant", "Supertonic é multilingual e até 9x mais rápido que o Piper."),
    ("user",      "Você pode me ajudar com uma conta de matemática?"),
    ("assistant", "Claro! Diga-me a operação e eu resolvo na hora."),
]


def populate(db: Database, user_id: int, n: int):
    db.clear_conversation_history(user_id, keep_last=0)
    for i in range(n):
        role, content = SAMPLE_MESSAGES[i % len(SAMPLE_MESSAGES)]
        db.add_conversation_message(user_id, role, content, "{}")


def benchmark(db: Database, user_id: int) -> list:
    """Retorna lista de latências em milissegundos."""
    history = ConversationHistory(db)
    latencies = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        history.get_context_for_llm(user_id, max_messages=8)
        latencies.append((time.perf_counter() - t0) * 1000)
    return latencies


def main():
    print("=" * 60)
    print("TESTE 5: SQLite — Latência de Recuperação de Contexto")
    print(f"Alvo: P95 < {TARGET_P95_MS}ms | {RUNS} execuções por cenário")
    print("=" * 60)

    results = []

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        user_id = db.add_user(
            "TestUser", "TEST_RFID_BENCH", "neutral (balanced)", "male", "pt-BR"
        )

        for n in MSG_COUNTS:
            print(f"\n📊 Histórico: {n} mensagens | buscando últimas 8")
            populate(db, user_id, n)
            lats = benchmark(db, user_id)

            med   = statistics.median(lats)
            mean  = statistics.mean(lats)
            p95   = sorted(lats)[int(0.95 * len(lats))]
            p99   = sorted(lats)[int(0.99 * len(lats))]
            ok    = p95 < TARGET_P95_MS
            status = "✅" if ok else "❌"

            print(f"  {status} Mediana={med:.2f}ms | Média={mean:.2f}ms | P95={p95:.2f}ms | P99={p99:.2f}ms")
            results.append({
                "history_size": n,
                "runs": RUNS,
                "median_ms": round(med, 3),
                "mean_ms": round(mean, 3),
                "p95_ms": round(p95, 3),
                "p99_ms": round(p99, 3),
                "passed": ok,
            })

        db.close()

    finally:
        try:
            os.unlink(db_path)
        except Exception:
            pass

    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    passed = sum(1 for r in results if r["passed"])
    print(f"  Passou: {passed}/{len(results)} cenários com P95 < {TARGET_P95_MS}ms")
    if results:
        worst_p95 = max(r["p95_ms"] for r in results)
        print(f"  Pior P95 encontrado: {worst_p95:.2f}ms")

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"target_p95_ms": TARGET_P95_MS, "results": results}, f, indent=2)
    print(f"\nResultados salvos em: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
