#!/usr/bin/env python3
"""
Teste de Caixa Branca 1: STT — Whisper.cpp Latência de Transcrição
Gera áudios de ~5s com Supertonic, transcreve com whisper-cli e mede latência.
Alvo: < 2s por transcrição em ARM64.

Uso (dentro de system-interface/, com venv ativo):
    python3 tests/test_stt.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# ── Configuração ──────────────────────────────────────────────────────────────
WHISPER_CLI   = os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli")
WHISPER_MODEL = os.path.expanduser("~/whisper.cpp/models/ggml-base.bin")
WHISPER_THREADS = 4
WHISPER_AUDIO_CTX = 512
TARGET_SECS   = 2.0
WHISPER_LANG  = "pt"

TEST_PHRASES = [
    "Olá, tudo bem com você? Fico feliz em poder ajudar hoje.",
    "O assistente virtual TalkingBuddy está funcionando e pronto para responder.",
    "Qual é a temperatura em São Paulo? Vai chover mais tarde?",
    "Explique de forma simples como funciona a inteligência artificial.",
    "Obrigado pela sua ajuda durante nossa conversa. Foi muito útil.",
]

RESULTS_FILE = os.path.join(os.path.dirname(__file__), "results_stt.json")


def generate_audio(text: str, out_path: str) -> bool:
    """Gera áudio WAV com Supertonic TTS."""
    try:
        from supertonic import TTS
        tts = TTS()
        wav_array, _ = tts.synthesize(text, voice_style=tts.get_voice_style("M2"), lang="pt")
        tts.save_audio(wav_array, out_path)
        return True
    except Exception as e:
        print(f"  ⚠️  Supertonic falhou: {e}")
        return False


def convert_to_16k(src: str, dst: str) -> bool:
    """Converte WAV para 16 kHz mono (necessário para whisper-cli)."""
    try:
        import scipy.io.wavfile as wavfile
        import numpy as np
        from scipy.signal import resample_poly
        from math import gcd

        sr, data = wavfile.read(src)
        if data.ndim > 1:
            data = data[:, 0]  # mono

        if sr != 16000:
            g = gcd(16000, sr)
            data = resample_poly(data, 16000 // g, sr // g).astype(np.int16)

        wavfile.write(dst, 16000, data.astype(np.int16))
        return True
    except Exception as e:
        print(f"  ⚠️  Conversão áudio falhou ({e}), tentando ffmpeg...")
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", dst],
                capture_output=True, timeout=15
            )
            return r.returncode == 0
        except Exception as e2:
            print(f"  ⚠️  ffmpeg também falhou ({e2}), usando arquivo original")
            import shutil
            shutil.copy(src, dst)
            return True


def get_audio_duration(wav_path: str) -> float:
    with wave.open(wav_path) as wf:
        return wf.getnframes() / wf.getframerate()


def transcribe(wav_path: str) -> tuple:
    """
    Transcreve o arquivo de áudio com whisper-cli.
    Retorna (texto_transcrito, tempo_em_segundos).
    """
    cmd = [
        WHISPER_CLI,
        "-m", WHISPER_MODEL,
        "-l", WHISPER_LANG,
        "-t", str(WHISPER_THREADS),
        "-ac", str(WHISPER_AUDIO_CTX),
        "--no-timestamps",
        "-otxt",
        "-f", wav_path,
    ]
    t0 = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    elapsed = time.perf_counter() - t0

    txt_path = wav_path + ".txt"
    if os.path.exists(txt_path):
        with open(txt_path, encoding="utf-8") as f:
            text = f.read().strip()
        os.unlink(txt_path)
    else:
        text = result.stdout.strip()

    return text, elapsed


def main():
    print("=" * 60)
    print("TESTE 1: STT — Whisper.cpp Latência de Transcrição")
    print(f"Alvo: < {TARGET_SECS}s por transcrição | {len(TEST_PHRASES)} frases de teste")
    print("=" * 60)

    if not os.path.exists(WHISPER_CLI):
        print(f"❌ whisper-cli não encontrado: {WHISPER_CLI}")
        sys.exit(1)
    if not os.path.exists(WHISPER_MODEL):
        print(f"❌ Modelo Whisper não encontrado: {WHISPER_MODEL}")
        sys.exit(1)

    print(f"✅ whisper-cli: {WHISPER_CLI}")
    print(f"✅ Modelo: {WHISPER_MODEL}")

    results = []

    for i, phrase in enumerate(TEST_PHRASES, 1):
        print(f"\n[{i}/{len(TEST_PHRASES)}] \"{phrase}\"")

        with tempfile.TemporaryDirectory() as tmpdir:
            raw_wav  = os.path.join(tmpdir, "raw.wav")
            conv_wav = os.path.join(tmpdir, f"test_{i}.wav")

            print("  🎙️  Gerando áudio com Supertonic...")
            if not generate_audio(phrase, raw_wav):
                print("  ❌ Falha ao gerar áudio, pulando")
                continue

            convert_to_16k(raw_wav, conv_wav)
            audio_dur = get_audio_duration(conv_wav)
            print(f"  📊 Duração do áudio: {audio_dur:.2f}s")

            print("  🔄 Transcrevendo com whisper-cli...")
            transcribed, elapsed = transcribe(conv_wav)

            ok = elapsed < TARGET_SECS
            status = "✅" if ok else "❌"
            print(f"  {status} Latência: {elapsed:.2f}s  (alvo < {TARGET_SECS}s)")
            print(f"  📝 Original:   \"{phrase}\"")
            print(f"  📝 Transcrito: \"{transcribed}\"")

            results.append({
                "phrase": phrase,
                "transcribed": transcribed,
                "audio_duration_s": round(audio_dur, 3),
                "transcription_time_s": round(elapsed, 3),
                "passed": ok,
            })

    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    if results:
        passed = sum(1 for r in results if r["passed"])
        avg_time = sum(r["transcription_time_s"] for r in results) / len(results)
        print(f"Passou: {passed}/{len(results)} frases abaixo de {TARGET_SECS}s")
        print(f"Latência média: {avg_time:.2f}s")
    else:
        print("Nenhum resultado — verifique dependências.")

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"results": results, "target_s": TARGET_SECS}, f, indent=2, ensure_ascii=False)
    print(f"\nResultados salvos em: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
