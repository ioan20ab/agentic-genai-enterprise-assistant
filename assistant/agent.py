"""Tool-calling agent loop: the LLM decides which tools to call until it can answer."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from .config import get_settings
from .providers import get_chat_model
from .tools import TOOLS, TOOLS_BY_NAME

SYSTEM_PROMPT = """You are an enterprise assistant for company employees.
- Always call `search_documents` before answering questions about policies or procedures.
- Answer ONLY from the retrieved documents; if they do not contain the answer, say so.
- Keep answers short (max 5 sentences) and end with "Sources:" listing the document names you used.
- Call `create_ticket` only when the user explicitly asks to open, raise or submit a ticket/request,
  then confirm the ticket id to the user."""


@dataclass
class AgentResult:
    answer: str
    sources: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    steps: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def run_agent(question: str, history: list[BaseMessage] | None = None) -> AgentResult:
    settings = get_settings()
    model = get_chat_model(settings).bind_tools(TOOLS)
    messages: list[BaseMessage] = [SystemMessage(SYSTEM_PROMPT), *(history or []), HumanMessage(question)]
    sources: list[str] = []
    actions: list[dict] = []

    for step in range(1, settings.max_steps + 1):
        ai: AIMessage = model.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            return AgentResult(answer=str(ai.content), sources=sources, actions=actions, steps=step)
        for call in ai.tool_calls:
            tool = TOOLS_BY_NAME.get(call["name"])
            if tool is None:
                output = {"error": f"unknown tool {call['name']}"}
            else:
                try:
                    output = tool.invoke(call["args"])
                except Exception as exc:  # surface tool errors to the model instead of crashing
                    output = {"error": f"{type(exc).__name__}: {exc}"}
            if call["name"] == "search_documents" and "results" in output:
                for r in output["results"]:
                    if r["source"] not in sources:
                        sources.append(r["source"])
            elif call["name"] == "create_ticket":
                actions.append(output)
            messages.append(ToolMessage(content=json.dumps(output), tool_call_id=call["id"]))

    return AgentResult(answer="I could not complete the request within the step limit.",
                       sources=sources, actions=actions, steps=settings.max_steps)
