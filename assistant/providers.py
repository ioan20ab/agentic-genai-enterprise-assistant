"""Embedding and chat-model providers.

`openai`  -> ChatOpenAI / OpenAIEmbeddings (needs OPENAI_API_KEY).
`offline` -> a deterministic hashing embedder and a rule-based tool-calling chat
model, so the whole agent loop (tool calls, RAG, workflow actions) runs and is
testable without network access or API costs.
"""
from __future__ import annotations

import json
import math
import re
import uuid
import zlib
from typing import Any, Sequence

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .config import Settings

TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = set("""a an the and or of to in on for with by is are was were be been it its this that
these those at as from how what when where which who whom why can do does did i you we they he she my
our your their me us them should would could will may must not no yes if than then there here about
into over under up down out please tell""".split())


def _stem(t: str) -> str:
    """Minimal plural stemming so 'passwords' matches 'password'."""
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def tokens(text: str) -> list[str]:
    return [_stem(t) for t in TOKEN.findall(text.lower()) if t not in STOPWORDS]


class HashingEmbeddings(Embeddings):
    """Bag of unigrams + bigrams hashed into a fixed vector (lexical retrieval)."""

    def __init__(self, dim: int = 2048):
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        toks = tokens(text)
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        vec = [0.0] * self.dim
        for f in feats:
            vec[zlib.crc32(f.encode()) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


ACTION_INTENT = re.compile(r"\b(open|create|raise|log|submit|file)\b.{0,40}\b(ticket|request|incident)\b", re.I)


class OfflineToolCallingModel(BaseChatModel):
    """Deterministic stand-in for an LLM that follows the agent protocol.

    1. New user question  -> calls `search_documents`.
    2. Search results in  -> if the user asked for a ticket/request, calls `create_ticket`.
    3. Otherwise          -> answers extractively from the best matching sentences, citing sources.
    """

    bound_tool_names: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "offline-tool-calling"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "OfflineToolCallingModel":
        names = [getattr(t, "name", None) or t.get("name") for t in tools]
        return self.model_copy(update={"bound_tool_names": names})

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        question = next(m.content for m in reversed(messages) if isinstance(m, HumanMessage))
        turn = messages[max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage)):]
        tool_msgs = [m for m in turn if isinstance(m, ToolMessage)]
        called = {c["name"] for m in turn if isinstance(m, AIMessage) for c in m.tool_calls}

        if "search_documents" not in called and "search_documents" in self.bound_tool_names:
            return _call("search_documents", {"query": question})

        hits = []
        for m in tool_msgs:
            data = json.loads(m.content)
            if isinstance(data, dict) and "results" in data:
                hits.extend(data["results"])

        if ACTION_INTENT.search(question) and "create_ticket" not in called \
                and "create_ticket" in self.bound_tool_names:
            context = hits[0]["source"] if hits else "n/a"
            return _call("create_ticket", {
                "title": question[:90],
                "description": f"Raised by the assistant on behalf of the user. Related policy: {context}.",
                "category": _category(question),
            })

        return AIMessage(content=_compose_answer(question, hits, tool_msgs))


def _call(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}"}])


def _category(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ("laptop", "access", "vpn", "account", "password", "software")):
        return "IT"
    if any(w in q for w in ("safety", "incident", "ppe", "hazard", "site")):
        return "HSE"
    if any(w in q for w in ("expense", "travel", "reimburse")):
        return "Finance"
    return "General"


def _compose_answer(question: str, hits: list[dict], tool_msgs: list[ToolMessage]) -> str:
    ticket = next((json.loads(m.content) for m in tool_msgs if '"ticket_id"' in m.content), None)
    parts = []
    if hits:
        q = set(tokens(question))
        sentences = []
        for rank, h in enumerate(hits):
            for s in re.split(r"(?<=[.!?])\s+|\n+", h["content"]):
                s = s.strip(" -#*")
                overlap = len(q & set(tokens(s)))
                if len(s) > 25 and overlap:
                    sentences.append((overlap, -rank, s, h["source"]))
        best = sorted(sentences, reverse=True)[:2]
        if best:
            parts.append(" ".join(s for _, _, s, _ in best))
            parts.append("Sources: " + ", ".join(sorted({src for *_, src in best})))
    if ticket:
        parts.insert(0, f"I created ticket {ticket['ticket_id']} ({ticket['status']}).")
    return "\n".join(parts) or "I could not find this in the indexed documents."


def get_embeddings(settings: Settings) -> Embeddings:
    if settings.offline_embeddings:
        return HashingEmbeddings()
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=settings.embedding_model)


def get_chat_model(settings: Settings) -> BaseChatModel:
    if settings.llm_provider == "offline":
        return OfflineToolCallingModel()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.openai_model, temperature=settings.temperature)
