"""
Module: agent/orchestrator.py

Main agent loop. Coordinates the LLM client, context manager,
tool dispatcher, prompt builder, and sentiment monitor into
a coherent conversation-driven reservation agent.

Model: llama3-groq-8b-8192-tool-use-preview (8B, Groq API)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import AsyncGenerator

import structlog

from agent.llm_client import LLMClient
from agent.context_manager import ContextManager, ConversationState
from agent.prompt_builder import build_system_prompt, get_tool_schemas
from agent.tool_dispatcher import dispatch_all
from agent.sentiment_monitor import analyze_sentiment, check_prompt_injection

logger = structlog.get_logger(__name__)

# Maximum tool call rounds per user turn to prevent infinite loops
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "5"))


class AgentOrchestrator:
    """Stateful agent that manages a single conversation session.

    Usage::

        agent = AgentOrchestrator()
        async for event in agent.handle_message("Find Italian for 4"):
            # event is {"type": "token"/"tool_call"/"done"/"error", ...}
            ...
    """

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.context = ContextManager(session_id=self.session_id)
        self.llm = LLMClient()

    async def handle_message(
        self, user_message: str
    ) -> AsyncGenerator[dict, None]:
        """Process a user message and yield streaming events.

        Yields:
            {"type": "token", "content": str}
            {"type": "tool_start", "tool_name": str, "arguments": dict}
            {"type": "tool_result", "tool_name": str, "result": dict}
            {"type": "state_change", "old": str, "new": str}
            {"type": "done", "final_content": str}
            {"type": "error", "error": str}
        """

        logger.info(
            "user_message",
            session_id=self.session_id,
            turn=self.context.get_turn_count(),
            length=len(user_message),
        )

        # Fast path for simple greetings to avoid unnecessary LLM latency.
        trimmed = user_message.strip().lower()
        if re.fullmatch(
            r"(hi|hello|hey|hiya|good (morning|afternoon|evening))[!. ]*",
            trimmed,
        ):
            safe_greeting = (
                "Hello! I'm Sage, the GoodFoods reservation concierge. "
                "How can I help with your reservation today?"
            )
            self.context.add_user_message(user_message)
            self.context.add_assistant_message(safe_greeting)
            yield {"type": "token", "content": safe_greeting}
            yield {"type": "done", "final_content": safe_greeting}
            return
        # ── Security: Prompt injection check ───────────────
        if check_prompt_injection(user_message):
            logger.warning(
                "prompt_injection_detected",
                session_id=self.session_id,
            )
            safe_response = (
                "I appreciate your creativity, but I'm here to help "
                "with restaurant reservations! How can I assist you "
                "with finding a restaurant or making a booking?"
            )
            self.context.add_user_message(user_message)
            self.context.add_assistant_message(safe_response)
            yield {"type": "token", "content": safe_response}
            yield {"type": "done", "final_content": safe_response}
            return

        # ── Sentiment analysis ─────────────────────────────
        sentiment = analyze_sentiment(user_message, self.session_id)
        if sentiment.should_escalate:
            logger.info(
                "auto_escalation",
                session_id=self.session_id,
                urgency=sentiment.urgency_level,
                reason=sentiment.reason,
            )
            # Let the LLM handle it with escalation state
            self.context.set_conversation_state(ConversationState.ESCALATED)

        # ── Add message to context ─────────────────────────
        self.context.add_user_message(user_message)

        # Transition from GREETING on first substantive message
        if (
            self.context.get_conversation_state() == ConversationState.GREETING
            and self.context.get_turn_count() >= 1
        ):
            self.context.set_conversation_state(
                ConversationState.COLLECTING_CONSTRAINTS
            )

        # ── Agent loop ─────────────────────────────────────
        try:
            async for event in self._agent_loop():
                yield event
        except Exception as e:
            logger.error(
                "agent_loop_unhandled_error",
                session_id=self.session_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            error_msg = str(e)
            # Provide user-friendly messages for known error types
            if "429" in error_msg or "rate_limit" in error_msg:
                friendly = (
                    "Rate limit reached on the AI service. "
                    "Please wait 30 seconds and try again."
                )
            elif "validation failed" in error_msg.lower():
                friendly = (
                    "The AI generated an invalid request. "
                    "Please try rephrasing your message."
                )
            else:
                friendly = (
                    "Something went wrong processing your request. "
                    "Please try again."
                )
            yield {"type": "token", "content": friendly}
            yield {"type": "done", "final_content": friendly}

    async def _agent_loop(self) -> AsyncGenerator[dict, None]:
        """Core loop: call LLM → dispatch tools → repeat until final answer."""
        tools = get_tool_schemas()
        accumulated_content = ""
        consecutive_tool_errors = 0
        previous_tool_signature: tuple[tuple[str, str], ...] | None = None
        repeated_tool_signature_count = 0

        for round_num in range(MAX_TOOL_ROUNDS):
            system_prompt = build_system_prompt(
                conversation_state=self.context.get_conversation_state(),
                state_hint=self.context.get_state_hint(),
                booking_state_summary=self.context.get_booking_summary(),
            )

            messages = self.context.get_messages()

            # ── Determine force_tool_call ──────────────────
            force_tool = self._should_force_tool_call()

            logger.debug(
                "agent_loop_turn",
                session_id=self.session_id,
                round=round_num,
                state=self.context.get_conversation_state(),
                force_tool=force_tool,
                message_count=len(messages),
            )

            # ── Stream LLM response ───────────────────────
            tool_calls_received = None
            round_content = ""
            _function_detected = False  # Track if <function=...> text is streaming
            context_trimmed_for_retry = False

            async for event in self.llm.stream_complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
                tools=tools,
                session_id=self.session_id,
                force_tool_call=force_tool,
            ):
                if event["type"] == "token":
                    round_content += event["content"]
                    # Detect ALL Llama function-call variants:
                    #   <function=name>    (standard)
                    #   </function>name>   (broken variant)
                    #   </function>        (closing tag used as prefix)
                    if any(marker in round_content for marker in
                           ("<function=", "</function>", "<function>")):
                        _function_detected = True
                    # Only yield tokens if we haven't detected function syntax
                    if not _function_detected:
                        yield event

                elif event["type"] == "tool_call":
                    tool_calls_received = event["tool_calls"]

                elif event["type"] == "error":
                    error_text = str(event.get("error", ""))
                    if self._is_context_too_large_error(error_text):
                        removed = self.context.trim_to_target_tokens(
                            int(self.context.max_tokens * 0.7)
                        )
                        if removed > 0:
                            context_trimmed_for_retry = True
                            logger.warning(
                                "llm_context_retry",
                                session_id=self.session_id,
                                round=round_num,
                                removed_messages=removed,
                                estimated_tokens=self.context.get_estimated_tokens(),
                            )
                            break
                    yield event
                    return

            if context_trimmed_for_retry:
                continue

            # ── Handle tool calls ──────────────────────────
            if tool_calls_received:
                signature = tuple(
                    (
                        tc.get("name", ""),
                        json.dumps(
                            tc.get("arguments", {}),
                            sort_keys=True,
                            default=str,
                        ),
                    )
                    for tc in tool_calls_received
                )
                if signature == previous_tool_signature:
                    repeated_tool_signature_count += 1
                else:
                    repeated_tool_signature_count = 0
                previous_tool_signature = signature

                if repeated_tool_signature_count >= 1:
                    loop_msg = (
                        "I am seeing the same tool checks repeat without progress. "
                        "Please share an alternate date or time and I will continue."
                    )
                    self.context.add_assistant_message(loop_msg)
                    yield {"type": "token", "content": loop_msg}
                    yield {"type": "done", "final_content": loop_msg}
                    return

                # Record assistant message with tool calls
                tc_for_context = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in tool_calls_received
                ]
                self.context.add_assistant_message(
                    round_content or None, tc_for_context
                )

                # Dispatch all tool calls
                results = await dispatch_all(
                    tool_calls_received, self.session_id
                )

                has_validation_error = any(
                    not res.get("result", {}).get("success", False) 
                    and ("Missing required" in str(res.get("result", {}).get("error", "")) or "Unknown tool" in str(res.get("result", {}).get("error", "")))
                    for res in results
                )
                if has_validation_error:
                    consecutive_tool_errors += 1
                else:
                    consecutive_tool_errors = 0

                if consecutive_tool_errors >= 2:
                    logger.warning(
                        "circuit_breaker_triggered",
                        session_id=self.session_id,
                        errors=consecutive_tool_errors
                    )
                    fallback_msg = "Could you please provide a bit more detail? For example, the date, time, or party size you are looking for."
                    yield {
                        "type": "token",
                        "content": fallback_msg
                    }
                    self.context.add_assistant_message(fallback_msg)
                    yield {"type": "done", "final_content": fallback_msg}
                    return

                for res in results:
                    tool_name = next(
                        (
                            tc["name"]
                            for tc in tool_calls_received
                            if tc["id"] == res["tool_call_id"]
                        ),
                        "unknown",
                    )

                    yield {
                        "type": "tool_start",
                        "tool_name": tool_name,
                        "arguments": next(
                            (
                                tc["arguments"]
                                for tc in tool_calls_received
                                if tc["id"] == res["tool_call_id"]
                            ),
                            {},
                        ),
                    }

                    yield {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "result": res["result"],
                    }

                    # Add tool result to context
                    compact_content = self._compact_tool_result_for_context(
                        tool_name, res["result"]
                    )
                    self.context.add_tool_result(
                        res["tool_call_id"], compact_content
                    )

                    # Update state and booking based on result
                    self._process_tool_result(
                        tool_name, res["result"]
                    )

                fast_response = self._build_fast_tool_response(
                    tool_calls_received, results
                )
                if fast_response:
                    self.context.add_assistant_message(fast_response)
                    yield {"type": "token", "content": fast_response}
                    yield {"type": "done", "final_content": fast_response}
                    return

                # Loop continues — LLM needs to process tool results
                continue


            # ── Final answer (no tool call) ────────────────
            if not round_content:
                round_content = (
                    "I can help with that. Please share your preferred "
                    "date, time, and party size."
                )

            if round_content:
                # Strip ALL Llama-style function call variants:
                # 1) <function=name>{json}</function>
                # 2) </function>name>{json}</function>
                # 3) Any leftover tags
                cleaned = re.sub(
                    r'<function=\w+[^>]*>.*?</function>',
                    '',
                    round_content,
                    flags=re.DOTALL,
                )
                cleaned = re.sub(
                    r'</function>\w+>.*?</function>',
                    '',
                    cleaned,
                    flags=re.DOTALL,
                )
                # Catch any remaining stray tags
                cleaned = re.sub(r'</?function[^>]*>', '', cleaned)
                cleaned = cleaned.strip()
                if cleaned:
                    round_content = cleaned
                else:
                    # Entire response was a function call — provide fallback
                    round_content = (
                        "I'm processing your request. "
                        "Could you provide a bit more detail so I can help?"
                    )
                accumulated_content = round_content
                self.context.add_assistant_message(round_content)

            yield {
                "type": "done",
                "final_content": accumulated_content,
            }
            return

        # If we hit MAX_TOOL_ROUNDS, give up gracefully
        logger.warning(
            "max_tool_rounds_exceeded",
            session_id=self.session_id,
        )
        fallback = (
            "I apologize, but I'm having trouble processing your "
            "request right now. Could you please try rephrasing?"
        )
        self.context.add_assistant_message(fallback)
        yield {"type": "token", "content": fallback}
        yield {"type": "done", "final_content": fallback}

    def _should_force_tool_call(self) -> bool:
        """Determine if we should force a tool call this turn.

        NOTE: With the llama-3.1-8b model, tool_choice='required' is
        unreliable and produces malformed <function=...> syntax or
        'Failed to call a function' errors.  We always use 'auto'
        and let the model decide, so this is effectively disabled.
        """
        # Disabled — the 8B model handles tool calls better when
        # the decision is left to its own judgment via tool_choice='auto'.
        return False

    def _process_tool_result(
        self, tool_name: str, result: dict
    ) -> None:
        """Update booking state and conversation state from tool results."""
        success = result.get("success", False)

        # Auto-transition conversation state
        self.context.infer_state_from_tool(tool_name, success)

        if not success:
            return

        data = result.get("data", {})
        if not data:
            return

        # Extract booking-relevant info from results
        if tool_name == "search_restaurants":
            results_list = data.get("results", [])
            if results_list:
                # Store first result for quick reference
                first = results_list[0]
                compact_results = [
                    {
                        "restaurant_id": r.get("restaurant_id"),
                        "name": r.get("name"),
                        "cuisine_type": r.get("cuisine_type"),
                        "neighborhood": r.get("neighborhood"),
                        "score": r.get("score"),
                    }
                    for r in results_list[:3]
                ]
                self.context.update_booking_state(
                    search_results=compact_results,
                    restaurant_id=first.get("restaurant_id"),
                    restaurant_name=first.get("name"),
                )

        elif tool_name == "check_availability":
            if data.get("available"):
                compact_slots = self._compact_slots(
                    data.get("slots", []), limit=3
                )
                self.context.update_booking_state(
                    hold_id=data.get("hold_id"),
                    available_slots=compact_slots,
                )
                if data.get("slots"):
                    slot = data["slots"][0]
                    self.context.update_booking_state(
                        table_id=slot.get("table_id"),
                    )

        elif tool_name == "create_reservation":
            res = data.get("reservation", {})
            self.context.update_booking_state(
                reservation_id=res.get("id"),
                confirmation_code=res.get("confirmation_code"),
            )

        elif tool_name == "cancel_reservation":
            self.context.update_booking_state(
                cancellation_confirmed=True,
            )

        elif tool_name == "escalate_to_human":
            self.context.update_booking_state(
                escalation_id=data.get("escalation_id"),
            )

    # ── Convenience: non-streaming single-turn ─────────────


    def _build_fast_tool_response(
        self,
        tool_calls: list[dict],
        results: list[dict],
    ) -> str | None:
        """Build deterministic responses for common one-tool turns.

        This avoids an extra LLM round-trip and reduces latency/hallucinations.
        """
        if len(tool_calls) != 1 or len(results) != 1:
            return None

        tool_name = tool_calls[0].get("name", "")
        result = results[0].get("result", {})
        if not isinstance(result, dict):
            return None

        success = bool(result.get("success"))
        data = result.get("data") or {}

        if tool_name == "search_restaurants" and success:
            options = data.get("results", [])[:3]
            if not options:
                return (
                    "I couldn't find strong matches for that request yet. "
                    "Try adjusting cuisine, location, date, or time."
                )
            lines = ["I found these options:"]
            for idx, item in enumerate(options, start=1):
                name = item.get("name", "Unknown")
                cuisine = item.get("cuisine_type", "")
                hood = item.get("neighborhood", "")
                lines.append(f"{idx}. {name} ({cuisine}, {hood})")
            lines.append("Pick one, and I'll check live availability.")
            return "\n".join(lines)

        if tool_name == "check_availability" and success:
            if data.get("available"):
                slots = data.get("slots", [])
                if slots:
                    slot_labels: list[str] = []
                    seen_labels: set[str] = set()
                    for slot in slots:
                        label = self._format_slot_datetime(slot.get("datetime", ""))
                        if label not in seen_labels:
                            seen_labels.add(label)
                            slot_labels.append(label)
                        if len(slot_labels) >= 3:
                            break
                    slot_text = ", ".join(slot_labels) if slot_labels else "the requested window"
                    restaurant_name = data.get("restaurant_name", "that restaurant")
                    return (
                        f"{restaurant_name} has availability at {slot_text}. "
                        "Tell me which time you prefer and I'll proceed."
                    )
                return "I found availability. Tell me your preferred time and I'll proceed."
            wait_pos = data.get("waitlist_position")
            if wait_pos:
                return (
                    "No tables are open at that time. "
                    f"I can add you to the waitlist at about position #{wait_pos}, "
                    "or check another time."
                )
            return "No tables are open for that slot. Share another time and I'll recheck."

        if tool_name == "create_reservation" and success:
            reservation = data.get("reservation", {})
            code = reservation.get("confirmation_code")
            if code:
                return f"Your reservation is confirmed. Confirmation code: {code}."
            return "Your reservation is confirmed."

        if tool_name == "escalate_to_human" and success:
            return "A human agent has been notified and will assist you shortly."

        return None

    @staticmethod
    def _is_context_too_large_error(error_text: str) -> bool:
        lowered = error_text.lower()
        return (
            "request too large" in lowered
            or "tokens per minute" in lowered
            or ("limit" in lowered and "requested" in lowered and "tpm" in lowered)
        )

    def _compact_tool_result_for_context(self, tool_name: str, result: dict) -> str:
        """Store compact tool results in context to avoid token bloat."""
        if not isinstance(result, dict):
            return json.dumps(
                {
                    "success": False,
                    "error": "invalid_tool_result_shape",
                }
            )

        success = bool(result.get("success"))
        data = result.get("data") or {}
        compact: dict = {"success": success}

        if not success:
            compact["error"] = str(result.get("error", ""))[:200]
            compact["error_code"] = result.get("error_code")
            return json.dumps(compact, default=str)

        if tool_name == "search_restaurants":
            options = data.get("results", [])[:3]
            compact["data"] = {
                "total": data.get("total", len(options)),
                "results": [
                    {
                        "restaurant_id": r.get("restaurant_id"),
                        "name": r.get("name"),
                        "cuisine_type": r.get("cuisine_type"),
                        "neighborhood": r.get("neighborhood"),
                        "score": r.get("score"),
                    }
                    for r in options
                ],
            }
            return json.dumps(compact, default=str)

        if tool_name == "check_availability":
            compact["data"] = {
                "available": bool(data.get("available")),
                "restaurant_name": data.get("restaurant_name"),
                "hold_id": data.get("hold_id"),
                "hold_expires_at": data.get("hold_expires_at"),
                "waitlist_position": data.get("waitlist_position"),
                "slots": self._compact_slots(data.get("slots", []), limit=3),
            }
            return json.dumps(compact, default=str)

        if tool_name == "create_reservation":
            reservation = data.get("reservation", {})
            compact["data"] = {
                "reservation": {
                    "id": reservation.get("id"),
                    "confirmation_code": reservation.get("confirmation_code"),
                    "status": reservation.get("status"),
                    "reservation_datetime": reservation.get("reservation_datetime"),
                }
            }
            return json.dumps(compact, default=str)

        compact["data"] = data
        return json.dumps(compact, default=str)

    @staticmethod
    def _compact_slots(slots: list[dict], limit: int = 3) -> list[dict]:
        compact_slots: list[dict] = []
        for slot in slots[:limit]:
            compact_slots.append(
                {
                    "datetime": slot.get("datetime"),
                    "table_id": slot.get("table_id"),
                    "capacity": slot.get("capacity"),
                }
            )
        return compact_slots

    @staticmethod
    def _format_slot_datetime(raw_dt: str) -> str:
        if not raw_dt:
            return "an available time"
        try:
            dt = datetime.fromisoformat(raw_dt)
        except ValueError:
            try:
                dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
            except ValueError:
                return raw_dt
        hour = dt.strftime("%I").lstrip("0") or "12"
        return f"{dt.strftime('%a, %b %d')} at {hour}:{dt.strftime('%M %p')}"

    async def handle_message_sync(self, user_message: str) -> str:
        """Process a message and return the full response text.

        Useful for testing. Collects all tokens into a single string.
        """
        final = ""
        async for event in self.handle_message(user_message):
            if event["type"] == "token":
                final += event["content"]
            elif event["type"] == "done":
                final = event.get("final_content", final)
            elif event["type"] == "error":
                return f"Error: {event['error']}"
        return final

    def get_state(self) -> dict:
        """Return agent state for debugging."""
        return {
            "session_id": self.session_id,
            "context": self.context.to_dict(),
        }
