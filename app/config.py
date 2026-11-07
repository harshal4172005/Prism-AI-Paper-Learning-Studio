import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "ai_research_papers")

EMBEDDING_MODEL = "models/gemini-embedding-001"
GENERATION_MODELS = [m.strip() for m in os.getenv("GENERATION_MODELS", "gemini-2.5-flash").split(",") if m.strip()]
EMBEDDING_DIM = 768

# Text-only fallbacks used after every Gemini model is exhausted/rate-limited. Optional.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
