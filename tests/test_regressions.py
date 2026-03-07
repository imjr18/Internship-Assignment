"""
Targeted regression tests for recent reliability fixes.
"""

from __future__ import annotations

import json
import re
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


def test_modify_invalid_input_fast_response_prompts_for_details():
    """Modify tool INVALID_INPUT should trigger a clarification prompt."""
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)

    tool_calls = [{"name": "modify_reservation"}]
    results = [{
        "result": {
            "success": False,
            "error_code": "INVALID_INPUT",
            "error": "No effective changes detected",
        }
    }]

    text = orchestrator._build_fast_tool_response(tool_calls, results)
    assert text is not None
    assert "What would you like to change" in text


def test_process_tool_result_modify_updates_booking_state():
    """Successful modify_reservation should update date/time fields in state."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-modify-state")

    orchestrator._process_tool_result(
        "modify_reservation",
        {
            "success": True,
            "data": {
                "restaurant_name": "Mint Spoon",
                "reservation": {
                    "id": "res-123",
                    "confirmation_code": "GF-ABC123",
                    "party_size": 4,
                    "reservation_datetime": "2026-03-08T20:00:00",
                    "special_requests": "quiet corner",
                },
            },
        },
    )

    state = orchestrator.context.get_booking_state()
    assert state["reservation_id"] == "res-123"
    assert state["confirmation_code"] == "GF-ABC123"
    assert state["restaurant_name"] == "Mint Spoon"
    assert state["party_size"] == 4
    assert state["date"] == "Sun, Mar 08"
    assert state["time"] == "8:00 PM"


@pytest.mark.asyncio
async def test_chat_stream_emits_done_fallback_text(monkeypatch):
    """If no token events are emitted, done.final_content should still be streamed."""
    from mcp_server import server as server_module

    class _FakeAgent:
        async def handle_message(self, _message: str):
            yield {"type": "done", "final_content": "Fallback final reply"}

    class _FakeRequest:
        async def json(self):
            return {"session_id": "done-fallback-test", "message": "hello"}

    monkeypatch.setattr(server_module, "_get_agent", lambda _sid: _FakeAgent())
    response = await server_module.chat_stream(_FakeRequest())

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    joined = "".join(chunks)

    assert "Fallback final reply" in joined
    assert "[DONE]" in joined


def test_modify_details_detector_requires_explicit_new_value():
    """Generic modify intent should not count as an explicit change."""
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)

    assert orchestrator._has_explicit_modification_details("can i modify it?") is False
    assert orchestrator._has_explicit_modification_details("change time please") is False
    assert orchestrator._has_explicit_modification_details("change it to 8 pm") is True
    assert orchestrator._has_explicit_modification_details("make it for 5 people") is True


def test_sanitize_assistant_text_removes_partial_function_prefix():
    """Partial function fragments should never be shown to the user."""
    from agent.orchestrator import AgentOrchestrator

    cleaned = AgentOrchestrator._sanitize_assistant_text(
        "I'll check options now <function"
    )
    assert cleaned == "I'll check options now"


def test_sanitize_assistant_text_removes_dangling_angle_bracket():
    """Stray trailing '<' should be removed from assistant output."""
    from agent.orchestrator import AgentOrchestrator

    cleaned = AgentOrchestrator._sanitize_assistant_text(
        "Based on your preferences, I'll search for options <"
    )
    assert cleaned == "Based on your preferences, I'll search for options"


def test_option_ranking_query_returns_deterministic_concise_response():
    """Best-option questions should use ranking shortcut and avoid repetition."""
    from agent.context_manager import ContextManager, ConversationState
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-option-ranking")
    orchestrator.context.set_conversation_state(ConversationState.PRESENTING_OPTIONS)
    orchestrator.context.update_booking_state(
        search_results=[
            {"name": "Mint Spoon", "score": 0.91},
            {"name": "Luna Corner", "score": 0.84},
            {"name": "Sol Garden", "score": 0.79},
        ]
    )

    text = orchestrator._try_handle_option_ranking_query("which one has the best food")
    assert text is not None
    assert "Mint Spoon" in text
    assert "Want me to check availability there?" in text


def test_option_ranking_query_handles_closest_to_downtown():
    """Closest-to-downtown should be answered deterministically."""
    from agent.context_manager import ContextManager, ConversationState
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-option-distance")
    orchestrator.context.set_conversation_state(ConversationState.PRESENTING_OPTIONS)
    orchestrator.context.update_booking_state(
        search_results=[
            {"name": "Rosemary Vine", "neighborhood": "Harbor District", "score": 0.88},
            {"name": "Downtown Table", "neighborhood": "Downtown", "score": 0.60},
            {"name": "East Room", "neighborhood": "East Village", "score": 0.90},
        ]
    )

    text = orchestrator._try_handle_option_ranking_query(
        "which one is closest to downtown?"
    )
    assert text is not None
    assert "Downtown Table" in text
    assert "closest to Downtown" in text
    state = orchestrator.context.get_booking_state()
    assert state["restaurant_name"] == "Downtown Table"
    assert state.get("restaurant_selected_explicit") is True


def test_capture_presented_option_selection_by_name():
    """Selecting a presented option by name should update restaurant context."""
    from agent.context_manager import ContextManager, ConversationState
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-option-pick-name")
    orchestrator.context.set_conversation_state(ConversationState.PRESENTING_OPTIONS)
    orchestrator.context.update_booking_state(
        search_results=[
            {"restaurant_id": "rest-1", "name": "Rosemary Vine"},
            {"restaurant_id": "rest-2", "name": "Sol Nest"},
            {"restaurant_id": "rest-3", "name": "Fig Cafe"},
        ]
    )

    changed = orchestrator._capture_presented_option_selection("Rosemary vine it is then")
    state = orchestrator.context.get_booking_state()
    assert changed is True
    assert state["restaurant_id"] == "rest-1"
    assert state["restaurant_name"] == "Rosemary Vine"
    assert state.get("restaurant_selected_explicit") is True


def test_capture_presented_option_selection_by_number():
    """Selecting 'option 2' should map to the second presented restaurant."""
    from agent.context_manager import ContextManager, ConversationState
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-option-pick-number")
    orchestrator.context.set_conversation_state(ConversationState.PRESENTING_OPTIONS)
    orchestrator.context.update_booking_state(
        search_results=[
            {"restaurant_id": "rest-1", "name": "Rosemary Vine"},
            {"restaurant_id": "rest-2", "name": "Sol Nest"},
            {"restaurant_id": "rest-3", "name": "Fig Cafe"},
        ]
    )

    changed = orchestrator._capture_presented_option_selection("option 2 please")
    state = orchestrator.context.get_booking_state()
    assert changed is True
    assert state["restaurant_id"] == "rest-2"
    assert state["restaurant_name"] == "Sol Nest"
    assert state.get("restaurant_selected_explicit") is True


def test_extract_relative_date_and_time_from_text():
    """Parser should pick up relative day + coarse time words."""
    from agent.orchestrator import AgentOrchestrator

    date_iso = AgentOrchestrator._extract_date_iso_from_text("this Saturday evening")
    time_24 = AgentOrchestrator._extract_time_24_from_text("this Saturday evening")

    assert date_iso is not None
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", date_iso)
    assert time_24 == "19:00"


def test_extract_party_size_from_short_replies_and_friends_phrase():
    """Party-size parser should handle short numeric replies and friends phrasing."""
    from agent.orchestrator import AgentOrchestrator

    assert AgentOrchestrator._extract_party_size_from_text("5") == 5
    assert AgentOrchestrator._extract_party_size_from_text("5 including me") == 5
    assert AgentOrchestrator._extract_party_size_from_text("five") == 5
    assert AgentOrchestrator._extract_party_size_from_text("me and 4 friends") == 5
    assert (
        AgentOrchestrator._extract_party_size_from_text(
            "lively, i am coming with 4 of my friends"
        )
        == 5
    )


def test_enrich_tool_arguments_uses_booking_state_date_and_time():
    """Availability call should be auto-filled from known booking context."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-enrich-tool-args")
    orchestrator.context.update_booking_state(
        restaurant_id="rest-123",
        party_size=2,
        party_size_explicit=True,
        date_iso="2026-03-10",
        time_24="20:00",
    )

    tool_calls = [{
        "id": "tc-1",
        "name": "check_availability",
        "arguments": {},
    }]
    orchestrator._enrich_tool_arguments_from_state(tool_calls)

    args = tool_calls[0]["arguments"]
    assert args["restaurant_id"] == "rest-123"
    assert args["party_size"] == 2
    assert args["date"] == "2026-03-10"
    assert args["preferred_time"] == "20:00"


