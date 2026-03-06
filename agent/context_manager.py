"""
Module: agent/context_manager.py

Manages conversation history, token budget, booking state, and
conversation state machine for the GoodFoods agent.
"""

from __future__ import annotations

import copy
import os
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Approximate tokens per character for budget estimation
_CHARS_PER_TOKEN = 4
# Default max tokens to keep in context
MAX_CONTEXT_TOKENS = int(
    os.getenv("MAX_CONTEXT_TOKENS", "3200")
)  # leaves headroom for tool schemas + output


class ConversationState:
    """Finite state machine for conversation flow."""

    GREETING = "GREETING"
    COLLECTING_CONSTRAINTS = "COLLECTING_CONSTRAINTS"
    SEARCHING = "SEARCHING"
    PRESENTING_OPTIONS = "PRESENTING_OPTIONS"
    CONFIRMING_DETAILS = "CONFIRMING_DETAILS"
    BOOKING_IN_PROGRESS = "BOOKING_IN_PROGRESS"
    MODIFYING = "MODIFYING"
    CANCELLING = "CANCELLING"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"

    VALID_STATES = {
        GREETING,
        COLLECTING_CONSTRAINTS,
        SEARCHING,
        PRESENTING_OPTIONS,
        CONFIRMING_DETAILS,
        BOOKING_IN_PROGRESS,
        MODIFYING,
        CANCELLING,
        COMPLETED,
        ESCALATED,
    }


# State hints guide the LLM on what to do next
STATE_HINTS: dict[str, str] = {
    ConversationState.GREETING: (
        "Greet the guest warmly. Ask what they're looking for today."
    ),
    ConversationState.COLLECTING_CONSTRAINTS: (
        "Ask ONE missing detail at a time: party size, date, time, "
        "cuisine, or dietary needs. Do not ask multiple questions."
    ),
    ConversationState.SEARCHING: (
        "You have enough info. Call search_restaurants now."
    ),
    ConversationState.PRESENTING_OPTIONS: (
        "Present the search results clearly. Ask which option "
        "the guest prefers."
    ),
    ConversationState.CONFIRMING_DETAILS: (
        "Confirm booking details with the guest: name, email, "
        "phone, special requests. Then call create_reservation."
    ),
    ConversationState.BOOKING_IN_PROGRESS: (
        "A reservation is being created. Wait for the result."
    ),
    ConversationState.MODIFYING: (
        "The guest wants to change a reservation. Identify "
        "what needs to change and call modify_reservation."
    ),
    ConversationState.CANCELLING: (
        "The guest wants to cancel. Confirm the reservation "
        "details then call cancel_reservation."
    ),
    ConversationState.COMPLETED: (
        "The booking is confirmed. Summarise the details and "
        "ask if there's anything else."
    ),
    ConversationState.ESCALATED: (
        "The conversation has been escalated to a human agent."
    ),
}


