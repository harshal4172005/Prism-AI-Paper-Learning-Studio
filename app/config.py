import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "ai_research_papers")

EMBEDDING_MODEL = "models/gemini-embedding-001"
GENERATION_MODELS = ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
EMBEDDING_DIM = 768

# Text-only fallbacks used after every Gemini model is exhausted/rate-limited. Optional.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"
