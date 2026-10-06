"""FastAPI service: real-time chat, batch inference, re-indexing and a Microsoft Teams webhook.

    uvicorn assistant.api:app --reload
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from . import __version__
from .agent import run_agent
from .config import get_settings
from .ingest import build_index, get_store

app = FastAPI(title="Agentic GenAI Enterprise Assistant", version=__version__)
_sessions: dict[str, deque] = defaultdict(lambda: deque(maxlen=2 * get_settings().history_turns))


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional shared-secret auth for low-code callers (Power Automate HTTP action)."""
    expected = get_settings().api_key
    if expected and not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class AgentResponse(BaseModel):
    answer: str
    sources: list[str]
    actions: list[dict]
    steps: int


class BatchRequest(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=500)


class BatchResponse(BaseModel):
    results: list[AgentResponse]


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "llm_provider": s.llm_provider, "indexed_chunks": len(get_store().store)}


@app.post("/chat", response_model=AgentResponse, dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest) -> dict:
    """Real-time inference: one question, optional conversation memory per session_id."""
    history = list(_sessions[req.session_id]) if req.session_id else []
    result = run_agent(req.message, history)
    if req.session_id:
        _sessions[req.session_id].extend([HumanMessage(req.message), AIMessage(result.answer)])
    return result.to_dict()


@app.post("/batch", response_model=BatchResponse, dependencies=[Depends(require_api_key)])
def batch(req: BatchRequest) -> dict:
    """Batch inference: answer many questions in parallel (order preserved)."""
    with ThreadPoolExecutor(max_workers=get_settings().batch_workers) as pool:
        results = list(pool.map(lambda q: run_agent(q).to_dict(), req.questions))
    return {"results": results}


@app.post("/ingest", dependencies=[Depends(require_api_key)])
def ingest() -> dict:
    """Rebuild the vector index from DOCS_DIR (e.g. after new documents are uploaded)."""
    store = build_index()
    return {"indexed_chunks": len(store.store)}


@app.post("/integrations/teams")
async def teams_outgoing_webhook(request: Request, authorization: str | None = Header(default=None)) -> dict:
    """Microsoft Teams *outgoing webhook*: @mention the bot in a channel, get an answer back."""
    body = await request.body()
    secret = get_settings().teams_webhook_secret
    if secret:
        digest = hmac.new(base64.b64decode(secret), body, hashlib.sha256).digest()
        expected = "HMAC " + base64.b64encode(digest).decode()
        if not hmac.compare_digest(authorization or "", expected):
            raise HTTPException(status_code=401, detail="Invalid Teams HMAC signature")
    activity = await request.json()
    text = re.sub(r"<at>.*?</at>", "", activity.get("text", "")).strip()
    text = re.sub(r"<[^>]+>", "", text).strip()  # Teams sends HTML
    if not text:
        return {"type": "message", "text": "Ask me about company policies, or ask me to open a ticket."}
    result = run_agent(text)
    reply = result.answer
    if result.actions:
        reply += "\n\n" + "\n".join(f"Ticket {a['ticket_id']}: {a['status']}" for a in result.actions)
    return {"type": "message", "text": reply}
