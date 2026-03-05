"""
Module: tools/reservations.py
Responsibility: Implements create_reservation, modify_reservation, and
cancel_reservation tools with idempotency, hold conversion, and
waitlist notification triggers.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from database.queries import (
    create_reservation as db_create_reservation,
    get_reservation_by_id,
    get_reservation_by_confirmation_code,
    update_reservation_status,
    cancel_reservation as db_cancel_reservation,
    get_or_create_guest,
    get_restaurant_by_id,
    check_table_availability,
)
from database.connection import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_idempotency_key(email: str, restaurant_id: str, dt: str) -> str:
    """Deterministic key from guest_email + restaurant_id + datetime."""
    raw = f"{email}|{restaurant_id}|{dt}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# create_reservation
# ---------------------------------------------------------------------------

async def create_reservation(params: dict) -> dict:
    """Create (or return existing) reservation. Supports hold conversion."""
    try:
        hold_id: str | None = params.get("hold_id")
        restaurant_id: str = params.get("restaurant_id", "")
        table_id: str = params.get("table_id", "")
        guest_name: str = params.get("guest_name", "")
        guest_email: str = params.get("guest_email", "")
        guest_phone: str = params.get("guest_phone", "")
        party_size: int = params.get("party_size", 0)
        reservation_datetime: str = params.get("reservation_datetime", "")
        special_requests: str = params.get("special_requests", "")
        idempotency_key: str = params.get("idempotency_key", "")

        # --- Validate required fields ---
        if not guest_email or not guest_name or not restaurant_id:
            return {
                "success": False,
                "data": None,
                "error": "guest_name, guest_email, and restaurant_id are required",
                "error_code": "INVALID_INPUT",
            }
        if party_size <= 0:
            return {
                "success": False,
                "data": None,
                "error": "party_size must be > 0",
                "error_code": "INVALID_INPUT",
            }

        # --- Restaurant check ---
        restaurant = await get_restaurant_by_id(restaurant_id)
        if restaurant is None:
            return {
                "success": False,
                "data": None,
                "error": f"Restaurant {restaurant_id} not found",
                "error_code": "NOT_FOUND",
            }

        # --- Guest upsert ---
        guest = await get_or_create_guest(guest_email, guest_name, guest_phone)

        # --- Hold conversion path ---
        if hold_id:
            hold = await get_reservation_by_id(hold_id)
            if hold is None:
                return {
                    "success": False,
                    "data": None,
                    "error": f"Hold {hold_id} not found",
                    "error_code": "NOT_FOUND",
                }
            if hold.get("status") != "hold":
                return {
                    "success": False,
                    "data": None,
                    "error": f"Hold {hold_id} is no longer valid (status: {hold.get('status')})",
                    "error_code": "CONFLICT",
                }

            # Convert hold to confirmed
            now_iso = datetime.now(timezone.utc).isoformat()
            async with get_db() as db:
                await db.execute(
                    """
                    UPDATE reservations
                    SET status = 'confirmed',
                        guest_id = ?,
                        special_requests = ?,
                        hold_expires_at = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (guest["id"], special_requests, now_iso, hold_id),
                )

            updated = await get_reservation_by_id(hold_id)
            return {
                "success": True,
                "data": {
                    "reservation": dict(updated) if updated else {},
                    "restaurant_name": restaurant["name"],
                },
                "error": None,
                "error_code": None,
            }

        # --- Normal creation path ---
        if not idempotency_key:
            idempotency_key = _make_idempotency_key(
                guest_email, restaurant_id, reservation_datetime
            )

        # Need a table_id — either provided or find one
        if not table_id:
            tables = await check_table_availability(
                restaurant_id, party_size, reservation_datetime
            )
            if not tables:
                return {
                    "success": False,
                    "data": None,
                    "error": "No tables available for the requested slot",
                    "error_code": "UNAVAILABLE",
                }
            table_id = tables[0]["id"]

        res = await db_create_reservation(
            idempotency_key=idempotency_key,
            restaurant_id=restaurant_id,
            table_id=table_id,
            guest_id=guest["id"],
            party_size=party_size,
            reservation_datetime=reservation_datetime,
            special_requests=special_requests,
        )

        return {
            "success": True,
            "data": {
                "reservation": dict(res),
                "restaurant_name": restaurant["name"],
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


# ---------------------------------------------------------------------------
# modify_reservation
# ---------------------------------------------------------------------------

async def modify_reservation(params: dict) -> dict:
    """Modify an existing confirmed reservation."""
    try:
        reservation_id: str = params.get("reservation_id", "")
        confirmation_code: str = params.get("confirmation_code", "")
        changes: dict = params.get("changes", {})

        # Look up reservation
        res = None
        if reservation_id:
            res = await get_reservation_by_id(reservation_id)
        elif confirmation_code:
            res = await get_reservation_by_confirmation_code(confirmation_code)

        if res is None:
            return {
                "success": False,
                "data": None,
                "error": "Reservation not found",
                "error_code": "NOT_FOUND",
            }

        if res.get("status") != "confirmed":
            return {
                "success": False,
                "data": None,
                "error": f"Cannot modify reservation with status '{res.get('status')}'",
                "error_code": "CONFLICT",
            }

        rid = res["id"]
        restaurant_id = res["restaurant_id"]
        now_iso = datetime.now(timezone.utc).isoformat()

        new_dt = changes.get("new_datetime")
        new_ps = changes.get("new_party_size")
        new_sr = changes.get("new_special_requests")

        # If changing datetime or party_size, re-check availability
        if new_dt or new_ps:
            check_dt = new_dt or res["reservation_datetime"]
            check_ps = new_ps or res["party_size"]
            tables = await check_table_availability(
                restaurant_id, check_ps, check_dt
            )
            if not tables:
                return {
                    "success": False,
                    "data": None,
                    "error": "No tables available for the new slot",
                    "error_code": "UNAVAILABLE",
                }
            new_table_id = tables[0]["id"]
        else:
            new_table_id = None

        # Apply changes
        async with get_db() as db:
            sets: list[str] = ["updated_at = ?"]
            vals: list = [now_iso]

            if new_dt:
                sets.append("reservation_datetime = ?")
                vals.append(new_dt)
            if new_ps:
                sets.append("party_size = ?")
                vals.append(new_ps)
            if new_sr is not None:
                sets.append("special_requests = ?")
                vals.append(new_sr)
            if new_table_id:
                sets.append("table_id = ?")
                vals.append(new_table_id)

            vals.append(rid)
            await db.execute(
                f"UPDATE reservations SET {', '.join(sets)} WHERE id = ?",
                vals,
            )

        updated = await get_reservation_by_id(rid)
        return {
            "success": True,
            "data": {"reservation": dict(updated) if updated else {}},
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


# ---------------------------------------------------------------------------
# cancel_reservation
# ---------------------------------------------------------------------------

async def cancel_reservation(params: dict) -> dict:
    """Cancel a reservation, release the slot, flag waitlist."""
    try:
        reservation_id: str = params.get("reservation_id", "")
        confirmation_code: str = params.get("confirmation_code", "")
        reason: str = params.get("reason", "")

        res = None
        if reservation_id:
            res = await get_reservation_by_id(reservation_id)
        elif confirmation_code:
            res = await get_reservation_by_confirmation_code(confirmation_code)

        if res is None:
            return {
                "success": False,
                "data": None,
                "error": "Reservation not found",
                "error_code": "NOT_FOUND",
            }

        if res.get("status") == "cancelled":
            return {
                "success": False,
                "data": None,
                "error": "Reservation is already cancelled",
                "error_code": "CONFLICT",
            }

        rid = res["id"]
        ok = await db_cancel_reservation(rid, reason)

        if not ok:
            return {
                "success": False,
                "data": None,
                "error": "Failed to cancel reservation",
                "error_code": "DB_ERROR",
            }

        # Flag waitlist entries for this restaurant/time window
        async with get_db() as db:
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """
                UPDATE waitlist
                SET status = 'notified', notified_at = ?
                WHERE id = (
                    SELECT id FROM waitlist
                    WHERE restaurant_id = ?
                      AND status = 'waiting'
                      AND preferred_datetime = ?
                    ORDER BY added_at ASC
                    LIMIT 1
                )
                """,
                (now_iso, res["restaurant_id"], res["reservation_datetime"]),
            )

        return {
            "success": True,
            "data": {
                "cancelled_reservation_id": rid,
                "confirmation_code": res.get("confirmation_code", ""),
                "message": "Reservation cancelled successfully.",
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