class ContextManager:
    """Manages conversation context for a single session.

    Responsibilities:
    - Message history with token budget enforcement
    - Conversation state machine transitions
    - Booking state accumulation (party_size, date, etc.)
    - Tool result tracking
    """

    def __init__(self, session_id: str, max_tokens: int = MAX_CONTEXT_TOKENS):
        self.session_id = session_id
        self.max_tokens = max_tokens
        self.messages: list[dict] = []
        self._state = ConversationState.GREETING
        self._booking: dict[str, Any] = {}
        self._tool_results: list[dict] = []
        self._turn_count = 0
        self._created_at = datetime.now(timezone.utc).isoformat()

    # ── State management ───────────────────────────────────

    def get_conversation_state(self) -> str:
        return self._state

    def set_conversation_state(self, new_state: str) -> None:
        if new_state not in ConversationState.VALID_STATES:
            logger.warning(
                "invalid_state_transition",
                session_id=self.session_id,
                attempted=new_state,
            )
            return
        old = self._state
        self._state = new_state
        logger.info(
            "state_transition",
            session_id=self.session_id,
            old=old,
            new=new_state,
        )

    def get_state_hint(self) -> str:
        return STATE_HINTS.get(self._state, "")

    # ── Booking state ──────────────────────────────────────

    def get_booking_state(self) -> dict:
        return copy.deepcopy(self._booking)

    def update_booking_state(self, **kwargs: Any) -> None:
        self._booking.update(kwargs)
        logger.debug(
            "booking_state_updated",
            session_id=self.session_id,
            keys=list(kwargs.keys()),
        )

    def get_booking_summary(self) -> str:
        """Human-readable summary of known booking details."""
        if not self._booking:
            return "No booking details collected yet."
        parts = []
        field_labels = {
            "party_size": "Party size",
            "date": "Date",
            "time": "Time",
            "cuisine_preference": "Cuisine",
            "dietary_requirements": "Dietary needs",
            "location_preference": "Location",
            "restaurant_id": "Restaurant ID",
            "restaurant_name": "Restaurant",
            "table_id": "Table ID",
            "guest_name": "Guest name",
            "guest_email": "Email",
            "guest_phone": "Phone",
            "special_requests": "Special requests",
            "confirmation_code": "Confirmation code",
            "reservation_id": "Reservation ID",
            "hold_id": "Hold ID",
        }
        for key, val in self._booking.items():
            label = field_labels.get(key, key)
            parts.append(f"- {label}: {val}")
        return "\n".join(parts)

    # ── Message history ────────────────────────────────────

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self._turn_count += 1
        self._enforce_budget()

    def add_assistant_message(
        self, content: str | None, tool_calls: list[dict] | None = None
    ) -> None:
        msg: dict = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)
        self._enforce_budget()

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }
        )
        self._enforce_budget()
        self._tool_results.append(
            {
                "tool_call_id": tool_call_id,
                "content": content[:200],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_messages(self) -> list[dict]:
        """Return message history (deep copy)."""
        return copy.deepcopy(self.messages)

    def get_turn_count(self) -> int:
        return self._turn_count

    def get_estimated_tokens(self) -> int:
        return self._estimate_tokens()

    # ── Token budget ───────────────────────────────────────

    def _estimate_tokens(self) -> int:
        total_chars = sum(
            len(str(m.get("content", ""))) for m in self.messages
        )
        return total_chars // _CHARS_PER_TOKEN

    def _enforce_budget(self) -> None:
        """Drop oldest user/assistant pairs if over budget."""
        while self._estimate_tokens() > self.max_tokens and len(self.messages) > 2:
            # Never drop tool results in isolation — drop pairs
            removed = self.messages.pop(0)
            logger.debug(
                "message_trimmed",
                session_id=self.session_id,
                role=removed.get("role"),
            )

    # ── Infer state from tool calls ────────────────────────

    def trim_to_target_tokens(self, target_tokens: int) -> int:
        """Aggressively trim oldest messages until estimated tokens fit target."""
        removed_count = 0
        safe_target = max(200, target_tokens)
        while self._estimate_tokens() > safe_target and len(self.messages) > 2:
            self.messages.pop(0)
            removed_count += 1
        if removed_count:
            logger.warning(
                "context_trimmed_for_retry",
                session_id=self.session_id,
                removed_messages=removed_count,
                estimated_tokens=self._estimate_tokens(),
                target_tokens=safe_target,
            )
        return removed_count

    def infer_state_from_tool(self, tool_name: str, success: bool) -> None:
        """Automatically transition state after a tool call."""
        transitions = {
            "search_restaurants": (
                ConversationState.PRESENTING_OPTIONS if success
                else ConversationState.COLLECTING_CONSTRAINTS
            ),
            "check_availability": (
                ConversationState.CONFIRMING_DETAILS if success
                else ConversationState.PRESENTING_OPTIONS
            ),
            "create_reservation": (
                ConversationState.COMPLETED if success
                else ConversationState.CONFIRMING_DETAILS
            ),
            "modify_reservation": (
                ConversationState.COMPLETED if success
                else ConversationState.MODIFYING
            ),
            "cancel_reservation": (
                ConversationState.COMPLETED if success
                else ConversationState.CANCELLING
            ),
            "escalate_to_human": (
                ConversationState.ESCALATED, ConversationState.ESCALATED
            ),
        }
        new_state = transitions.get(tool_name)
        if isinstance(new_state, tuple):
            new_state = new_state[0]
        if new_state:
            self.set_conversation_state(new_state)

    # ── Debug / serialisation ──────────────────────────────

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "state": self._state,
            "turn_count": self._turn_count,
            "booking": self._booking,
            "message_count": len(self.messages),
            "estimated_tokens": self._estimate_tokens(),
            "created_at": self._created_at,
        }
