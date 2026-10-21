from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from querymind.config import Settings
from querymind.service import QueryMindService

API_DIR = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Environment first, then querymind-api/.env, then querymind-agentic/.env."""
    load_dotenv(API_DIR / ".env")
    return Settings.from_env()


@lru_cache(maxsize=1)
def get_service() -> QueryMindService:
    # One shared instance so Qdrant, LLM and database clients are reused across requests.
    return QueryMindService(get_settings())
