"""
Module: agent/llm_client.py

Wraps Groq API for llama-3.1-8b-instant.
All parsing logic derived from scripts/groq_api_reference.txt.

MODEL: llama-3.1-8b-instant
- 8B parameters (Llama 3.1 family)
- Groq API inference (no local GPU needed)
- Production-grade model replacing deprecated tool-use preview
- Compensated by explicit few-shot prompting
  and strategic use of tool_choice="required"
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncGenerator

from groq import AsyncGroq
import structlog

logger = structlog.get_logger(__name__)

MODEL = "llama-3.1-8b-instant"


class LLMClient:
    """Async wrapper around Groq chat completions with tool-call parsing."""

    def __init__(self):
        self.client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
        self.model = MODEL

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        session_id: str,
        force_tool_call: bool = False,
    ) -> dict:
        """Non-streaming completion.

        Args:
            messages: Chat history in OpenAI format.
            tools: Tool schemas.
            session_id: For structured logging.
            force_tool_call: Currently disabled for llama-3.1-8b-instant
                because tool_choice='required' produces malformed calls.
                Always uses 'auto' with strong prompting instead.

        Returns:
            {
                "type": "tool_call" | "final_answer",
                "content": str | None,
                "tool_calls": list[dict] | None,
                "finish_reason": str
            }
        """
        # NOTE: tool_choice="required" is unreliable with llama-3.1-8b-instant
        # It produces malformed <function=...> syntax. Always use "auto".
        tool_choice = "auto"

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice=tool_choice if tools else None,
                max_tokens=1000,
            )

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            logger.debug(
                "llm_response",
                session_id=session_id,
                finish_reason=finish_reason,
                has_tool_calls=bool(message.tool_calls),
                force_tool_call=force_tool_call,
                content_preview=(message.content or "")[:50],
            )

            if message.tool_calls:
                parsed_calls = []
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        logger.warning(
                            "tool_call_json_parse_error",
                            session_id=session_id,
                            raw=tc.function.arguments,
                        )
                        args = {}

                    parsed_calls.append(
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": args,
                        }
                    )

                return {
                    "type": "tool_call",
                    "content": message.content,
                    "tool_calls": parsed_calls,
                    "finish_reason": finish_reason,
                }

            return {
                "type": "final_answer",
                "content": message.content or "",
                "tool_calls": None,
                "finish_reason": finish_reason,
            }

        except Exception as e:
            error_str = str(e)
            # Handle malformed tool calls from 8B model
            # Groq returns tool_use_failed when the model generates
            # <function=...> syntax instead of proper JSON tool calls.
            # Retry without tools to get a natural language response.
            if "tool_use_failed" in error_str or "tool call validation" in error_str:
                logger.warning(
                    "tool_use_failed_retry",
                    session_id=session_id,
                    error=error_str[:100],
                )
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=1000,
                    )
                    message = response.choices[0].message
                    return {
                        "type": "final_answer",
                        "content": message.content or "",
                        "tool_calls": None,
                        "finish_reason": response.choices[0].finish_reason,
                    }
                except Exception as retry_err:
                    logger.error(
                        "retry_failed",
                        session_id=session_id,
                        error=str(retry_err),
                    )
                    raise retry_err from e

            logger.error(
                "llm_api_error",
                session_id=session_id,
                error=error_str,
                error_type=type(e).__name__,
            )
            raise

    async def stream_complete(
        self,
        messages: list[dict],
        tools: list[dict],
        session_id: str,
        force_tool_call: bool = False,
    ) -> AsyncGenerator[dict, None]:
        """Streaming completion.

        Yields:
            {"type": "token", "content": str}
            {"type": "tool_call", "tool_calls": list[dict]}
            {"type": "done", "finish_reason": str}
            {"type": "error", "error": str}

        NOTE on 8B streaming behavior:
        Tool calls and text tokens are mutually exclusive in one
        response. Tool call chunks arrive with empty content.
        Accumulate all tool call chunks before parsing arguments.
        """
        # NOTE: tool_choice="required" is unreliable with llama-3.1-8b-instant
        # It produces malformed <function=...> syntax. Always use "auto".
        tool_choice = "auto"

        max_retries = 3
        retry_delays = [5, 15, 30]  # seconds

        for attempt in range(max_retries + 1):
            accumulated_tool_calls: list[dict] = []
            finish_reason = None

            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice=tool_choice if tools else None,
                    max_tokens=1000,
                    stream=True,
                )

                async for chunk in stream:
                    choice = chunk.choices[0]
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                    delta = choice.delta

                    if delta.content:
                        yield {"type": "token", "content": delta.content}

                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            while len(accumulated_tool_calls) <= idx:
                                accumulated_tool_calls.append(
                                    {"id": "", "name": "", "arguments": ""}
                                )
                            if tc_chunk.id:
                                accumulated_tool_calls[idx]["id"] = tc_chunk.id
                            if tc_chunk.function.name:
                                accumulated_tool_calls[idx][
                                    "name"
                                ] = tc_chunk.function.name
                            if tc_chunk.function.arguments:
                                accumulated_tool_calls[idx][
                                    "arguments"
                                ] += tc_chunk.function.arguments

                # After stream ends — emit accumulated tool calls
                if accumulated_tool_calls:
                    parsed = []
                    for tc in accumulated_tool_calls:
                        try:
                            args = json.loads(tc["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        parsed.append(
                            {
                                "id": tc["id"],
                                "name": tc["name"],
                                "arguments": args,
                            }
                        )
                    yield {"type": "tool_call", "tool_calls": parsed}

                yield {"type": "done", "finish_reason": finish_reason}
                return  # Success — exit retry loop

            except Exception as e:
                error_str = str(e)
                is_rate_limit = "429" in error_str or "rate_limit" in error_str
                is_validation_error = (
                    "validation failed" in error_str.lower()
                    or "failed to call a function" in error_str.lower()
                )

                if is_rate_limit and attempt < max_retries:
                    delay = retry_delays[attempt]
                    logger.warning(
                        "rate_limit_retry",
                        session_id=session_id,
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    # Notify frontend about the wait
                    yield {
                        "type": "token",
                        "content": f"\n\n*Rate limit reached. Retrying in {delay}s...*\n\n",
                    }
                    await asyncio.sleep(delay)
                    continue  # Retry

                if is_validation_error and attempt < max_retries:
                    logger.warning(
                        "tool_validation_retry",
                        session_id=session_id,
                        attempt=attempt + 1,
                        error=error_str[:200],
                    )
                    # On validation error, retry without tools so the
                    # model falls back to a text response
                    try:
                        fallback_stream = await self.client.chat.completions.create(
                            model=self.model,
                            messages=messages,
                            stream=True,
                            max_tokens=1024,
                        )
                        async for chunk in fallback_stream:
                            if chunk.choices:
                                delta = chunk.choices[0].delta
                                if delta.content:
                                    yield {"type": "token", "content": delta.content}
                        yield {"type": "done", "finish_reason": "stop"}
                        return
                    except Exception as fallback_err:
                        logger.error(
                            "tool_validation_fallback_error",
                            session_id=session_id,
                            error=str(fallback_err),
                        )
                        # Fall through to the original error handler

                logger.error(
                    "llm_stream_error", session_id=session_id, error=error_str
                )
                yield {"type": "error", "error": error_str}
