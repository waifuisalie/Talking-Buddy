"""
Dispatcher: classifies a user turn into one of four intents.

RAG          — user is asking about their specialization corpus
FACT_RECALL  — user is asking about a personal fact they previously stated
FACT_STORE   — user is stating a personal fact worth remembering
CHITCHAT     — everything else (default fallback)

Single-token classification via Gemma3:1B. Calls Ollama directly with
system_prompt fully owned by this module — must NOT inherit personality bias
from the chat path. Defaults to CHITCHAT on any parse / network failure so the
chat path always has a usable label.
"""

import os
import re
import requests
from typing import Optional

VALID_INTENTS = ("RAG", "FACT_RECALL", "FACT_STORE", "CHITCHAT")
DEFAULT_INTENT = "CHITCHAT"

_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
_DISPATCHER_MODEL = os.getenv("DISPATCHER_MODEL", os.getenv("OLLAMA_MODEL", "gemma3:1b"))
_TIMEOUT = float(os.getenv("DISPATCHER_TIMEOUT", "30"))

_SYSTEM_PROMPT_PTBR = """Classifique a mensagem do usuário em UMA destas 4 categorias e responda SOMENTE com a palavra-rótulo, sem nada mais:

RAG          = pergunta sobre conteúdo de um livro/material/manual/apostila da especialização do assistente.
FACT_RECALL  = pergunta sobre um fato PESSOAL do próprio usuário que ele pode ter dito antes (ele quer LEMBRAR).
FACT_STORE   = afirmação/declaração sobre um fato PESSOAL do usuário no presente ou passado (ele está REGISTRANDO algo agora).
CHITCHAT     = qualquer outra coisa: cumprimentos, conversa fiada, conhecimento geral, comandos.

Regras:
- Termina com "?" e fala de "eu/meu/minha" → quase sempre FACT_RECALL.
- Termina com "?" e fala de "o livro/o material/capítulo/manual" → RAG.
- Frase declarativa sobre o que EU fiz/sinto/tenho → FACT_STORE.
- Cumprimento, piada, dúvida sobre o mundo → CHITCHAT.

Responda apenas a palavra: RAG, FACT_RECALL, FACT_STORE, ou CHITCHAT."""

_SYSTEM_PROMPT_EN = """Classify the user message into ONE of these 4 categories and reply ONLY with the label word:

RAG          = question about content from a book/manual/material from the assistant's specialization.
FACT_RECALL  = question about a PERSONAL fact about the user themselves that they may have stated before (they want to REMEMBER).
FACT_STORE   = statement/declaration about a PERSONAL fact about the user in present or past (they are RECORDING something now).
CHITCHAT     = anything else: greetings, small talk, general knowledge, commands.

Rules:
- Ends with "?" and mentions "I/my/me" → almost always FACT_RECALL.
- Ends with "?" and mentions "the book/the material/chapter/manual" → RAG.
- Declarative sentence about what I did/feel/have → FACT_STORE.
- Greeting, joke, question about the world → CHITCHAT.

Reply only the word: RAG, FACT_RECALL, FACT_STORE, or CHITCHAT."""

_FEW_SHOT_PTBR = [
    ("o que o livro diz sobre redes neurais?", "RAG"),
    ("resuma o capítulo 1", "RAG"),
    ("explica o material sobre regressão", "RAG"),
    ("já tomei meu remédio hoje?", "FACT_RECALL"),
    ("que dia eu fui ao médico?", "FACT_RECALL"),
    ("o que eu disse ontem?", "FACT_RECALL"),
    ("vou dormir agora", "FACT_STORE"),
    ("fui correr de manhã", "FACT_STORE"),
    ("dormi mal essa noite", "FACT_STORE"),
    ("oi", "CHITCHAT"),
    ("quem foi Einstein?", "CHITCHAT"),
    ("você gosta de futebol?", "CHITCHAT"),
]

_FEW_SHOT_EN = [
    ("what does the book say about neural networks?", "RAG"),
    ("summarize chapter 1", "RAG"),
    ("did I take my medicine today?", "FACT_RECALL"),
    ("when was my last appointment?", "FACT_RECALL"),
    ("I took losartan 50mg now", "FACT_STORE"),
    ("I just had lunch", "FACT_STORE"),
    ("hi how are you?", "CHITCHAT"),
    ("what is the capital of France?", "CHITCHAT"),
]


def _system_prompt_for(language: str) -> str:
    if language and language.lower().startswith("en"):
        return _SYSTEM_PROMPT_EN
    return _SYSTEM_PROMPT_PTBR


def _few_shot_for(language: str):
    if language and language.lower().startswith("en"):
        return _FEW_SHOT_EN
    return _FEW_SHOT_PTBR


def _parse(raw: str) -> str:
    if not raw:
        return DEFAULT_INTENT
    cleaned = re.sub(r"[^A-Za-z_]", " ", raw).strip().upper()
    if not cleaned:
        return DEFAULT_INTENT
    first = cleaned.split()[0]
    if first in VALID_INTENTS:
        return first
    for intent in VALID_INTENTS:
        if intent in cleaned:
            return intent
    return DEFAULT_INTENT


def classify(
    user_message: str,
    language: str = "pt-BR",
    model: Optional[str] = None,
    think: Optional[bool] = None,
    keep_alive: Optional[str] = None,
    timeout: Optional[float] = None,
    system_suffix: Optional[str] = None,
) -> str:
    """Return one of RAG | FACT_RECALL | FACT_STORE | CHITCHAT.

    `think`: forwarded to Ollama for thinking models (e.g. qwen3). None = use server default.
    `keep_alive`: forwarded as-is. Use "0" to unload the model after this call.

    Never raises. Falls back to CHITCHAT on any error.
    """
    if not user_message or not user_message.strip():
        return DEFAULT_INTENT

    sys_prompt = _system_prompt_for(language)
    if system_suffix:
        sys_prompt = sys_prompt + "\n\n" + system_suffix
    messages = [{"role": "system", "content": sys_prompt}]
    for sample, label in _few_shot_for(language):
        messages.append({"role": "user", "content": sample})
        messages.append({"role": "assistant", "content": label})
    messages.append({"role": "user", "content": user_message.strip()})

    payload = {
        "model": model or _DISPATCHER_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 6,
        },
    }
    if think is not None:
        payload["think"] = bool(think)
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive

    try:
        resp = requests.post(_OLLAMA_URL, json=payload, timeout=timeout or _TIMEOUT)
        if resp.status_code != 200:
            print(f"[DISPATCH] HTTP {resp.status_code}: {resp.text[:120]}")
            return DEFAULT_INTENT
        data = resp.json()
        raw = (data.get("message") or {}).get("content", "")
        intent = _parse(raw)
        return intent
    except requests.exceptions.Timeout:
        print(f"[DISPATCH] timeout after {timeout or _TIMEOUT}s")
        return DEFAULT_INTENT
    except Exception as e:
        print(f"[DISPATCH] non-fatal: {e}")
        return DEFAULT_INTENT


if __name__ == "__main__":
    import sys
    samples_ptbr = [
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

    print("(warmup)")
    classify("oi", language="pt-BR")  # load model into RAM
    correct = 0
    for msg, expected in samples_ptbr:
        got = classify(msg, language="pt-BR")
        ok = got == expected
        correct += int(ok)
        mark = "✓" if ok else "✗"
        print(f"{mark} [{expected:<11}] -> [{got:<11}]  {msg}")
    pct = 100.0 * correct / len(samples_ptbr)
    print(f"\nScore: {correct}/{len(samples_ptbr)} ({pct:.0f}%)")
    sys.exit(0 if correct >= 16 else 1)
