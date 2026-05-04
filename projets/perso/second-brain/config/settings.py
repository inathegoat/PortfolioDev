"""config/settings.py — Constantes globales du projet."""
import os
import sys
from pathlib import Path

# ── Chargement du .env ───────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Répertoires ──────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent.parent
PROJECT_ROOT   = BASE_DIR
DATA_DIR       = BASE_DIR / "data"
RAW_DIR        = DATA_DIR / "raw"
RAW_DATA_DIR   = RAW_DIR                        # alias
NOTES_DIR      = DATA_DIR / "notes"
DB_DIR         = DATA_DIR / "db"
LOGS_DIR       = BASE_DIR / "logs"
CHROMA_DIR     = DB_DIR / "chroma"
EXPORTS_DIR    = DATA_DIR / "exports"
PLUGINS_DIR    = BASE_DIR / "plugins"

TASKS_DIR = DATA_DIR / "tasks"
GOALS_DIR = DATA_DIR / "goals"

# ── Fichiers ─────────────────────────────────────────────────────────
TASKS_FILE = TASKS_DIR / "tasks.json"
GOALS_FILE = GOALS_DIR / "goals.json"
TASKS_DB   = DB_DIR / "tasks.db"
GOALS_DB   = DB_DIR / "goals.db"
CONV_DB    = DB_DIR / "conversations.db"
HIST_DB    = DB_DIR / "history.db"

METADATA_DB_PATH = DB_DIR / "metadata.db"

TOOLS_LOG_FILE = LOGS_DIR / "tool_executions.json"
ALLOWED_TOOL_DIRS = [NOTES_DIR, EXPORTS_DIR, TASKS_DIR]

# ── Initialisation des dossiers ──────────────────────────────────────

def init_directories():
    """Créer les dossiers au démarrage si nécessaire."""
    for d in [RAW_DIR, NOTES_DIR, DB_DIR, LOGS_DIR, CHROMA_DIR, EXPORTS_DIR,
              TASKS_DIR, GOALS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

init_directories()

# ── Ollama ───────────────────────────────────────────────────────────
OLLAMA_HOST     = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://localhost:11434"))
DEFAULT_MODEL   = os.getenv("LLM_MODEL", "qwen3:8b")
LLM_MODEL       = DEFAULT_MODEL
LLM_PROVIDER    = os.getenv("LLM_PROVIDER", "ollama")  # ollama, openai, deepseek, anthropic, groq...

EMBED_MODEL       = "bge-m3"                                 # sentence-transformers
OLLAMA_EMBED_MODEL = "nomic-embed-text"                      # alternative via Ollama
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL", EMBED_MODEL)

# ── Agent / Jarvis ───────────────────────────────────────────────────
AGENT_LOOP_INTERVAL   = int(os.getenv("AGENT_LOOP_INTERVAL", "900"))
ATTENTION_THRESHOLD   = float(os.getenv("ATTENTION_THRESHOLD", "0.6"))
MAX_HISTORY_MESSAGES  = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
MAX_CONTEXT_CHUNKS    = int(os.getenv("MAX_CONTEXT_CHUNKS", "5"))
TASK_PRIORITY_THRESHOLD = int(os.getenv("TASK_PRIORITY_THRESHOLD", "7"))
NOTIFICATION_COOLDOWN   = int(os.getenv("NOTIFICATION_COOLDOWN", "300"))
FOLLOW_UP_REMINDER_HOURS   = int(os.getenv("FOLLOW_UP_REMINDER_HOURS", "24"))
FOLLOW_UP_ESCALATION_HOURS = int(os.getenv("FOLLOW_UP_ESCALATION_HOURS", "72"))

# ── Chunking ─────────────────────────────────────────────────────────
CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))

# ── Retrieval ────────────────────────────────────────────────────────
TOP_K = int(os.getenv("TOP_K", "5"))

# ── Sécurité ─────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS  = {".pdf", ".txt", ".md", ".docx", ".xlsx", ".pptx"}
SUPPORTED_EXTENSIONS = ALLOWED_EXTENSIONS                  # alias

# ── Telegram ─────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_USERS  = os.getenv("TELEGRAM_ALLOWED_USERS", "")

# ── API ──────────────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "")