def test_enrich_tool_arguments_overrides_model_date_when_user_explicit():
    """Explicit user date/time in state should override stale model guesses."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-enrich-override")
    orchestrator.context.update_booking_state(
        party_size=2,
        party_size_explicit=True,
        date_iso="2026-03-08",
        time_24="20:00",
        date_explicit=True,
        time_explicit=True,
    )

    tool_calls = [{
        "id": "tc-2",
        "name": "check_availability",
        "arguments": {"date": "2026-03-12", "preferred_time": "19:00"},
    }]
    orchestrator._enrich_tool_arguments_from_state(tool_calls)

    args = tool_calls[0]["arguments"]
    assert args["date"] == "2026-03-08"
    assert args["preferred_time"] == "20:00"


def test_resolve_party_size_uses_existing_state_even_if_flag_missing():
    """Critical tool guard should accept known party size from state."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-resolve-size-state")
    orchestrator.context.update_booking_state(party_size=5, party_size_explicit=False)

    tool_calls = [{
        "id": "tc-size-1",
        "name": "search_restaurants",
        "arguments": {"query": "indian", "date": "2026-03-20", "time": "20:00"},
    }]

    resolved = orchestrator._resolve_party_size_for_critical_tools(
        tool_calls,
        latest_user_message="indian or italian near downtown",
    )
    assert resolved is True
    assert tool_calls[0]["arguments"]["party_size"] == 5
    state = orchestrator.context.get_booking_state()
    assert state["party_size"] == 5


