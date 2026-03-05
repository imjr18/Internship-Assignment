"""
Module: database/queries.py
Responsibility: Every read and write query the application needs, implemented
as fully-typed async functions.  Each function acquires its own connection via
``get_db`` and never raises on "not found" — it returns ``None`` or ``[]``.
Actual errors (constraint violations, connection failures) propagate as
exceptions.
"""

from __future__ import annotations

import json
import uuid
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Any

from database.connection import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict:
    """Convert an aiosqlite.Row (or None) to a plain dict."""
    if row is None:
        return {}
    return dict(row)


def _generate_confirmation_code() -> str:
    """Return a short human-friendly confirmation code like 'GF-A7K2M9'."""
    chars = string.ascii_uppercase + string.digits
    body = "".join(random.choices(chars, k=6))
    return f"GF-{body}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Restaurant queries
# ---------------------------------------------------------------------------

async def get_restaurant_by_id(restaurant_id: str) -> dict | None:
    """Fetch a single restaurant by its UUID.

    Returns:
        dict with all restaurant columns, or None if not found.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM restaurants WHERE id = ?", (restaurant_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def search_restaurants_structured(
    cuisine_type: str | None = None,
    min_capacity: int = 1,
    date: str | None = None,       # unused for SQL filter, kept for interface
    time: str | None = None,       # unused for SQL filter, kept for interface
    dietary_certifications: list[str] | None = None,
) -> list[dict]:
    """Search restaurants with optional structured filters.

    Filters applied via SQL WHERE:
    - ``cuisine_type`` exact match (case-insensitive) if provided.
    - ``total_capacity >= min_capacity``.
    - Each requested ``dietary_certifications`` must appear inside the
      restaurant's JSON array string.

    Returns:
        List of matching restaurant dicts (may be empty).
    """
    clauses: list[str] = ["1=1"]
    params: list[Any] = []

    if cuisine_type:
        clauses.append("LOWER(cuisine_type) = LOWER(?)")
        params.append(cuisine_type)

    clauses.append("total_capacity >= ?")
    params.append(min_capacity)

    if dietary_certifications:
        for cert in dietary_certifications:
            clauses.append("dietary_certifications LIKE ?")
            params.append(f"%{cert}%")

    query = f"SELECT * FROM restaurants WHERE {' AND '.join(clauses)}"
    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def get_all_restaurants() -> list[dict]:
    """Returns all restaurants for the browser UI.

    Returns:
        List of restaurant dicts ordered by neighborhood, name.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, name, neighborhood, cuisine_type,
                   price_range, total_capacity,
                   dietary_certifications, ambiance_tags,
                   operating_hours, description
            FROM restaurants
            ORDER BY neighborhood, name
            """
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Availability queries
# ---------------------------------------------------------------------------

async def check_table_availability(
    restaurant_id: str,
    party_size: int,
    datetime_str: str,
    duration_minutes: int = 90,
) -> list[dict]:
    """Find tables at *restaurant_id* that can seat *party_size* and have no
    overlapping confirmed/hold reservations for the requested window.

    The overlap window is [datetime_str, datetime_str + duration_minutes).

    Returns:
        List of available table dicts (may be empty).
    """
    dt = datetime.fromisoformat(datetime_str)
    window_end = (dt + timedelta(minutes=duration_minutes)).isoformat()

    query = """
    SELECT t.*
    FROM   tables t
    WHERE  t.restaurant_id = ?
      AND  t.capacity >= ?
      AND  t.id NOT IN (
               SELECT r.table_id
               FROM   reservations r
               WHERE  r.restaurant_id = ?
                 AND  r.status IN ('confirmed', 'hold')
                 AND  r.reservation_datetime < ?
                 AND  datetime(r.reservation_datetime, '+' || ? || ' minutes') > ?
           )
    ORDER BY t.capacity ASC
    """
    params = (
        restaurant_id,
        party_size,
        restaurant_id,
        window_end,
        duration_minutes,
        datetime_str,
    )

    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Reservation queries
# ---------------------------------------------------------------------------

async def create_reservation(
    idempotency_key: str,
    restaurant_id: str,
    table_id: str,
    guest_id: str,
    party_size: int,
    reservation_datetime: str,
    special_requests: str = "",
) -> dict:
    """Insert a new reservation. Respects idempotency: if the same
    *idempotency_key* already exists, the existing row is returned instead.

    Returns:
        The reservation row as a dict.

    Raises:
        sqlite3.IntegrityError on FK / uniqueness violations other than the
        idempotency key.
    """
    async with get_db() as db:
        # Idempotency check
        cursor = await db.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        existing = await cursor.fetchone()
        if existing:
            return _row_to_dict(existing)

        reservation_id = str(uuid.uuid4())
        confirmation_code = _generate_confirmation_code()
        now = _now_iso()

        await db.execute(
            """
            INSERT INTO reservations
                (id, idempotency_key, restaurant_id, table_id, guest_id,
                 party_size, reservation_datetime, status, special_requests,
                 confirmation_code, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?, ?, ?)
            """,
            (
                reservation_id, idempotency_key, restaurant_id, table_id,
                guest_id, party_size, reservation_datetime, special_requests,
                confirmation_code, now, now,
            ),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM reservations WHERE id = ?", (reservation_id,)
        )
        return _row_to_dict(await cursor.fetchone())


async def get_reservation_by_id(reservation_id: str) -> dict | None:
    """Fetch a reservation by its UUID.

    Returns:
        dict or None.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM reservations WHERE id = ?", (reservation_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_reservation_by_confirmation_code(code: str) -> dict | None:
    """Look up a reservation by its human-readable confirmation code.

    Returns:
        dict or None.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM reservations WHERE confirmation_code = ?", (code,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def update_reservation_status(
    reservation_id: str,
    status: str,
) -> bool:
    """Set a reservation's status and bump ``updated_at``.

    Returns:
        True if a row was updated, False if the reservation was not found.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            UPDATE reservations
            SET    status = ?, updated_at = ?
            WHERE  id = ?
            """,
            (status, _now_iso(), reservation_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def cancel_reservation(
    reservation_id: str,
    reason: str = "",
) -> bool:
    """Cancel a reservation (sets status = 'cancelled').

    *reason* is appended to ``special_requests`` for auditing.

    Returns:
        True if cancelled, False if not found.
    """
    async with get_db() as db:
        now = _now_iso()
        note = f" [CANCELLED: {reason}]" if reason else ""
        cursor = await db.execute(
            """
            UPDATE reservations
            SET    status = 'cancelled',
                   special_requests = COALESCE(special_requests, '') || ?,
                   updated_at = ?
            WHERE  id = ?
              AND  status != 'cancelled'
            """,
            (note, now, reservation_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Guest queries
# ---------------------------------------------------------------------------

async def get_or_create_guest(
    email: str,
    name: str = "",
    phone: str = "",
) -> dict:
    """Find an existing guest by email, or create a new one.

    Returns:
        Guest dict.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM guests WHERE email = ?", (email,)
        )
        existing = await cursor.fetchone()
        if existing:
            return _row_to_dict(existing)

        guest_id = str(uuid.uuid4())
        now = _now_iso()
        await db.execute(
            """
            INSERT INTO guests (id, name, email, phone, dietary_restrictions,
                                preferences, visit_count, lifetime_value,
                                created_at, consent_given)
            VALUES (?, ?, ?, ?, '[]', '{}', 0, 0.0, ?, 0)
            """,
            (guest_id, name, email, phone, now),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM guests WHERE id = ?", (guest_id,)
        )
        return _row_to_dict(await cursor.fetchone())


