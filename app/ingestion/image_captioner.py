"""Captions extracted manual images with Gemini Vision so they become independently
searchable (instead of only riding along with whichever text chunk is nearby)."""
from PIL import Image

import google.generativeai as genai

from app.config import GEMINI_API_KEY, GENERATION_MODELS
from app.rag.generator import _first_success

genai.configure(api_key=GEMINI_API_KEY)

CAPTION_PROMPT = (
    "Describe this figure from an AI/ML research paper in 1-3 sentences. "
    "Note any architecture diagrams, plots, equations, or labeled components.\n\n"
    "Surrounding page text for context:\n{context}"
)


def caption_image(image_path: str, context_text: str) -> str:
    prompt = CAPTION_PROMPT.format(context=context_text[:1000])
    image = Image.open(image_path)

    def call(model_name):
        model = genai.GenerativeModel(model_name)
        response = model.generate_content([prompt, image], request_options={"timeout": 30})
        return response.text.strip()

    return _first_success([(lambda m=name: call(m)) for name in GENERATION_MODELS])


def _demo():
    prompt = CAPTION_PROMPT.format(context="the drain pump")
    assert "Describe this image" in prompt
    assert "the drain pump" in prompt


if __name__ == "__main__":
    _demo()
    print("ok")
