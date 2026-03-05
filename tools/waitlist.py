"""
Module: tools/waitlist.py
Responsibility: Implements the add_to_waitlist tool — registers a guest on
the waitlist and returns estimated position and wait time.
"""

from __future__ import annotations

from database.connection import get_db
from database.queries import (
    get_restaurant_by_id,
    get_or_create_guest,
    add_to_waitlist as db_add_to_waitlist,
)

# Hardcoded historical no-show rate
_NO_SHOW_RATE = 0.15
# Average reservation duration for wait-time estimation (minutes)
_AVG_DURATION = 90


async def add_to_waitlist(params: dict) -> dict:
    """Add a guest to a restaurant waitlist.

    Returns position, estimated wait, and confirmation.
    """
    try:
        restaurant_id: str = params.get("restaurant_id", "")
        guest_name: str = params.get("guest_name", "")
        guest_email: str = params.get("guest_email", "")
        guest_phone: str = params.get("guest_phone", "")
        party_size: int = params.get("party_size", 0)
        preferred_datetime: str = params.get("preferred_datetime", "")

        # --- Validation ---
        if not restaurant_id or not guest_email or not guest_name:
            return {
                "success": False,
                "data": None,
                "error": "restaurant_id, guest_name, and guest_email are required",
                "error_code": "INVALID_INPUT",
            }
        if party_size <= 0:
            return {
                "success": False,
                "data": None,
                "error": "party_size must be > 0",
                "error_code": "INVALID_INPUT",
            }

        # Restaurant exists?
        restaurant = await get_restaurant_by_id(restaurant_id)
        if restaurant is None:
            return {
                "success": False,
                "data": None,
                "error": f"Restaurant {restaurant_id} not found",
                "error_code": "NOT_FOUND",
            }

        # Upsert guest
        guest = await get_or_create_guest(guest_email, guest_name, guest_phone)

        # Add to waitlist
        entry = await db_add_to_waitlist(
            restaurant_id=restaurant_id,
            guest_id=guest["id"],
            party_size=party_size,
            preferred_datetime=preferred_datetime,
        )

        # Calculate position
        async with get_db() as db:
            cur = await db.execute(
                """
                SELECT COUNT(*) FROM waitlist
                WHERE restaurant_id = ?
                  AND status = 'waiting'
                  AND added_at <= ?
                """,
                (restaurant_id, entry["added_at"]),
            )
            (position,) = await cur.fetchone()

        # Estimated wait: position * avg_duration * (1 - no_show_rate)
        est_wait_min = int(position * _AVG_DURATION * (1 - _NO_SHOW_RATE))

        return {
            "success": True,
            "data": {
                "waitlist_id": entry["id"],
                "restaurant_name": restaurant["name"],
                "position": position,
                "estimated_wait_minutes": est_wait_min,
                "message": (
                    f"You are #{position} on the waitlist for "
                    f"{restaurant['name']}. Estimated wait: ~{est_wait_min} min."
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
