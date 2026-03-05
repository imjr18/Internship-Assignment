"""
Module: tools/guest_profiles.py
Responsibility: Implements the get_guest_history tool — retrieves a guest's
profile and last 10 reservations for agent personalisation.
"""

from __future__ import annotations

from database.queries import get_or_create_guest, get_guest_history as db_guest_history
from database.connection import get_db


async def get_guest_history(params: dict) -> dict:
    """Retrieve guest profile + last 10 reservations.

    Accepts guest_email or guest_id.
    """
    try:
        guest_email: str = params.get("guest_email", "")
        guest_id: str = params.get("guest_id", "")

        if not guest_email and not guest_id:
            return {
                "success": False,
                "data": None,
                "error": "guest_email or guest_id is required",
                "error_code": "INVALID_INPUT",
            }

        guest = None
        if guest_email:
            async with get_db() as db:
                cur = await db.execute(
                    "SELECT * FROM guests WHERE email = ?", (guest_email,)
                )
                row = await cur.fetchone()
                if row:
                    guest = dict(row)
        elif guest_id:
            async with get_db() as db:
                cur = await db.execute(
                    "SELECT * FROM guests WHERE id = ?", (guest_id,)
                )
                row = await cur.fetchone()
                if row:
                    guest = dict(row)

        if guest is None:
            return {
                "success": False,
                "data": None,
                "error": "Guest not found",
                "error_code": "NOT_FOUND",
            }

        history = await db_guest_history(guest["id"])

        return {
            "success": True,
            "data": {
                "guest": {
                    "id": guest["id"],
                    "name": guest.get("name", ""),
                    "email": guest.get("email", ""),
                    "phone": guest.get("phone", ""),
                    "dietary_restrictions": guest.get("dietary_restrictions", "[]"),
                    "preferences": guest.get("preferences", "{}"),
                    "visit_count": guest.get("visit_count", 0),
                    "lifetime_value": guest.get("lifetime_value", 0.0),
                },
                "reservations": history[:10],
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
