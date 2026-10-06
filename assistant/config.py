"""Runtime settings, read from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

ROOT = Path(__file__).resolve().parents[1]


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # LLM provider: "openai" uses the OpenAI API; "offline" uses the built-in
    # deterministic tool-calling model (no API key needed - used by tests/demos).
    llm_provider: str = field(default_factory=lambda: os.getenv(
        "LLM_PROVIDER", "openai" if os.getenv("OPENAI_API_KEY") else "offline"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    temperature: float = field(default_factory=lambda: float(os.getenv("TEMPERATURE", "0")))

    # RAG
    docs_dir: Path = field(default_factory=lambda: Path(os.getenv("DOCS_DIR", ROOT / "data" / "sample_docs")))
    index_path: Path = field(default_factory=lambda: Path(os.getenv("INDEX_PATH", ROOT / "data" / "index.json")))
    chunk_size: int = field(default_factory=lambda: int(os.getenv("CHUNK_SIZE", "800")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "120")))
    top_k: int = field(default_factory=lambda: int(os.getenv("TOP_K", "4")))

    # Agent
    max_steps: int = field(default_factory=lambda: int(os.getenv("MAX_AGENT_STEPS", "5")))
    history_turns: int = field(default_factory=lambda: int(os.getenv("HISTORY_TURNS", "6")))

    # Integrations
    power_automate_webhook_url: str = field(default_factory=lambda: os.getenv("POWER_AUTOMATE_WEBHOOK_URL", ""))
    actions_log: Path = field(default_factory=lambda: Path(os.getenv("ACTIONS_LOG", ROOT / "data" / "actions_log.jsonl")))
    teams_webhook_secret: str = field(default_factory=lambda: os.getenv("TEAMS_WEBHOOK_SECRET", ""))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", ""))
    batch_workers: int = field(default_factory=lambda: int(os.getenv("BATCH_WORKERS", "4")))
    offline_embeddings: bool = field(default_factory=lambda: _bool("OFFLINE_EMBEDDINGS", not os.getenv("OPENAI_API_KEY")))


def get_settings() -> Settings:
    return Settings()
