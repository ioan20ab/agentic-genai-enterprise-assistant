"""Tools the agent can call: document retrieval (RAG) and workflow actions."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import httpx
from langchain_core.tools import tool

from .config import get_settings
from .ingest import get_store


@tool
def search_documents(query: str) -> dict:
    """Search the indexed enterprise documents (policies, procedures, manuals).
    Use this before answering any question about company rules or processes."""
    settings = get_settings()
    hits = get_store().similarity_search_with_score(query, k=settings.top_k)
    return {"results": [
        {"source": d.metadata.get("source"), "page": d.metadata.get("page"),
         "score": round(float(score), 4), "content": d.page_content}
        for d, score in hits
    ]}


@tool
def create_ticket(title: str, description: str, category: str = "General") -> dict:
    """Create a service ticket / request in the company workflow system (Power Automate).
    Use only when the user explicitly asks to open, raise or submit a ticket or request.
    category: one of IT, HSE, Finance, General."""
    settings = get_settings()
    ticket = {
        "ticket_id": f"TCK-{uuid.uuid4().hex[:6].upper()}",
        "title": title,
        "description": description,
        "category": category,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if settings.power_automate_webhook_url:
        resp = httpx.post(settings.power_automate_webhook_url, json=ticket, timeout=15)
        resp.raise_for_status()
        ticket["status"] = "submitted to Power Automate"
    else:
        settings.actions_log.parent.mkdir(parents=True, exist_ok=True)
        with settings.actions_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ticket) + "\n")
        ticket["status"] = "logged locally (no POWER_AUTOMATE_WEBHOOK_URL set)"
    return ticket


TOOLS = [search_documents, create_ticket]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