def test_resolve_party_size_uses_latest_user_message_short_number():
    """A short numeric reply like '5' should satisfy critical tool guard."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-resolve-size-user")

    tool_calls = [{
        "id": "tc-size-2",
        "name": "search_restaurants",
        "arguments": {"query": "lively indian", "date": "2026-03-20", "time": "20:00"},
    }]

    resolved = orchestrator._resolve_party_size_for_critical_tools(
        tool_calls,
        latest_user_message="5",
    )
    assert resolved is True
    assert tool_calls[0]["arguments"]["party_size"] == 5
    state = orchestrator.context.get_booking_state()
    assert state["party_size"] == 5
    assert state["party_size_explicit"] is True


def test_resolve_party_size_uses_tool_arguments_as_last_resort():
    """If parser misses, valid tool arg party_size should still unblock flow."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-resolve-size-toolarg")

    tool_calls = [{
        "id": "tc-size-3",
        "name": "check_availability",
        "arguments": {
            "restaurant_id": "rest-123",
            "date": "2026-03-20",
            "preferred_time": "20:00",
            "party_size": "5",
        },
    }]

    resolved = orchestrator._resolve_party_size_for_critical_tools(
        tool_calls,
        latest_user_message="yes please",
    )
    assert resolved is True
    state = orchestrator.context.get_booking_state()
    assert state["party_size"] == 5
    assert state["party_size_explicit"] is True


def test_booking_summary_hides_internal_metadata_keys():
    """Prompt-facing booking summary should exclude internal context keys."""
    from agent.context_manager import ContextManager

    ctx = ContextManager(session_id="regression-booking-summary-filter")
    ctx.update_booking_state(
        party_size=5,
        party_size_explicit=True,
        date_iso="2026-03-20",
        date="2026-03-20",
        time_24="20:00",
        time="20:00",
        restaurant_name="Indigo Palace",
        search_results=[{"name": "Indigo Palace"}],
    )

    summary = ctx.get_booking_summary()
    assert "Party size: 5" in summary
    assert "Date: 2026-03-20" in summary
    assert "Time: 20:00" in summary
    assert "Restaurant: Indigo Palace" in summary
    assert "party_size_explicit" not in summary
    assert "search_results" not in summary
    assert "date_iso" not in summary
    assert "time_24" not in summary


