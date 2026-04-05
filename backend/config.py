# backend/config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "uploaded"
CHROMA_PERSIST_DIR = BASE_DIR / "chroma_db"

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
LLM_MODEL = "llama3.1"
OLLAMA_BASE_URL = "http://localhost:11434"

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
TOP_K_RETRIEVAL = 3

HOST = "0.0.0.0"
PORT = 8000

# Create directories
DATA_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)