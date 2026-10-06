import json

import httpx

from assistant.agent import run_agent
from assistant.config import get_settings
from assistant.ingest import build_index, get_store


def test_index_is_built_and_persisted():
    store = build_index()
    assert len(store.store) > 0
    assert get_settings().index_path.exists()
    assert len(get_store().store) == len(store.store)  # reload from disk


def test_answers_from_documents_with_sources():
    result = run_agent("Within how many hours must a near miss be reported?")
    assert "24 hours" in result.answer
    assert result.sources[0] == "hse_site_safety_policy.md"
    assert result.actions == []
    assert result.steps == 2  # search tool call, then final answer


def test_unknown_topic_does_not_hallucinate():
    result = run_agent("zzqx quantum blockchain marmalade")
    assert "could not find" in result.answer.lower()


def test_ticket_request_triggers_workflow_action():
    result = run_agent("Please open a ticket to request VPN access")
    assert len(result.actions) == 1
    ticket = result.actions[0]
    assert ticket["category"] == "IT"
    assert ticket["ticket_id"] in result.answer
    logged = [json.loads(l) for l in get_settings().actions_log.read_text().splitlines()]
    assert logged[0]["ticket_id"] == ticket["ticket_id"]


def test_ticket_is_posted_to_power_automate_when_configured(monkeypatch):
    monkeypatch.setenv("POWER_AUTOMATE_WEBHOOK_URL", "https://example.invalid/flow")
    sent = {}

    def fake_post(url, json, timeout):
        sent.update(url=url, body=json)
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr("assistant.tools.httpx.post", fake_post)
    result = run_agent("Can you raise a ticket for a new laptop?")
    assert sent["url"] == "https://example.invalid/flow"
    assert sent["body"]["ticket_id"] == result.actions[0]["ticket_id"]
    assert result.actions[0]["status"] == "submitted to Power Automate"
