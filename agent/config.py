from os import getenv

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = (getenv("DATABASE_URL") or "").strip()
DB_POOL_MIN_CONN = int(getenv("DB_POOL_MIN_CONN", "1"))
DB_POOL_MAX_CONN = int(getenv("DB_POOL_MAX_CONN", "5"))
DB_CONNECT_TIMEOUT = int(getenv("DB_CONNECT_TIMEOUT", "10"))
GROQ_API_KEY = (getenv("GROQ_API_KEY") or "").strip()
GROQ_MODEL = (getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()

if DB_POOL_MIN_CONN < 1:
    raise RuntimeError("DB_POOL_MIN_CONN must be at least 1.")

if DB_POOL_MAX_CONN < DB_POOL_MIN_CONN:
    raise RuntimeError("DB_POOL_MAX_CONN must be greater than or equal to DB_POOL_MIN_CONN.")

if not GROQ_MODEL:
    raise RuntimeError("GROQ_MODEL must be a non-empty string.")