@pytest.mark.asyncio
async def test_agent_loop_filters_partial_function_fragment_tokens():
    """Streamed partial function fragments should not be surfaced as user tokens."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator

    class _FakeLLM:
        async def stream_complete(self, **kwargs):
            yield {"type": "token", "content": "Based on your preferences, I will search now. "}
            yield {"type": "token", "content": "<"}

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.session_id = "regression-partial-token-filter"
    orchestrator.context = ContextManager(session_id=orchestrator.session_id)
    orchestrator.llm = _FakeLLM()

    events = []
    async for event in orchestrator._agent_loop():
        events.append(event)

    token_text = "".join(
        str(e.get("content", ""))
        for e in events
        if e.get("type") == "token"
    )
    done_event = next(e for e in events if e.get("type") == "done")

    assert token_text.strip().endswith("search now.")
    assert "<" not in token_text
    assert "<" not in str(done_event.get("final_content", ""))


@pytest.mark.asyncio
async def test_agent_loop_modify_requests_confirmation_before_dispatch():
    """Explicit modify request should ask confirmation before applying changes."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator

    class _FakeLLM:
        async def stream_complete(self, **kwargs):
            yield {
                "type": "tool_call",
                "tool_calls": [{
                    "id": "tc-mod-1",
                    "name": "modify_reservation",
                    "arguments": {
                        "reservation_id": "res-123",
                        "changes": {"new_datetime": "2026-03-19T20:00:00"},
                    },
                }],
            }

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.session_id = "regression-modify-confirm-gate"
    orchestrator.context = ContextManager(session_id=orchestrator.session_id)
    orchestrator.llm = _FakeLLM()
    orchestrator.context.add_user_message("change the date to march 19 at 8 pm")

    events = []
    async for event in orchestrator._agent_loop():
        events.append(event)

    text = "".join(
        str(e.get("content", ""))
        for e in events
        if e.get("type") == "token"
    )
    assert "Please confirm" in text
    state = orchestrator.context.get_booking_state()
    assert state.get("pending_modify_awaiting_confirm") is True
    assert isinstance(state.get("pending_modify_args"), dict)


@pytest.mark.asyncio
async def test_handle_message_confirm_executes_pending_modification(monkeypatch):
    """Pending modification should execute only after explicit confirmation."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator
    from agent import orchestrator as orchestrator_module

    async def _fake_dispatch_all(tool_calls, session_id):
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "modify_reservation"
        return [{
            "tool_call_id": tool_calls[0]["id"],
            "result": {
                "success": True,
                "data": {
                    "restaurant_name": "Sol Garden",
                    "reservation": {
                        "id": "res-123",
                        "confirmation_code": "GF-XYZ999",
                        "party_size": 6,
                        "reservation_datetime": "2026-03-19T20:00:00",
                        "special_requests": "",
                    },
                },
            },
        }]

    monkeypatch.setattr(orchestrator_module, "dispatch_all", _fake_dispatch_all)

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.session_id = "regression-modify-confirm-exec"
    orchestrator.context = ContextManager(session_id=orchestrator.session_id)
    orchestrator.llm = None  # not used in pending-confirm path
    orchestrator.context.update_booking_state(
        pending_modify_awaiting_confirm=True,
        pending_modify_args={
            "reservation_id": "res-123",
            "changes": {"new_datetime": "2026-03-19T20:00:00"},
        },
    )

    events = []
    async for event in orchestrator.handle_message("yes please, confirm"):
        events.append(event)

    event_types = [e.get("type") for e in events]
    assert "tool_start" in event_types
    assert "tool_result" in event_types
    token_text = "".join(
        str(e.get("content", ""))
        for e in events
        if e.get("type") == "token"
    )
    assert "updated" in token_text.lower()


def test_rewrite_create_to_modify_in_modification_mode():
    """In modification mode, create_reservation should be rewritten to modify_reservation."""
    from agent.context_manager import ContextManager
    from agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.context = ContextManager(session_id="regression-rewrite-create-to-modify")
    orchestrator.context.update_booking_state(
        modification_context_active=True,
        reservation_id="res-777",
        party_size=6,
        date_iso="2026-03-18",
        time_24="13:00",
    )

    tool_calls = [{
        "id": "tc-create-1",
        "name": "create_reservation",
        "arguments": {
            "restaurant_id": "rest-123",
            "hold_id": "hold-123",
        },
    }]

    orchestrator._rewrite_create_to_modify_in_modification_mode(tool_calls)

    rewritten = tool_calls[0]
    assert rewritten["name"] == "modify_reservation"
    args = rewritten["arguments"]
    assert args["reservation_id"] == "res-777"
    assert args["changes"]["new_datetime"] == "2026-03-18T13:00:00"
    assert args["changes"]["new_party_size"] == 6
