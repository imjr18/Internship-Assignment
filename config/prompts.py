"""
Module: config/prompts.py
Responsibility: Stores production LLM system prompts, tool JSON schemas
in the format expected by Llama 3.3 / Groq API tool calling, and any
other prompt templates.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are GoodFoods, a helpful and professional AI restaurant reservation "
    "assistant. You help guests find restaurants, check availability, make "
    "reservations, modify or cancel bookings, and join waitlists.\n\n"
    "Guidelines:\n"
    "- Always confirm details before making a reservation.\n"
    "- Never fabricate availability — always use the check_availability tool.\n"
    "- If a guest seems frustrated or the request is outside your scope, "
    "escalate to a human.\n"
    "- Be concise but warm. Use the guest's name when known.\n"
    "- When presenting options, highlight why each matches the guest's needs.\n"
)

ESCALATION_PROMPT = (
    "The user's request requires human assistance. Summarise the conversation "
    "so far and the reason for escalation."
)

# ---------------------------------------------------------------------------
# Tool JSON schemas — Llama 3.3 / Groq format
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_restaurants",
            "description": (
                "Search for restaurant recommendations matching the guest's "
                "preferences. Use this tool when a guest describes what kind "
                "of dining experience they want (e.g. cuisine, ambiance, "
                "dietary needs, location). Returns scored and ranked results "
                "with explanations. Do NOT use this for confirming a specific "
                "time slot — use check_availability for that."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural-language description of what the guest "
                            "is looking for, e.g. 'quiet romantic Italian "
                            "dinner with gluten-free options'."
                        ),
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests dining.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Desired date in YYYY-MM-DD format.",
                    },
                    "time": {
                        "type": "string",
                        "description": "Desired time in HH:MM (24-hour) format.",
                    },
                    "dietary_requirements": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": (
                            "List of dietary needs, e.g. "
                            "['vegan_friendly', 'gluten_free_kitchen']."
                        ),
                    },
                    "location_preference": {
                        "type": ["string", "null"],
                        "description": (
                            "Preferred neighborhood, e.g. 'Downtown', "
                            "'Harbor District'."
                        ),
                    },
                    "cuisine_preference": {
                        "type": ["string", "null"],
                        "description": (
                            "Preferred cuisine type, e.g. 'Italian', 'Japanese'."
                        ),
                    },
                    "ambiance_preferences": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": (
                            "List of desired ambiance tags, e.g. "
                            "['romantic', 'quiet', 'private_dining']."
                        ),
                    },
                },
                "required": ["query", "party_size", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "Check whether a specific restaurant has available tables "
                "for a given party size, date, and time. Use this AFTER "
                "search_restaurants has identified a candidate, or when the "
                "guest already knows which restaurant they want. Returns "
                "available table slots and creates a 3-minute hold."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {
                        "type": "string",
                        "description": "UUID of the restaurant to check.",
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format.",
                    },
                    "preferred_time": {
                        "type": "string",
                        "description": "Preferred time in HH:MM (24-hour).",
                    },
                    "duration_minutes": {
                        "type": ["integer", "null"],
                        "description": (
                            "Expected duration in minutes. Defaults to 90."
                        ),
                    },
                },
                "required": [
                    "restaurant_id",
                    "party_size",
                    "date",
                    "preferred_time",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reservation",
            "description": (
                "Confirm and create a reservation. Requires guest details "
                "and either a hold_id from check_availability or a "
                "restaurant_id + table_id. Idempotent: duplicate calls "
                "with the same idempotency_key return the existing booking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hold_id": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional. Reservation hold ID from "
                            "check_availability to convert to confirmed."
                        ),
                    },
                    "restaurant_id": {
                        "type": "string",
                        "description": "UUID of the restaurant.",
                    },
                    "table_id": {
                        "type": ["string", "null"],
                        "description": "UUID of the specific table.",
                    },
                    "guest_name": {
                        "type": "string",
                        "description": "Full name of the guest.",
                    },
                    "guest_email": {
                        "type": "string",
                        "description": "Guest email address.",
                    },
                    "guest_phone": {
                        "type": "string",
                        "description": "Guest phone number.",
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests.",
                    },
                    "reservation_datetime": {
                        "type": "string",
                        "description": (
                            "Full ISO-8601 datetime for the reservation, "
                            "e.g. '2026-04-01T19:00:00'."
                        ),
                    },
                    "special_requests": {
                        "type": ["string", "null"],
                        "description": "Any special requests from the guest.",
                    },
                    "idempotency_key": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional unique key to prevent duplicate "
                            "reservations. Auto-generated if not provided."
                        ),
                    },
                },
                "required": [
                    "restaurant_id",
                    "guest_name",
                    "guest_email",
                    "guest_phone",
                    "party_size",
                    "reservation_datetime",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_reservation",
            "description": (
                "Modify an existing confirmed reservation. Can change "
                "date/time, party size, or special requests. If changing "
                "date/time or party size, availability is re-checked."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": ["string", "null"],
                        "description": (
                            "UUID of the reservation. Provide either this "
                            "or confirmation_code."
                        ),
                    },
                    "confirmation_code": {
                        "type": ["string", "null"],
                        "description": (
                            "Human-readable confirmation code (e.g. GF-A7K2M9). "
                            "Provide either this or reservation_id."
                        ),
                    },
                    "changes": {
                        "type": "object",
                        "description": (
                            "Dict of fields to change. Supported keys: "
                            "new_datetime (ISO-8601), new_party_size (int), "
                            "new_special_requests (str)."
                        ),
                    },
                },
                "required": ["changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reservation",
            "description": (
                "Cancel an existing reservation. Releases the table slot "
                "and checks the waitlist for potential notifications. "
                "Cannot cancel an already-cancelled reservation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": ["string", "null"],
                        "description": (
                            "UUID of the reservation. Provide either this "
                            "or confirmation_code."
                        ),
                    },
                    "confirmation_code": {
                        "type": ["string", "null"],
                        "description": (
                            "Human-readable confirmation code. "
                            "Provide either this or reservation_id."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for cancellation.",
                    },
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_guest_history",
            "description": (
                "Retrieve a guest's profile and reservation history for "
                "personalisation. Use when a returning guest identifies "
                "themselves by email. Returns past bookings, preferences, "
                "and dietary restrictions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "guest_email": {
                        "type": "string",
                        "description": "Guest email address.",
                    },
                    "guest_id": {
                        "type": ["string", "null"],
                        "description": (
                            "Guest UUID. Provide either this or guest_email."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_waitlist",
            "description": (
                "Add a guest to the waitlist for a fully-booked restaurant. "
                "Use when check_availability returns no available tables "
                "and the guest wants to wait for a cancellation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {
                        "type": "string",
                        "description": "UUID of the restaurant.",
                    },
                    "guest_name": {
                        "type": "string",
                        "description": "Guest full name.",
                    },
                    "guest_email": {
                        "type": "string",
                        "description": "Guest email address.",
                    },
                    "guest_phone": {
                        "type": "string",
                        "description": "Guest phone number.",
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of guests.",
                    },
                    "preferred_datetime": {
                        "type": "string",
                        "description": "Desired ISO-8601 datetime.",
                    },
                },
                "required": [
                    "restaurant_id",
                    "guest_name",
                    "guest_email",
                    "guest_phone",
                    "party_size",
                    "preferred_datetime",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Escalate the conversation to a human agent. Use ONLY when: "
                "(1) the guest is hostile or abusive, (2) the request is "
                "complex and outside your capabilities (e.g. large event "
                "coordination, complaints about past visits), or (3) the "
                "guest explicitly asks for a human. Do NOT use for normal "
                "reservation tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": (
                            "Why the conversation is being escalated."
                        ),
                    },
                    "urgency_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": (
                            "Urgency: low (general inquiry), medium "
                            "(complaint), high (hostile/safety concern)."
                        ),
                    },
                    "conversation_summary": {
                        "type": "string",
                        "description": (
                            "Brief summary of the conversation so far "
                            "for the human agent."
                        ),
                    },
                },
                "required": [
                    "reason",
                    "urgency_level",
                    "conversation_summary",
                ],
            },
        },
    },
]
