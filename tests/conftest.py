import pytest


@pytest.fixture(autouse=True)
def offline_env(tmp_path, monkeypatch):
    """Every test runs offline against a fresh index and action log in tmp_path."""
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    monkeypatch.setenv("OFFLINE_EMBEDDINGS", "true")
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.json"))
    monkeypatch.setenv("ACTIONS_LOG", str(tmp_path / "actions.jsonl"))
    for var in ("POWER_AUTOMATE_WEBHOOK_URL", "API_KEY", "TEAMS_WEBHOOK_SECRET", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    from assistant.ingest import get_store

    get_store.cache_clear()
    yield
    get_store.cache_clear()