async def get_guest_history(guest_id: str) -> list[dict]:
    """Return all reservations for a guest, ordered by date descending.

    Returns:
        List of reservation dicts (may be empty).
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT r.*, rest.name AS restaurant_name
            FROM   reservations r
            JOIN   restaurants rest ON rest.id = r.restaurant_id
            WHERE  r.guest_id = ?
            ORDER  BY r.reservation_datetime DESC
            """,
            (guest_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Waitlist queries
# ---------------------------------------------------------------------------

async def add_to_waitlist(
    restaurant_id: str,
    guest_id: str,
    party_size: int,
    preferred_datetime: str,
) -> dict:
    """Create a new waitlist entry.

    Returns:
        The newly created waitlist row as a dict.
    """
    async with get_db() as db:
        entry_id = str(uuid.uuid4())
        now = _now_iso()
        await db.execute(
            """
            INSERT INTO waitlist (id, restaurant_id, guest_id, party_size,
                                  preferred_datetime, added_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'waiting')
            """,
            (entry_id, restaurant_id, guest_id, party_size,
             preferred_datetime, now),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM waitlist WHERE id = ?", (entry_id,)
        )
        return _row_to_dict(await cursor.fetchone())


# ---------------------------------------------------------------------------
# Maintenance queries
# ---------------------------------------------------------------------------

async def expire_stale_holds() -> int:
    """Release all reservations with status='hold' whose hold_expires_at
    has passed.

    Returns:
        Number of rows released (set to 'cancelled').
    """
    now = _now_iso()
    async with get_db() as db:
        cursor = await db.execute(
            """
            UPDATE reservations
            SET    status = 'cancelled', updated_at = ?
            WHERE  status = 'hold'
              AND  hold_expires_at IS NOT NULL
              AND  hold_expires_at < ?
            """,
            (now, now),
        )
        await db.commit()
        return cursor.rowcount
