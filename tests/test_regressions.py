"""
Targeted regression tests for recent reliability fixes.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_chat_invalid_json_returns_400():
    """Malformed JSON body to /chat should return a clean 400 response."""
    from mcp_server.server import chat_stream

    class _BadRequest:
        async def json(self):
            raise ValueError("invalid json")

    response = await chat_stream(_BadRequest())
    assert response.status_code == 400
    body = json.loads(response.body.decode("utf-8"))
    assert body["error"] == "invalid json body"


@pytest.mark.asyncio
async def test_llm_daily_quota_short_circuits_without_retry(monkeypatch):
    """Daily quota errors should not emit retry tokens."""
    from agent import llm_client as llm_module
    from agent.llm_client import LLMClient

    quota_error = (
        "Error code: 429 - {'error': {'message': "
        "'Rate limit reached on tokens per day (TPD): Limit 500000, "
        "Used 499999, Requested 2000', 'type': 'tokens'}}"
    )

    class _FakeCompletions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            raise Exception(quota_error)

    fake_completions = _FakeCompletions()

    class _FakeGroq:
        def __init__(self, api_key: str):
            self.chat = SimpleNamespace(completions=fake_completions)

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm_module, "AsyncGroq", _FakeGroq)

    client = LLMClient()
    events = []
    async for event in client.stream_complete(
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
        session_id="quota-test",
    ):
        events.append(event)

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "tokens per day" in events[0]["error"].lower()
    assert fake_completions.calls == 1


@pytest.mark.asyncio
async def test_llm_generic_rate_limit_short_circuits_without_retry(monkeypatch):
    """Any 429/rate-limit error should return immediately without retry tokens."""
    from agent import llm_client as llm_module
    from agent.llm_client import LLMClient

    rate_limit_error = "Error code: 429 - {'error': {'message': 'rate_limit_exceeded'}}"

    class _FakeCompletions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            raise Exception(rate_limit_error)

    fake_completions = _FakeCompletions()

    class _FakeGroq:
        def __init__(self, api_key: str):
            self.chat = SimpleNamespace(completions=fake_completions)

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm_module, "AsyncGroq", _FakeGroq)

    client = LLMClient()
    events = []
    async for event in client.stream_complete(
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
        session_id="rate-limit-test",
    ):
        events.append(event)

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "429" in events[0]["error"]
    assert fake_completions.calls == 1


def test_fast_response_deduplicates_duplicate_slot_times():
    """Fast-path availability response should not repeat identical times."""
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)

    tool_calls = [{"name": "check_availability"}]
    results = [{
        "result": {
            "success": True,
            "data": {
                "available": True,
                "restaurant_name": "Le Petit Kitchen",
                "slots": [
                    {"datetime": "2026-03-15T19:00:00"},
                    {"datetime": "2026-03-15T19:00:00"},
                    {"datetime": "2026-03-15T19:00:00"},
                    {"datetime": "2026-03-15T19:30:00"},
                ],
            },
        }
    }]

    text = orchestrator._build_fast_tool_response(tool_calls, results)
    assert text is not None
    assert text.count("Mar 15 at 7:00 PM") == 1
    assert "Mar 15 at 7:30 PM" in text


def test_compact_tool_result_limits_slots_to_three():
    """Context payload for availability should include at most 3 slots."""
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)

    compact_json = orchestrator._compact_tool_result_for_context(
        "check_availability",
        {
            "success": True,
            "data": {
                "available": True,
                "restaurant_name": "Rosemary Garden",
                "hold_id": "hold-123",
                "hold_expires_at": "2026-03-10T10:00:00",
                "slots": [
                    {"datetime": "2026-03-10T19:00:00", "table_id": "t1", "capacity": 4},
                    {"datetime": "2026-03-10T19:30:00", "table_id": "t2", "capacity": 4},
                    {"datetime": "2026-03-10T20:00:00", "table_id": "t3", "capacity": 4},
                    {"datetime": "2026-03-10T20:30:00", "table_id": "t4", "capacity": 4},
                ],
            },
        },
    )

    compact = json.loads(compact_json)
    assert compact["success"] is True
    assert len(compact["data"]["slots"]) == 3
