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
from datetime import datetime, timedelta
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

    @staticmethod
    def _extract_party_size_from_text(text: str) -> int | None:
        """Extract explicit party size from user text."""
        lower = text.lower()
        word_to_num = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
        }

        # Short replies like "5" or "5 including me".
        m_standalone = re.fullmatch(
            r"\s*(\d{1,2})\s*(?:people|persons|guests|pax)?"
            r"(?:\s*(?:including|incl(?:uding)?|with)\s*(?:me|myself|us))?\s*",
            lower,
        )
        if m_standalone:
            size = int(m_standalone.group(1))
            if 1 <= size <= 24:
                return size

        m_standalone_word = re.fullmatch(
            r"\s*(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*"
            r"(?:people|persons|guests|pax)?"
            r"(?:\s*(?:including|incl(?:uding)?|with)\s*(?:me|myself|us))?\s*",
            lower,
        )
        if m_standalone_word:
            size = word_to_num[m_standalone_word.group(1)]
            if 1 <= size <= 24:
                return size

        # "with 4 of my friends" usually means the speaker + friends.
        m_with_friends_num = re.search(
            r"\b(?:with|bringing)\s+(\d{1,2})\s+(?:of\s+my\s+)?friends\b",
            lower,
        )
        if m_with_friends_num:
            size = int(m_with_friends_num.group(1)) + 1
            if 1 <= size <= 24:
                return size

        m_with_friends_word = re.search(
            r"\b(?:with|bringing)\s+"
            r"(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
            r"(?:of\s+my\s+)?friends\b",
            lower,
        )
        if m_with_friends_word:
            size = word_to_num[m_with_friends_word.group(1)] + 1
            if 1 <= size <= 24:
                return size

        m_me_and_friends_num = re.search(
            r"\b(?:me\s+and|myself\s+and)\s+(\d{1,2})\s+friends\b",
            lower,
        )
        if m_me_and_friends_num:
            size = int(m_me_and_friends_num.group(1)) + 1
            if 1 <= size <= 24:
                return size

        m_me_and_friends_word = re.search(
            r"\b(?:me\s+and|myself\s+and)\s+"
            r"(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+friends\b",
            lower,
        )
        if m_me_and_friends_word:
            size = word_to_num[m_me_and_friends_word.group(1)] + 1
            if 1 <= size <= 24:
                return size

        numeric_patterns = [
            r"\bfor\s+(\d{1,2})\s*(?:people|persons|guests|pax)?\b",
            r"\bparty\s+of\s+(\d{1,2})\b",
            r"\b(\d{1,2})\s*(?:people|persons|guests|pax)\b",
            r"\bwe\s+are\s+(\d{1,2})\b",
        ]
        for pattern in numeric_patterns:
            m = re.search(pattern, lower)
            if m:
                size = int(m.group(1))
                if 1 <= size <= 24:
                    return size

        word_patterns = [
            r"\bfor\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*(?:people|persons|guests|pax)?\b",
            r"\bparty\s+of\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*(?:people|persons|guests|pax)\b",
            r"\bwe\s+are\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
        ]
        for pattern in word_patterns:
            m = re.search(pattern, lower)
            if m:
                return word_to_num[m.group(1)]

        return None

    @staticmethod
    def _extract_time_24_from_text(text: str) -> str | None:
        """Extract preferred time as HH:MM (24h)."""
        lower = text.lower()

        # 24h forms like 19:30.
        m_24 = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lower)
        if m_24:
            hour = int(m_24.group(1))
            minute = int(m_24.group(2))
            return f"{hour:02d}:{minute:02d}"

        # 12h forms like 8 pm / 8:30pm.
        m_12 = re.search(r"\b(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*(am|pm)\b", lower)
        if m_12:
            hour = int(m_12.group(1))
            minute = int(m_12.group(2) or "00")
            meridiem = m_12.group(3)
            if meridiem == "pm" and hour != 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"

        # Coarse intent words.
        if "evening" in lower:
            return "19:00"
        if "dinner" in lower or "tonight" in lower:
            return "20:00"
        if "lunch" in lower:
            return "13:00"
        if "afternoon" in lower:
            return "15:00"
        if "morning" in lower:
            return "09:00"

        return None

    @staticmethod
    def _extract_date_iso_from_text(text: str) -> str | None:
        """Extract preferred date as YYYY-MM-DD."""
        lower = text.lower()
        now = datetime.now()

        # ISO date.
        m_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", lower)
        if m_iso:
            candidate = m_iso.group(1)
            try:
                datetime.fromisoformat(candidate)
                return candidate
            except ValueError:
                pass

        # Relative day words.
        if re.search(r"\btoday\b", lower):
            return now.strftime("%Y-%m-%d")
        if re.search(r"\b(tomorrow|tmrw)\b", lower):
            return (now + timedelta(days=1)).strftime("%Y-%m-%d")

        # Weekday references.
        weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        m_weekday = re.search(
            r"\b(?:(this|next)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            lower,
        )
        if m_weekday:
            prefix = m_weekday.group(1) or ""
            target_weekday = weekday_map[m_weekday.group(2)]
            days_ahead = (target_weekday - now.weekday()) % 7
            if prefix == "next":
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)
            return target_date.strftime("%Y-%m-%d")

        # "10th of march" / "march 10th".
        month_map = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        m_day_month = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?"
            r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
            lower,
        )
        m_month_day = re.search(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
            r"(\d{1,2})(?:st|nd|rd|th)?\b",
            lower,
        )

        day: int | None = None
        month: int | None = None
        if m_day_month:
            day = int(m_day_month.group(1))
            month = month_map[m_day_month.group(2)]
        elif m_month_day:
            month = month_map[m_month_day.group(1)]
            day = int(m_month_day.group(2))

        if day is not None and month is not None:
            for year in (now.year, now.year + 1):
                try:
                    candidate_dt = datetime(year, month, day)
                except ValueError:
                    return None
                if candidate_dt.date() >= now.date():
                    return candidate_dt.strftime("%Y-%m-%d")
            return datetime(now.year + 1, month, day).strftime("%Y-%m-%d")

        return None

    def _enrich_tool_arguments_from_state(self, tool_calls: list[dict]) -> None:
        """Fill missing tool arguments from known booking state."""
        state = self.context.get_booking_state()
        party_size = state.get("party_size")
        date_iso = state.get("date_iso")
        time_24 = state.get("time_24")
        date_explicit = bool(state.get("date_explicit"))
        time_explicit = bool(state.get("time_explicit"))
        restaurant_id = state.get("restaurant_id")
        reservation_id = state.get("reservation_id")
        confirmation_code = state.get("confirmation_code")

        for tool_call in tool_calls:
            name = str(tool_call.get("name", ""))
            args = tool_call.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}

            if (
                name in {"search_restaurants", "check_availability", "create_reservation"}
                and party_size is not None
                and "party_size" not in args
            ):
                args["party_size"] = party_size

            if name == "search_restaurants":
                if date_iso and (date_explicit or not args.get("date")):
                    args["date"] = date_iso
                if time_24 and (time_explicit or not args.get("time")):
                    args["time"] = time_24

            if name == "check_availability":
                if restaurant_id and not args.get("restaurant_id"):
                    args["restaurant_id"] = restaurant_id
                if date_iso and (date_explicit or not args.get("date")):
                    args["date"] = date_iso
                if time_24 and (time_explicit or not args.get("preferred_time")):
                    args["preferred_time"] = time_24

            if name == "modify_reservation":
                if reservation_id and not args.get("reservation_id"):
                    args["reservation_id"] = reservation_id
                if confirmation_code and not args.get("confirmation_code"):
                    args["confirmation_code"] = confirmation_code

            tool_call["arguments"] = args

    @staticmethod
    def _coerce_party_size(value: object) -> int | None:
        """Convert raw value to valid party size in [1, 24]."""
        if value is None:
            return None
        try:
            parsed = int(str(value).strip())
        except Exception:
            return None
        if 1 <= parsed <= 24:
            return parsed
        return None

    def _resolve_party_size_for_critical_tools(
        self,
        tool_calls: list[dict],
        latest_user_message: str,
    ) -> bool:
        """Ensure party size is available before critical tool execution.

        Returns True if a valid party size exists and has been propagated to
        critical tool calls; otherwise False.
        """
        critical_tools = {"search_restaurants", "check_availability", "create_reservation"}
        has_critical_tool = any(tc.get("name") in critical_tools for tc in tool_calls)
        if not has_critical_tool:
            return True

        state = self.context.get_booking_state()
        party_size = self._coerce_party_size(state.get("party_size"))

        if party_size is None:
            extracted = self._extract_party_size_from_text(latest_user_message or "")
            if extracted is not None:
                party_size = extracted
                self.context.update_booking_state(
                    party_size=party_size,
                    party_size_explicit=True,
                )

        if party_size is None:
            for tc in tool_calls:
                if tc.get("name") not in critical_tools:
                    continue
                args = tc.get("arguments") or {}
                if not isinstance(args, dict):
                    continue
                from_args = self._coerce_party_size(args.get("party_size"))
                if from_args is not None:
                    party_size = from_args
                    self.context.update_booking_state(
                        party_size=party_size,
                        # Mark explicit to prevent repeated guard loops.
                        party_size_explicit=True,
                    )
                    break

        if party_size is None:
            return False

        for tc in tool_calls:
            if tc.get("name") not in critical_tools:
                continue
            args = tc.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}
            if self._coerce_party_size(args.get("party_size")) is None:
                args["party_size"] = party_size
            tc["arguments"] = args

        return True

    @staticmethod
    def _has_modification_intent(text: str) -> bool:
        """Detect whether the user is trying to modify an existing reservation."""
        lower = text.lower()
        cues = (
            "modify",
            "change",
            "reschedule",
            "update",
            "move it",
            "move the booking",
            "change the date",
            "change the time",
        )
        return any(cue in lower for cue in cues)

    def _rewrite_create_to_modify_in_modification_mode(
        self,
        tool_calls: list[dict],
    ) -> None:
        """Prevent accidental new-booking flow when user is modifying reservation."""
        state = self.context.get_booking_state()
        if not state.get("modification_context_active"):
            return

        reservation_id = state.get("reservation_id")
        confirmation_code = state.get("confirmation_code")
        if not reservation_id and not confirmation_code:
            return

        date_iso = state.get("date_iso")
        time_24 = state.get("time_24")
        party_size_state = self._coerce_party_size(state.get("party_size"))

        for tc in tool_calls:
            if tc.get("name") != "create_reservation":
                continue

            args = tc.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}

            changes: dict[str, object] = {}

            # Prefer explicit datetime from tool args; fallback to booking state.
            raw_dt = args.get("reservation_datetime")
            if isinstance(raw_dt, str) and raw_dt:
                changes["new_datetime"] = raw_dt
            elif isinstance(date_iso, str) and isinstance(time_24, str) and date_iso and time_24:
                changes["new_datetime"] = f"{date_iso}T{time_24}:00"

            party_size_arg = self._coerce_party_size(args.get("party_size"))
            if party_size_arg is not None:
                changes["new_party_size"] = party_size_arg
            elif party_size_state is not None:
                changes["new_party_size"] = party_size_state

            new_special = args.get("special_requests")
            if isinstance(new_special, str) and new_special.strip():
                changes["new_special_requests"] = new_special.strip()

            # If we cannot infer any actual change, keep original call.
            if not changes:
                continue

            new_args: dict[str, object] = {"changes": changes}
            if reservation_id:
                new_args["reservation_id"] = reservation_id
            elif confirmation_code:
                new_args["confirmation_code"] = confirmation_code

            tc["name"] = "modify_reservation"
            tc["arguments"] = new_args

    def _has_explicit_modification_details(self, text: str) -> bool:
        """Return True only when user explicitly states new modification values."""
        lower = text.lower().strip()
        if not lower:
            return False

        # Explicit party-size update.
        if self._extract_party_size_from_text(text) is not None:
            return True

        # Explicit clock time.
        if re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", lower):
            return True
        if re.search(r"\b\d{1,2}:\d{2}\b", lower):
            return True

        # Explicit date clues.
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", lower):
            return True
        if re.search(
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b",
            lower,
        ):
            return True
        if re.search(r"\b(today|tomorrow|tonight|next\s+\w+day|this\s+\w+day)\b", lower):
            return True

        # Explicit request text update (not just "change it").
        request_keywords = (
            "special request",
            "window",
            "quiet",
            "outdoor",
            "indoor",
            "booth",
            "high chair",
            "birthday",
            "anniversary",
            "allergy",
        )
        if any(k in lower for k in request_keywords) and any(
            v in lower for v in ("change", "modify", "update", "set", "make", "add", "request")
        ):
            return True

        return False

    @staticmethod
    def _classify_confirmation_reply(text: str) -> str:
        """Classify short confirmation/cancel replies."""
        lower = text.lower().strip()
        if not lower:
            return "other"

        cancel_terms = (
            "cancel",
            "stop",
            "don't",
            "do not",
            "no",
            "not now",
            "leave it",
            "never mind",
        )
        if any(term in lower for term in cancel_terms):
            return "cancel"

        confirm_terms = (
            "yes",
            "yeah",
            "yep",
            "sure",
            "go ahead",
            "proceed",
            "confirm",
            "do it",
            "please do",
            "sounds good",
            "ok",
            "okay",
        )
        if any(term in lower for term in confirm_terms):
            return "confirm"

        return "other"

    def _summarize_modify_arguments(self, args: dict) -> str:
        """Build a user-facing summary for pending reservation changes."""
        if not isinstance(args, dict):
            return "the requested update"

        changes = args.get("changes") or {}
        if not isinstance(changes, dict):
            return "the requested update"

        summary_parts: list[str] = []

        new_datetime = changes.get("new_datetime")
        if isinstance(new_datetime, str) and new_datetime:
            date_str, time_str = self._reservation_datetime_to_booking_fields(new_datetime)
            if date_str and time_str:
                summary_parts.append(f"{date_str} at {time_str}")
            elif date_str:
                summary_parts.append(date_str)

        new_party_size = self._coerce_party_size(changes.get("new_party_size"))
        if new_party_size is not None:
            summary_parts.append(f"for {new_party_size} guests")

        new_special = changes.get("new_special_requests")
        if isinstance(new_special, str) and new_special.strip():
            summary_parts.append(f"special requests: {new_special.strip()}")

        if not summary_parts:
            return "the requested update"
        return "; ".join(summary_parts)

    async def _execute_pending_modification(
        self, pending_args: dict
    ) -> AsyncGenerator[dict, None]:
        """Execute a previously confirmed modify_reservation call."""
        tool_call = {
            "id": f"pending-modify-{uuid.uuid4().hex[:8]}",
            "name": "modify_reservation",
            "arguments": pending_args,
        }

        tc_for_context = [{
            "id": tool_call["id"],
            "type": "function",
            "function": {
                "name": "modify_reservation",
                "arguments": json.dumps(pending_args),
            },
        }]
        self.context.add_assistant_message(None, tc_for_context)

        yield {
            "type": "tool_start",
            "tool_name": "modify_reservation",
            "arguments": pending_args,
        }

        results = await dispatch_all([tool_call], self.session_id)
        result_payload = (
            results[0].get("result", {})
            if results and isinstance(results[0], dict)
            else {"success": False, "error": "modify_dispatch_failed"}
        )

        yield {
            "type": "tool_result",
            "tool_name": "modify_reservation",
            "result": result_payload,
        }

        compact = self._compact_tool_result_for_context("modify_reservation", result_payload)
        self.context.add_tool_result(tool_call["id"], compact)
        self._process_tool_result("modify_reservation", result_payload)

        response = self._build_fast_tool_response(
            [tool_call],
            [{"result": result_payload}],
        )
        if not response:
            if result_payload.get("success"):
                response = "Done - I have updated your reservation."
            else:
                response = "I couldn't apply that change yet. Please share the new details and I'll try again."

        self.context.add_assistant_message(response)
        yield {"type": "token", "content": response}
        yield {"type": "done", "final_content": response}

    @staticmethod
    def _latest_user_message(messages: list[dict]) -> str:
        """Return latest user message from context list."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return str(msg.get("content", ""))
        return ""

    @staticmethod
    def _normalize_match_text(text: str) -> str:
        """Normalize text for lightweight restaurant-name matching."""
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _capture_presented_option_selection(self, user_message: str) -> bool:
        """Capture explicit option selection while options are on screen."""
        if self.context.get_conversation_state() != ConversationState.PRESENTING_OPTIONS:
            return False

        booking = self.context.get_booking_state()
        raw_options = booking.get("search_results", [])
        if not isinstance(raw_options, list) or not raw_options:
            return False
        options = [opt for opt in raw_options[:3] if isinstance(opt, dict)]
        if not options:
            return False

        lower = user_message.lower()
        selected: dict | None = None

        ordinal_map = {
            0: (r"\b(first|1st)\b",),
            1: (r"\b(second|2nd)\b",),
            2: (r"\b(third|3rd)\b",),
        }
        for idx, patterns in ordinal_map.items():
            if idx >= len(options):
                continue
            if any(re.search(pattern, lower) for pattern in patterns):
                selected = options[idx]
                break

        if selected is None:
            numeric_choice = re.search(r"\b(?:option|number|#)\s*([1-3])\b", lower)
            if numeric_choice:
                idx = int(numeric_choice.group(1)) - 1
                if 0 <= idx < len(options):
                    selected = options[idx]

        if selected is None:
            normalized_user = self._normalize_match_text(user_message)
            candidates: list[tuple[int, dict]] = []
            for option in options:
                name = str(option.get("name", "")).strip()
                normalized_name = self._normalize_match_text(name)
                if normalized_name and normalized_name in normalized_user:
                    candidates.append((len(normalized_name), option))
            if candidates:
                candidates.sort(key=lambda item: item[0], reverse=True)
                selected = candidates[0][1]

        if selected is None:
            return False

        updates: dict = {"restaurant_selected_explicit": True}
        if selected.get("restaurant_id"):
            updates["restaurant_id"] = selected["restaurant_id"]
        if selected.get("name"):
            updates["restaurant_name"] = selected["name"]
        self.context.update_booking_state(**updates)
        return True

    def _try_handle_option_ranking_query(self, user_message: str) -> str | None:
        """Deterministic answer for best-option queries to avoid repetitive LLM loops."""
        if self.context.get_conversation_state() != ConversationState.PRESENTING_OPTIONS:
            return None

        lower = user_message.lower()
        ranking_cues = ("best", "good food", "highest rated", "top option", "quietest")
        proximity_cues = ("closest", "near", "nearest")
        asks_downtown_proximity = "downtown" in lower and any(cue in lower for cue in proximity_cues)
        if not any(cue in lower for cue in ranking_cues) and not asks_downtown_proximity:
            return None

        booking = self.context.get_booking_state()
        options = booking.get("search_results", [])
        if not isinstance(options, list) or not options:
            return None

        if asks_downtown_proximity:
            distance_rank = {
                "downtown": 0,
                "midtown": 1,
                "west end": 2,
                "harbor district": 2,
                "east village": 3,
                "university quarter": 4,
            }

            def _proximity_key(item: dict) -> tuple[int, float]:
                neighborhood = str(item.get("neighborhood", "")).lower().strip()
                rank = distance_rank.get(neighborhood, 5)
                try:
                    score = float(item.get("score", 0.0) or 0.0)
                except Exception:
                    score = 0.0
                return rank, -score

            best_by_distance = min(options[:3], key=_proximity_key)
            chosen_name = best_by_distance.get("name", "that option")
            chosen_hood = best_by_distance.get("neighborhood", "its area")
            selection_updates = {
                "restaurant_name": chosen_name,
                "restaurant_selected_explicit": True,
            }
            if best_by_distance.get("restaurant_id"):
                selection_updates["restaurant_id"] = best_by_distance.get("restaurant_id")
            self.context.update_booking_state(**selection_updates)
            return (
                f"Great question - {chosen_name} is the closest to Downtown among these options "
                f"({chosen_hood}). Want me to check availability there?"
            )

        def _score(item: dict) -> float:
            try:
                return float(item.get("score", 0.0) or 0.0)
            except Exception:
                return 0.0

        best = max(options[:3], key=_score)
        best_name = best.get("name", "the top option")
        selection_updates = {
            "restaurant_name": best_name,
            "restaurant_selected_explicit": True,
        }
        if best.get("restaurant_id"):
            selection_updates["restaurant_id"] = best.get("restaurant_id")
        self.context.update_booking_state(**selection_updates)
        if "quiet" in lower:
            return (
                f"I don't have live noise data, but {best_name} is the strongest match. "
                "Want me to check availability there?"
            )
        return (
            f"{best_name} looks like the strongest match from these results. "
            "Want me to check availability there?"
        )

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
        parsed_party_size = self._extract_party_size_from_text(user_message)
        parsed_date_iso = self._extract_date_iso_from_text(user_message)
        parsed_time_24 = self._extract_time_24_from_text(user_message)

        booking_updates: dict = {}
        if parsed_party_size is not None:
            booking_updates["party_size"] = parsed_party_size
            booking_updates["party_size_explicit"] = True
        if parsed_date_iso is not None:
            booking_updates["date_iso"] = parsed_date_iso
            booking_updates["date"] = parsed_date_iso
            booking_updates["date_explicit"] = True
        if parsed_time_24 is not None:
            booking_updates["time_24"] = parsed_time_24
            booking_updates["time"] = parsed_time_24
            booking_updates["time_explicit"] = True
        if booking_updates:
            self.context.update_booking_state(**booking_updates)

        booking_state = self.context.get_booking_state()
        if self._has_modification_intent(user_message) and (
            booking_state.get("reservation_id") or booking_state.get("confirmation_code")
        ):
            self.context.update_booking_state(modification_context_active=True)
            if self.context.get_conversation_state() != ConversationState.ESCALATED:
                self.context.set_conversation_state(ConversationState.MODIFYING)

        pending_modify = booking_state.get("pending_modify_awaiting_confirm")
        pending_args = booking_state.get("pending_modify_args")
        if pending_modify and isinstance(pending_args, dict):
            # If user provided a new explicit change, replace pending request.
            if self._has_explicit_modification_details(user_message):
                self.context.update_booking_state(
                    pending_modify_awaiting_confirm=False,
                    pending_modify_args=None,
                    pending_modify_summary=None,
                )
            else:
                decision = self._classify_confirmation_reply(user_message)
                if decision == "confirm":
                    self.context.update_booking_state(
                        pending_modify_awaiting_confirm=False,
                        pending_modify_summary=None,
                    )
                    async for event in self._execute_pending_modification(pending_args):
                        yield event
                    return
                if decision == "cancel":
                    cancel_msg = "No problem - I have not changed your reservation."
                    self.context.update_booking_state(
                        pending_modify_awaiting_confirm=False,
                        pending_modify_args=None,
                        pending_modify_summary=None,
                    )
                    self.context.add_assistant_message(cancel_msg)
                    yield {"type": "token", "content": cancel_msg}
                    yield {"type": "done", "final_content": cancel_msg}
                    return

                remind_msg = (
                    "Please confirm if you want me to apply that change, "
                    "or tell me new details to update."
                )
                self.context.add_assistant_message(remind_msg)
                yield {"type": "token", "content": remind_msg}
                yield {"type": "done", "final_content": remind_msg}
                return

        self._capture_presented_option_selection(user_message)

        deterministic_option_answer = self._try_handle_option_ranking_query(user_message)
        if deterministic_option_answer:
            self.context.add_assistant_message(deterministic_option_answer)
            yield {"type": "token", "content": deterministic_option_answer}
            yield {"type": "done", "final_content": deterministic_option_answer}
            return

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
                           ("<function=", "</function>", "<function>", "<function")):
                        _function_detected = True
                    # Only yield tokens if we haven't detected function syntax
                    if not _function_detected:
                        token_text = str(event.get("content", ""))
                        # Drop partial function-tag fragments that can leak into UI
                        # during streamed tool-call generation.
                        if re.fullmatch(r"\s*<\s*/?\s*fun\w*\s*", token_text, re.IGNORECASE):
                            continue
                        if token_text.strip() in {"<", "</", "</function>"}:
                            continue
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
                self._enrich_tool_arguments_from_state(tool_calls_received)
                self._rewrite_create_to_modify_in_modification_mode(tool_calls_received)
                latest_user = self._latest_user_message(messages)
                if not self._resolve_party_size_for_critical_tools(
                    tool_calls_received,
                    latest_user,
                ):
                    ask_size = "Before I proceed, how many people are in your party?"
                    self.context.add_assistant_message(ask_size)
                    yield {"type": "token", "content": ask_size}
                    yield {"type": "done", "final_content": ask_size}
                    return

                if any(tc.get("name") == "modify_reservation" for tc in tool_calls_received):
                    if not self._has_explicit_modification_details(latest_user):
                        ask_change = (
                            "Sure - what would you like to change: new time/date, "
                            "party size, or special requests?"
                        )
                        self.context.add_assistant_message(ask_change)
                        yield {"type": "token", "content": ask_change}
                        yield {"type": "done", "final_content": ask_change}
                        return

                    modify_call = next(
                        (
                            tc for tc in tool_calls_received
                            if tc.get("name") == "modify_reservation"
                        ),
                        None,
                    )
                    if modify_call:
                        modify_args = modify_call.get("arguments") or {}
                        if not isinstance(modify_args, dict):
                            modify_args = {}
                        summary = self._summarize_modify_arguments(modify_args)
                        self.context.update_booking_state(
                            pending_modify_awaiting_confirm=True,
                            pending_modify_args=modify_args,
                            pending_modify_summary=summary,
                        )
                        ask_confirm = (
                            f"I can update your reservation to {summary}. "
                            "Please confirm and I will apply this change."
                        )
                        self.context.add_assistant_message(ask_confirm)
                        yield {"type": "token", "content": ask_confirm}
                        yield {"type": "done", "final_content": ask_confirm}
                        return

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
                cleaned = self._sanitize_assistant_text(round_content)
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
                check_updates = {
                    "hold_id": data.get("hold_id"),
                    "available_slots": compact_slots,
                }
                if data.get("slots"):
                    slot = data["slots"][0]
                    slot_date, slot_time = self._reservation_datetime_to_booking_fields(
                        slot.get("datetime", "")
                    )
                    slot_date_iso, slot_time_24 = self._reservation_datetime_to_iso_fields(
                        slot.get("datetime", "")
                    )
                    check_updates.update(
                        {
                            "table_id": slot.get("table_id"),
                            "date": slot_date,
                            "time": slot_time,
                            "date_iso": slot_date_iso,
                            "time_24": slot_time_24,
                        }
                    )
                filtered_check = {k: v for k, v in check_updates.items() if v is not None}
                if filtered_check:
                    self.context.update_booking_state(**filtered_check)
                if self.context.get_booking_state().get("modification_context_active"):
                    self.context.set_conversation_state(ConversationState.MODIFYING)

        elif tool_name == "create_reservation":
            res = data.get("reservation", {})
            date_str, time_str = self._reservation_datetime_to_booking_fields(
                res.get("reservation_datetime", "")
            )
            date_iso, time_24 = self._reservation_datetime_to_iso_fields(
                res.get("reservation_datetime", "")
            )
            updates = {
                "reservation_id": res.get("id"),
                "confirmation_code": res.get("confirmation_code"),
                "restaurant_id": res.get("restaurant_id"),
                "restaurant_name": (
                    data.get("restaurant_name")
                    or self.context.get_booking_state().get("restaurant_name")
                ),
                "party_size": res.get("party_size"),
                "special_requests": res.get("special_requests"),
                "date": date_str,
                "time": time_str,
                "date_iso": date_iso,
                "time_24": time_24,
            }
            filtered = {k: v for k, v in updates.items() if v is not None}
            if filtered:
                self.context.update_booking_state(**filtered)
            self.context.update_booking_state(modification_context_active=False)

        elif tool_name == "modify_reservation":
            res = data.get("reservation", {})
            date_str, time_str = self._reservation_datetime_to_booking_fields(
                res.get("reservation_datetime", "")
            )
            date_iso, time_24 = self._reservation_datetime_to_iso_fields(
                res.get("reservation_datetime", "")
            )
            updates = {
                "reservation_id": res.get("id"),
                "confirmation_code": (
                    res.get("confirmation_code")
                    or self.context.get_booking_state().get("confirmation_code")
                ),
                "restaurant_id": res.get("restaurant_id"),
                "restaurant_name": (
                    data.get("restaurant_name")
                    or self.context.get_booking_state().get("restaurant_name")
                ),
                "party_size": res.get("party_size"),
                "special_requests": res.get("special_requests"),
                "date": date_str,
                "time": time_str,
                "date_iso": date_iso,
                "time_24": time_24,
            }
            filtered = {k: v for k, v in updates.items() if v is not None}
            if filtered:
                self.context.update_booking_state(**filtered)
            self.context.update_booking_state(
                modification_context_active=False,
                pending_modify_awaiting_confirm=False,
                pending_modify_args=None,
                pending_modify_summary=None,
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
            lines = ["Great choice - here are the best matches I found:"]
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
                        f"Great news - {restaurant_name} has availability at {slot_text}. "
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
                return f"Wonderful - your reservation is confirmed. Confirmation code: {code}."
            return "Wonderful - your reservation is confirmed."

        if tool_name == "modify_reservation":
            if not success:
                error_code = result.get("error_code")
                if error_code == "INVALID_INPUT":
                    return (
                        "Sure. What would you like to change: date/time, "
                        "party size, or special requests?"
                    )
                if error_code == "UNAVAILABLE":
                    return (
                        "That updated slot is not available. Share another "
                        "time and I'll check alternatives."
                    )
                if error_code == "NOT_FOUND":
                    return (
                        "I couldn't find that reservation. Please share your "
                        "confirmation code so I can locate it."
                    )
                return (
                    "I couldn't apply that change yet. Tell me what details "
                    "you want to update and I'll try again."
                )

            reservation = data.get("reservation", {})
            date_str, time_str = self._reservation_datetime_to_booking_fields(
                reservation.get("reservation_datetime", "")
            )
            party_size = reservation.get("party_size")
            special = reservation.get("special_requests")

            summary_parts: list[str] = []
            if date_str and time_str:
                summary_parts.append(f"{date_str} at {time_str}")
            elif date_str:
                summary_parts.append(date_str)
            if party_size:
                summary_parts.append(f"for {party_size} guests")
            if special:
                summary_parts.append(f"special requests: {special}")

            if summary_parts:
                return "Done - your reservation has been updated: " + "; ".join(summary_parts) + "."
            return "Done - your reservation has been updated."

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
    def _sanitize_assistant_text(text: str) -> str:
        """Remove malformed function-call text that may leak from the 8B model."""
        cleaned = re.sub(
            r"<function=\w+[^>]*>.*?</function>",
            "",
            text,
            flags=re.DOTALL,
        )
        cleaned = re.sub(
            r"</function>\w+>.*?</function>",
            "",
            cleaned,
            flags=re.DOTALL,
        )
        cleaned = re.sub(r"</?function[^>]*>", "", cleaned)
        # Remove incomplete trailing fragments such as "<function" or "<fun".
        cleaned = re.sub(r"<\s*/?\s*function[^ \n\r\t>]*\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<\s*fun\w*\s*$", "", cleaned, flags=re.IGNORECASE)
        # Remove stray trailing angle bracket artifacts from interrupted tool syntax.
        cleaned = re.sub(r"<\s*$", "", cleaned)
        return cleaned.strip()

    @staticmethod
    def _reservation_datetime_to_booking_fields(
        reservation_datetime: str,
    ) -> tuple[str | None, str | None]:
        """Convert ISO reservation datetime to UI-friendly date/time strings."""
        if not reservation_datetime:
            return None, None
        try:
            dt = datetime.fromisoformat(reservation_datetime)
        except ValueError:
            try:
                dt = datetime.fromisoformat(reservation_datetime.replace("Z", "+00:00"))
            except ValueError:
                return None, None

        hour = dt.strftime("%I").lstrip("0") or "12"
        date_str = dt.strftime("%a, %b %d")
        time_str = f"{hour}:{dt.strftime('%M %p')}"
        return date_str, time_str

    @staticmethod
    def _reservation_datetime_to_iso_fields(
        reservation_datetime: str,
    ) -> tuple[str | None, str | None]:
        """Convert ISO reservation datetime to canonical YYYY-MM-DD/HH:MM fields."""
        if not reservation_datetime:
            return None, None
        try:
            dt = datetime.fromisoformat(reservation_datetime)
        except ValueError:
            try:
                dt = datetime.fromisoformat(reservation_datetime.replace("Z", "+00:00"))
            except ValueError:
                return None, None
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

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
