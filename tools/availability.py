"""
Module: tools/availability.py
Responsibility: Implements the check_availability tool — validates restaurant
hours, finds available tables, creates a 3-minute hold, and returns slot info.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from database.connection import get_db
from database.queries import (
    get_restaurant_by_id,
    check_table_availability,
    get_or_create_guest,
)

_hold_guest_id: str | None = None


async def _get_hold_guest_id() -> str:
    """Get a stable internal guest id used for temporary hold rows."""
    global _hold_guest_id
    if _hold_guest_id:
        return _hold_guest_id
    hold_guest = await get_or_create_guest(
        email="hold-system@goodfoods.local",
        name="GoodFoods Hold",
        phone="",
    )
    _hold_guest_id = hold_guest["id"]
    return _hold_guest_id


def _safe_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _is_open(operating_hours: Any, date_str: str, time_str: str) -> bool:
    """Check whether the restaurant is open on the given date/time."""
    hours = _safe_json(operating_hours)
    if not hours:
        return True  # assume open if no hours specified

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return True

    day_name = dt.strftime("%A").lower()
    day_info = hours.get(day_name)

    if day_info is None:
        return True
    if day_info == "closed":
        return False
    if isinstance(day_info, dict):
        open_t = day_info.get("open", "00:00")
        close_t = day_info.get("close", "23:59")
        return open_t <= time_str <= close_t

    return True


async def check_availability(params: dict) -> dict:
    """Check availability for a specific restaurant and create a hold.

    Returns available slots or waitlist position if fully booked.
    """
    try:
        restaurant_id: str = params.get("restaurant_id", "")
        party_size = params.get("party_size")
        date: str = params.get("date", "")
        preferred_time: str = params.get("preferred_time", "")
        duration_minutes: int = params.get("duration_minutes", 90)

        if party_size is None:
            return {
                "success": False,
                "data": None,
                "error": "party_size is required",
                "error_code": "INVALID_INPUT",
            }

        # Coerce party_size to int safely
        try:
            party_size = int(party_size)
        except (TypeError, ValueError):
            return {
                "success": False,
                "data": None,
                "error": "party_size must be a positive integer",
                "error_code": "INVALID_INPUT",
            }

        if not restaurant_id:
            return {
                "success": False,
                "data": None,
                "error": "restaurant_id is required",
                "error_code": "INVALID_INPUT",
            }

        if party_size < 1:
            return {
                "success": False,
                "data": None,
                "error": "party_size must be at least 1",
                "error_code": "INVALID_INPUT",
            }

        if not date or not preferred_time:
            return {
                "success": False,
                "data": None,
                "error": "date and preferred_time are required",
                "error_code": "INVALID_INPUT",
            }

        # 1. Does restaurant exist?
        restaurant = await get_restaurant_by_id(restaurant_id)
        if restaurant is None:
            return {
                "success": False,
                "data": None,
                "error": f"Restaurant {restaurant_id} not found",
                "error_code": "NOT_FOUND",
            }

        # 2. Is it open?
        if not _is_open(restaurant.get("operating_hours"), date, preferred_time):
            return {
                "success": False,
                "data": None,
                "error": (
                    f"{restaurant['name']} is closed on "
                    f"{date} at {preferred_time}"
                ),
                "error_code": "UNAVAILABLE",
            }

        # 3. Check availability for preferred time ± 60 min
        base_dt = datetime.fromisoformat(f"{date}T{preferred_time}:00")
        offsets = [0, -30, 30, -60, 60]
        available_slots: list[dict] = []

        from database.queries import _generate_confirmation_code

        hold_guest_id = await _get_hold_guest_id()

        async with get_db() as db:
            await db.execute("BEGIN EXCLUSIVE")
            try:
                for offset in offsets:
                    slot_dt = base_dt + timedelta(minutes=offset)
                    slot_str = slot_dt.isoformat()
                    tables = await check_table_availability(
                        restaurant_id=restaurant_id,
                        party_size=party_size,
                        datetime_str=slot_str,
                        duration_minutes=duration_minutes,
                        db=db,
                    )
                    for t in tables:
                        # Avoid duplicates
                        if not any(s["table_id"] == t["id"] and s["datetime"] == slot_str
                                   for s in available_slots):
                            available_slots.append({
                                "table_id": t["id"],
                                "capacity": t["capacity"],
                                "location_tag": t.get("location_tag", ""),
                                "is_accessible": bool(t.get("is_accessible", 0)),
                                "datetime": slot_str,
                            })

                if not available_slots:
                    # No slots — get waitlist count
                    cur = await db.execute(
                        "SELECT COUNT(*) FROM waitlist "
                        "WHERE restaurant_id = ? AND status = 'waiting'",
                        (restaurant_id,),
                    )
                    (wait_count,) = await cur.fetchone()

                    return {
                        "success": True,
                        "data": {
                            "available": False,
                            "restaurant_name": restaurant["name"],
                            "slots": [],
                            "waitlist_position": wait_count + 1,
                        },
                        "error": None,
                        "error_code": None,
                    }

                # 4. Create a hold on the best slot (first available)
                best = available_slots[0]
                hold_id = str(uuid.uuid4())
                now_iso = datetime.now(timezone.utc).isoformat()
                hold_expires = (
                    datetime.now(timezone.utc) + timedelta(minutes=3)
                ).isoformat()
                await db.execute(
                    """
                    INSERT INTO reservations
                        (id, idempotency_key, restaurant_id, table_id, guest_id,
                         party_size, reservation_datetime, status,
                         hold_expires_at, special_requests, confirmation_code,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'hold', ?, '', ?, ?, ?)
                    """,
                    (
                        hold_id,
                        f"hold-{hold_id}",
                        restaurant_id,
                        best["table_id"],
                        hold_guest_id,
                        party_size,
                        best["datetime"],
                        hold_expires,
                        _generate_confirmation_code(),
                        now_iso,
                        now_iso,
                    ),
                )
            except Exception:
                # get_db() handles rollback on exception, just re-raise
                raise

        return {
            "success": True,
            "data": {
                "available": True,
                "restaurant_name": restaurant["name"],
                "hold_id": hold_id,
                "hold_expires_at": hold_expires,
                "slots": available_slots,
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
