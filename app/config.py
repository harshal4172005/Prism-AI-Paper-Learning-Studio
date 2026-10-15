import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "appliance_manuals")

EMBEDDING_MODEL = "models/gemini-embedding-001"
GENERATION_MODEL = "gemini-3.8-flash"
VISION_MODEL = "gemini-3.8-flash"
EMBEDDING_DIM = 768
