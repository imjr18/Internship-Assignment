"""Phase 4 verification: test context manager and prompt builder."""

import sys

sys.path.insert(0, ".")

from agent.context_manager import ContextManager, ConversationState
from agent.prompt_builder import build_system_prompt

print("=== Test 1: State machine transitions ===")
ctx = ContextManager("test-001")
assert ctx.get_conversation_state() == ConversationState.GREETING
ctx.set_conversation_state(ConversationState.COLLECTING_CONSTRAINTS)
assert ctx.get_conversation_state() == ConversationState.COLLECTING_CONSTRAINTS
print("PASS: State transitions work")

print("\n=== Test 2: Booking state accumulation ===")
ctx.update_booking_state(party_size=4, cuisine_preference="Italian")
ctx.update_booking_state(date="2026-04-01", time="19:00")
bs = ctx.get_booking_state()
assert bs["party_size"] == 4
assert bs["date"] == "2026-04-01"
print("PASS: Booking state accumulates")

print("\n=== Test 3: Message history ===")
ctx.add_user_message("Find Italian for 4")
ctx.add_assistant_message("Let me search for you!", None)
msgs = ctx.get_messages()
assert len(msgs) == 2
assert msgs[0]["role"] == "user"
assert msgs[1]["role"] == "assistant"
print("PASS: Message history works")

print("\n=== Test 4: Token budget enforcement ===")
ctx2 = ContextManager("test-002", max_tokens=50)
for i in range(20):
    ctx2.add_user_message(f"Message {i} " * 50)
# Should have trimmed old messages
assert len(ctx2.messages) < 20
print(f"PASS: Budget enforced — {len(ctx2.messages)} messages kept")

print("\n=== Test 5: Booking summary ===")
summary = ctx.get_booking_summary()
assert "Party size: 4" in summary
assert "Italian" in summary
print(f"PASS: Summary generated:\n{summary}")

print("\n=== Test 6: State inference from tool ===")
ctx.infer_state_from_tool("search_restaurants", True)
assert ctx.get_conversation_state() == ConversationState.PRESENTING_OPTIONS
ctx.infer_state_from_tool("check_availability", True)
assert ctx.get_conversation_state() == ConversationState.CONFIRMING_DETAILS
ctx.infer_state_from_tool("create_reservation", True)
assert ctx.get_conversation_state() == ConversationState.COMPLETED
print("PASS: State inference works")

print("\n=== Test 7: Prompt builder ===")
prompt = build_system_prompt(
    conversation_state=ConversationState.COLLECTING_CONSTRAINTS,
    state_hint="Ask ONE missing detail at a time.",
    booking_state_summary="- Party size: 4\n- Cuisine: Italian",
)
assert "Sage" in prompt
assert "COLLECTING_CONSTRAINTS" in prompt
assert "Party size: 4" in prompt
assert "Security Rules" in prompt  # injection defense
print("PASS: Prompt built correctly")
print(f"Prompt length: {len(prompt)} chars")

print("\n=== Test 8: Tool result in context ===")
ctx3 = ContextManager("test-003")
ctx3.add_user_message("Find Italian for 4")
ctx3.add_assistant_message(
    None,
    [{"id": "tc1", "type": "function", "function": {"name": "search_restaurants", "arguments": "{}"}}],
)
ctx3.add_tool_result("tc1", '{"success": true, "data": []}')
msgs = ctx3.get_messages()
assert msgs[2]["role"] == "tool"
assert msgs[2]["tool_call_id"] == "tc1"
print("PASS: Tool results stored in context")

print("\n=== Test 9: Serialisation ===")
state = ctx.to_dict()
assert state["session_id"] == "test-001"
assert state["state"] == ConversationState.COMPLETED
print(f"PASS: Serialisation works: {state}")

print("\n" + "=" * 50)
print("All context manager tests passed!")
