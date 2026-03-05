"""
Module: tools/escalation.py
Responsibility: Implements the escalate_to_human tool — logs the escalation,
writes a structured handoff packet to disk, and returns a guest-facing message.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone


_URGENCY_SLA = {
    "low": "24 hours",
    "medium": "2 hours",
    "high": "15 minutes",
}

_REASON_ACTIONS = {
    "hostile": "Review tone; offer apology and compensation.",
    "complaint": "Pull up guest history; prepare service recovery.",
    "complex": "Route to events coordinator or manager on duty.",
    "out_of_scope": "Clarify scope and transfer to general support.",
}


def _recommend_action(reason: str) -> str:
    reason_lower = reason.lower()
    for key, action in _REASON_ACTIONS.items():
        if key in reason_lower:
            return action
    return "Review conversation context and respond appropriately."


async def escalate_to_human(params: dict) -> dict:
    """Escalate conversation to a human agent.

    Writes a handoff JSON file and returns a guest-facing message.
    """
    try:
        reason: str = params.get("reason", "")
        urgency_level: str = params.get("urgency_level", "medium")
        conversation_summary: str = params.get("conversation_summary", "")

        if not reason:
            return {
                "success": False,
                "data": None,
                "error": "reason is required",
                "error_code": "INVALID_INPUT",
            }

        if urgency_level not in ("low", "medium", "high"):
            return {
                "success": False,
                "data": None,
                "error": "urgency_level must be low, medium, or high",
                "error_code": "INVALID_INPUT",
            }

        escalation_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        handoff = {
            "escalation_id": escalation_id,
            "timestamp": timestamp,
            "urgency": urgency_level,
            "reason": reason,
            "summary": conversation_summary,
            "recommended_action": _recommend_action(reason),
        }

        # Persist handoff packet
        esc_dir = os.path.join("logs", "escalations")
        os.makedirs(esc_dir, exist_ok=True)
        filepath = os.path.join(esc_dir, f"{escalation_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(handoff, f, indent=2)

        sla = _URGENCY_SLA.get(urgency_level, "2 hours")

        return {
            "success": True,
            "data": {
                "escalation_id": escalation_id,
                "handoff": handoff,
                "guest_message": (
                    f"I'm connecting you with a team member who can better "
                    f"assist you. You'll hear from us within {sla}."
                ),
            },
            "error": None,
            "error_code": None,
        }

    except Exception as exc:
        return {
            "success": False,
            "data": None,
            "error": str(exc),
            "error_code": "DB_ERROR",
        }
