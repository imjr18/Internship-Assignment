"""
Module: agent/orchestrator.py

Main agent loop. Coordinates the LLM client, context manager,
tool dispatcher, prompt builder, and sentiment monitor into
a coherent conversation-driven reservation agent.

Model: llama3-groq-8b-8192-tool-use-preview (8B, Groq API)
"""

from __future__ import annotations

import json
import re
import uuid
from typing import AsyncGenerator

import structlog

from agent.llm_client import LLMClient
from agent.context_manager import ContextManager, ConversationState
from agent.prompt_builder import build_system_prompt, get_tool_schemas
from agent.tool_dispatcher import dispatch_all
from agent.sentiment_monitor import analyze_sentiment, check_prompt_injection

logger = structlog.get_logger(__name__)

# Maximum tool call rounds per user turn to prevent infinite loops
MAX_TOOL_ROUNDS = 5


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
                    yield event
                    return

            # ── Handle tool calls ──────────────────────────
            if tool_calls_received:
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
                    self.context.add_tool_result(
                        res["tool_call_id"], res["content"]
                    )

                    # Update state and booking based on result
                    self._process_tool_result(
                        tool_name, res["result"]
                    )

                # Loop continues — LLM needs to process tool results
                continue

            # ── Final answer (no tool call) ────────────────
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
                self.context.update_booking_state(
                    search_results=results_list,
                    restaurant_id=first.get("restaurant_id"),
                    restaurant_name=first.get("name"),
                )

        elif tool_name == "check_availability":
            if data.get("available"):
                self.context.update_booking_state(
                    hold_id=data.get("hold_id"),
                    available_slots=data.get("slots", []),
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
