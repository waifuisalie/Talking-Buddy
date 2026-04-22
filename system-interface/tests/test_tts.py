#!/usr/bin/env python3
"""
Teste de Caixa Branca 3: TTS — Supertonic 2 e Piper (comparação)
Mede o RTF (Real-Time Factor) de cada engine.
RTF = tempo_de_síntese / duração_do_áudio_gerado
Alvo: RTF < 0.1 para Supertonic (processa 10x mais rápido que a locução).

Uso (dentro de system-interface/, com venv ativo):
    python3 tests/test_tts.py
"""

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# ── Configuração ──────────────────────────────────────────────────────────────
RTF_TARGET    = 0.1
RESULTS_FILE  = os.path.join(os.path.dirname(__file__), "results_tts.json")

# Piper paths (mesmos do CLAUDE.md / config.py)
PIPER_BINARY  = os.path.expanduser("~/piper/piper/piper")
PIPER_MODEL   = os.path.expanduser("~/piper/piper/pt_BR-faber-medium.onnx")

TEST_PHRASES = [
    # (label, text)
    ("curta",    "Olá! Como posso ajudar você hoje?"),
    ("média",    "O assistente virtual está pronto para responder suas perguntas sobre o projeto."),
    ("longa",    "A inteligência artificial local roda completamente no Raspberry Pi 5 sem precisar de conexão com a internet, garantindo privacidade total."),
    ("números",  "A temperatura está em vinte e cinco graus e a bateria em noventa por cento."),
    ("pergunta", "Você gostaria de saber mais sobre as funcionalidades disponíveis no sistema de voz?"),
]


# ── Utilitários ───────────────────────────────────────────────────────────────

def wav_duration(path: str) -> float:
    with wave.open(path) as wf:
        return wf.getnframes() / wf.getframerate()


# ── Supertonic ────────────────────────────────────────────────────────────────

def test_supertonic() -> list:
    print("\n── Supertonic 2 TTS ──────────────────────────────────────────")
    try:
        from supertonic import TTS
    except ImportError:
        print("  ❌ Supertonic não instalado (pip install supertonic)")
        return []

    print("  🔄 Carregando modelo Supertonic...")
    t_load = time.perf_counter()
    tts = TTS()
    load_time = time.perf_counter() - t_load
    print(f"  ✅ Modelo carregado em {load_time:.2f}s")

    results = []
    for label, text in TEST_PHRASES:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out = f.name
        try:
            t0 = time.perf_counter()
            wav_array, duration = tts.synthesize(
                text, voice_style=tts.get_voice_style("M2"), lang="pt"
            )
            tts.save_audio(wav_array, out)
            synth_time = time.perf_counter() - t0

            audio_dur = wav_duration(out)
            rtf = synth_time / audio_dur if audio_dur > 0 else float("inf")
            ok  = rtf < RTF_TARGET

            status = "✅" if ok else "❌"
            print(f"  {status} [{label:8s}] RTF={rtf:.4f} | synth={synth_time:.3f}s | áudio={audio_dur:.2f}s")
            results.append({
                "label": label, "text": text,
                "synth_time_s": round(synth_time, 3),
                "audio_duration_s": round(audio_dur, 3),
                "rtf": round(rtf, 4),
                "passed": ok,
            })
        finally:
            try:
                os.unlink(out)
            except Exception:
                pass

    if results:
        rtfs = [r["rtf"] for r in results]
        print(f"\n  📊 RTF médio: {statistics.mean(rtfs):.4f} | máx: {max(rtfs):.4f} | alvo < {RTF_TARGET}")
        print(f"  💡 Tempo de carregamento do modelo: {load_time:.2f}s (não conta no RTF)")
    return results


# ── Piper ─────────────────────────────────────────────────────────────────────

def test_piper() -> list:
    print("\n── Piper TTS ──────────────────────────────────────────────────")
    if not os.path.exists(PIPER_BINARY):
        print(f"  ⚠️  Piper não encontrado: {PIPER_BINARY}")
        return []
    if not os.path.exists(PIPER_MODEL):
        print(f"  ⚠️  Modelo Piper não encontrado: {PIPER_MODEL}")
        return []

    print(f"  ✅ Piper: {PIPER_BINARY}")
    print(f"  ✅ Modelo: {PIPER_MODEL}")

    results = []
    for label, text in TEST_PHRASES:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out = f.name
        try:
            cmd = [PIPER_BINARY, "--model", PIPER_MODEL, "--output_file", out]
            t0 = time.perf_counter()
            proc = subprocess.run(
                cmd, input=text, capture_output=True, text=True, timeout=30
            )
            synth_time = time.perf_counter() - t0

            if proc.returncode != 0:
                print(f"  ❌ [{label:8s}] Piper retornou erro: {proc.stderr[:80]}")
                continue

            audio_dur = wav_duration(out)
            rtf = synth_time / audio_dur if audio_dur > 0 else float("inf")
            ok  = rtf < RTF_TARGET

            status = "✅" if ok else "❌"
            print(f"  {status} [{label:8s}] RTF={rtf:.4f} | synth={synth_time:.3f}s | áudio={audio_dur:.2f}s")
            results.append({
                "label": label, "text": text,
                "synth_time_s": round(synth_time, 3),
                "audio_duration_s": round(audio_dur, 3),
                "rtf": round(rtf, 4),
                "passed": ok,
            })
        finally:
            try:
                os.unlink(out)
            except Exception:
                pass

    if results:
        rtfs = [r["rtf"] for r in results]
        print(f"\n  📊 RTF médio: {statistics.mean(rtfs):.4f} | máx: {max(rtfs):.4f} | alvo < {RTF_TARGET}")
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("TESTE 3: TTS — RTF (Real-Time Factor)")
    print(f"Alvo: RTF < {RTF_TARGET}  (10x mais rápido que a locução natural)")
    print("=" * 60)

    supertonic_results = test_supertonic()
    piper_results      = test_piper()

    # ── Comparação ────────────────────────────────────────────────────────────
    if supertonic_results and piper_results:
        print("\n── Comparação Supertonic vs Piper ─────────────────────────────")
        for s, p in zip(supertonic_results, piper_results):
            if s["label"] == p["label"]:
                speedup = p["rtf"] / s["rtf"] if s["rtf"] > 0 else float("inf")
                print(f"  [{s['label']:8s}] Supertonic RTF={s['rtf']:.4f} | Piper RTF={p['rtf']:.4f} | Supertonic {speedup:.1f}x mais rápido")

    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    if supertonic_results:
        rtfs = [r["rtf"] for r in supertonic_results]
        passed = sum(1 for r in supertonic_results if r["passed"])
        print(f"  Supertonic: {passed}/{len(supertonic_results)} abaixo de RTF {RTF_TARGET}")
        print(f"  RTF médio: {statistics.mean(rtfs):.4f}")
    if piper_results:
        rtfs = [r["rtf"] for r in piper_results]
        passed = sum(1 for r in piper_results if r["passed"])
        print(f"  Piper:      {passed}/{len(piper_results)} abaixo de RTF {RTF_TARGET}")
        print(f"  RTF médio: {statistics.mean(rtfs):.4f}")
    if not supertonic_results and not piper_results:
        print("  Nenhum engine TTS disponível para testar.")

    out = {
        "rtf_target": RTF_TARGET,
        "supertonic": supertonic_results,
        "piper": piper_results,
    }
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nResultados salvos em: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
