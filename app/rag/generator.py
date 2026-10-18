"""Generates a grounded troubleshooting answer from retrieved manual chunks (text + diagrams).

Falls back across models when one is unavailable or rate-limited: Gemini models
(with images) first, then Groq, then NVIDIA NIM (text-only, no image grounding).
"""
import json
import urllib.request
from pathlib import Path

import google.generativeai as genai
from PIL import Image

from app.config import (
    GEMINI_API_KEY,
    GENERATION_MODELS,
    GROQ_API_KEY,
    GROQ_MODEL,
    NVIDIA_API_KEY,
    NVIDIA_MODEL,
)

genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = (
    "You are an AI/ML technical assistant. Answer the user's question using ONLY the "
    "provided paper excerpts and figures/diagrams. Cite the page number for each fact you use. "
    "If the excerpts don't contain the answer, say so instead of guessing."
)

MAX_IMAGES = 4
REQUEST_TIMEOUT = 30


def _gemini_call(model_name: str, prompt: str, images: list) -> str:
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        [prompt, *images], request_options={"timeout": REQUEST_TIMEOUT}
    )
    return response.text


def _openai_compatible_call(base_url: str, api_key: str, model: str, prompt: str) -> str:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.load(resp)
    return data["choices"][0]["message"]["content"]


def _first_success(attempts: list):
    last_exc = RuntimeError("no attempts given")
    for attempt in attempts:
        try:
            return attempt()
        except Exception as exc:
            last_exc = exc
            continue
    raise last_exc


def generate_answer(query: str, retrieved_chunks: list[dict]) -> str:
    context = "\n\n".join(f"[Page {c['page_number']}] {c['text']}" for c in retrieved_chunks)

    images = []
    for chunk in retrieved_chunks:
        for image_path in chunk["image_paths"]:
            if len(images) >= MAX_IMAGES:
                break
            if Path(image_path).exists():
                images.append(Image.open(image_path))

    prompt = f"{SYSTEM_PROMPT}\n\nManual excerpts:\n{context}\n\nQuestion: {query}"

    attempts = [
        (lambda m=model_name: _gemini_call(m, prompt, images)) for model_name in GENERATION_MODELS
    ]
    if GROQ_API_KEY:
        attempts.append(
            lambda: _openai_compatible_call("https://api.groq.com/openai/v1", GROQ_API_KEY, GROQ_MODEL, prompt)
        )
    if NVIDIA_API_KEY:
        attempts.append(
            lambda: _openai_compatible_call(
                "https://integrate.api.nvidia.com/v1", NVIDIA_API_KEY, NVIDIA_MODEL, prompt
            )
        )

    return _first_success(attempts)


def _demo():
    calls = []

    def fail():
        calls.append("fail")
        raise RuntimeError("boom")

    def ok():
        calls.append("ok")
        return "answer"

    assert _first_success([fail, fail, ok]) == "answer"
    assert calls == ["fail", "fail", "ok"]

    try:
        _first_success([fail, fail])
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected all-fail to raise")


if __name__ == "__main__":
    _demo()
    print("ok")
