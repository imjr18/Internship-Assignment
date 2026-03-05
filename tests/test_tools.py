"""
Tests for the tool layer (TL-01 through TL-10).

Each tool is tested for:
  a) Happy path — correct input, correct output structure
  b) Not found — invalid ID returns NOT_FOUND
  c) Invalid input — wrong/missing params returns INVALID_INPUT
  d) Edge case specific to the tool

Uses a file-backed temp SQLite seeded with 3 restaurants + tables + 1 guest.
"""

from __future__ import annotations

import json
import os
import tempfile

# Point at a temp DB before any app imports
_TEST_DB = os.path.join(tempfile.gettempdir(), "goodfoods_tools_test.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["DATABASE_PATH"] = _TEST_DB
os.environ["FAISS_INDEX_PATH"] = os.path.join(
    tempfile.gettempdir(), "goodfoods_test.faiss"
)

import uuid
import pytest
import pytest_asyncio

from database.connection import initialize_database, get_db
from database.models import get_all_ddl

# Tool imports
from tools.recommendations import search_restaurants
from tools.availability import check_availability
from tools.reservations import (
    create_reservation,
    modify_reservation,
    cancel_reservation,
)
from tools.guest_profiles import get_guest_history
from tools.waitlist import add_to_waitlist
from tools.escalation import escalate_to_human


# ---------------------------------------------------------------------------
# Minimal seed data (3 restaurants, tables, 1 guest)
# ---------------------------------------------------------------------------

_REST_IDS = [str(uuid.uuid4()) for _ in range(3)]
_TABLE_IDS = {rid: [str(uuid.uuid4()) for _ in range(4)] for rid in _REST_IDS}
_GUEST_ID = str(uuid.uuid4())

_HOURS_OPEN = json.dumps({
    "monday": {"open": "11:00", "close": "22:00"},
    "tuesday": {"open": "11:00", "close": "22:00"},
    "wednesday": {"open": "11:00", "close": "22:00"},
    "thursday": {"open": "11:00", "close": "22:00"},
    "friday": {"open": "11:00", "close": "23:00"},
    "saturday": {"open": "11:00", "close": "23:00"},
    "sunday": {"open": "10:00", "close": "21:00"},
})

_HOURS_CLOSED_MON = json.dumps({
    "monday": "closed",
    "tuesday": {"open": "11:00", "close": "22:00"},
    "wednesday": {"open": "11:00", "close": "22:00"},
    "thursday": {"open": "11:00", "close": "22:00"},
    "friday": {"open": "11:00", "close": "23:00"},
    "saturday": {"open": "11:00", "close": "23:00"},
    "sunday": {"open": "10:00", "close": "21:00"},
})


async def _seed_test_data():
    """Insert minimal restaurant/table/guest data for testing."""
    restaurants = [
        (_REST_IDS[0], "Bella Italia", "Downtown", "Italian", 2, _HOURS_OPEN,
         30, '["vegetarian_friendly","gluten_free_kitchen"]',
         '["romantic","quiet"]', "A cozy Italian gem"),
        (_REST_IDS[1], "Tokyo Ramen", "Midtown", "Japanese", 1, _HOURS_CLOSED_MON,
         20, '["vegan_friendly"]', '["lively","family_friendly"]',
         "Authentic ramen house"),
        (_REST_IDS[2], "Spice Route", "East Village", "Indian", 3, _HOURS_OPEN,
         40, '["vegan_friendly","halal_certified"]',
         '["business_friendly","private_dining"]',
         "Fine Indian dining with private rooms"),
    ]

    async with get_db() as db:
        for r in restaurants:
            await db.execute(
                """INSERT INTO restaurants
                   (id, name, neighborhood, cuisine_type, price_range,
                    operating_hours, total_capacity,
                    dietary_certifications, ambiance_tags, description,
                    created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                r,
            )

        table_caps = [2, 4, 6, 8]
        tags = ["window", "booth", "main_floor", "patio"]
        for rid in _REST_IDS:
            for i, tid in enumerate(_TABLE_IDS[rid]):
                await db.execute(
                    """INSERT INTO tables
                       (id, restaurant_id, capacity, location_tag,
                        is_accessible, table_number)
                       VALUES (?,?,?,?,?,?)""",
                    (tid, rid, table_caps[i], tags[i], 1 if i == 0 else 0,
                     f"T{i+1:02d}"),
                )

        await db.execute(
            """INSERT INTO guests
               (id, name, email, phone, dietary_restrictions, preferences,
                visit_count, lifetime_value, created_at, consent_given)
               VALUES (?,?,?,?,'[]','{}',5,250.0,datetime('now'),1)""",
            (_GUEST_ID, "Test User", "test@example.com", "+1-555-000-0000"),
        )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _init_test_db():
    await initialize_database()
    await _seed_test_data()
    yield
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)


# ---------------------------------------------------------------------------
# Helper to verify the standard tool response contract
# ---------------------------------------------------------------------------

def assert_tool_response(resp: dict):
    """Every tool response must have these 4 keys."""
    assert "success" in resp, f"Missing 'success': {resp}"
    assert "data" in resp, f"Missing 'data': {resp}"
    assert "error" in resp, f"Missing 'error': {resp}"
    assert "error_code" in resp, f"Missing 'error_code': {resp}"


# ===================================================================
# search_restaurants
# ===================================================================

@pytest.mark.asyncio
async def test_search_restaurants_happy():
    resp = await search_restaurants({
        "query": "romantic Italian dinner",
        "party_size": 2,
        "date": "2026-04-01",
        "time": "19:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is True
    assert len(resp["data"]["results"]) > 0


@pytest.mark.asyncio
async def test_search_restaurants_no_query():
    resp = await search_restaurants({
        "party_size": 2,
        "date": "2026-04-01",
        "time": "19:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "INVALID_INPUT"


# ===================================================================
# check_availability
# ===================================================================

@pytest.mark.asyncio
async def test_check_availability_happy():
    resp = await check_availability({
        "restaurant_id": _REST_IDS[0],
        "party_size": 2,
        "date": "2026-04-01",
        "preferred_time": "19:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is True
    assert resp["data"]["available"] is True
    assert "hold_id" in resp["data"]


@pytest.mark.asyncio
async def test_check_availability_not_found():
    resp = await check_availability({
        "restaurant_id": "nonexistent-id",
        "party_size": 2,
        "date": "2026-04-01",
        "preferred_time": "19:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_check_availability_closed_day():
    # Tokyo Ramen is closed on Mondays; 2026-04-06 is a Monday
    resp = await check_availability({
        "restaurant_id": _REST_IDS[1],
        "party_size": 2,
        "date": "2026-04-06",
        "preferred_time": "19:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_check_availability_no_restaurant_id():
    resp = await check_availability({
        "party_size": 2,
        "date": "2026-04-01",
        "preferred_time": "19:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "INVALID_INPUT"


# ===================================================================
# create_reservation
# ===================================================================

@pytest.mark.asyncio
async def test_create_reservation_happy():
    resp = await create_reservation({
        "restaurant_id": _REST_IDS[0],
        "table_id": _TABLE_IDS[_REST_IDS[0]][0],
        "guest_name": "Alice Test",
        "guest_email": "alice@test.com",
        "guest_phone": "+1-555-111-1111",
        "party_size": 2,
        "reservation_datetime": "2026-04-02T19:00:00",
        "special_requests": "Anniversary dinner",
        "idempotency_key": "idem-tool-test-1",
    })
    assert_tool_response(resp)
    assert resp["success"] is True
    assert "reservation" in resp["data"]
    assert resp["data"]["reservation"]["status"] == "confirmed"


@pytest.mark.asyncio
async def test_create_reservation_idempotent():
    key = "idem-tool-dup-test"
    args = {
        "restaurant_id": _REST_IDS[0],
        "table_id": _TABLE_IDS[_REST_IDS[0]][1],
        "guest_name": "Bob Test",
        "guest_email": "bob@test.com",
        "guest_phone": "+1-555-222-2222",
        "party_size": 2,
        "reservation_datetime": "2026-04-03T19:00:00",
        "idempotency_key": key,
    }
    r1 = await create_reservation(args)
    r2 = await create_reservation(args)
    assert_tool_response(r1)
    assert_tool_response(r2)
    assert r1["data"]["reservation"]["id"] == r2["data"]["reservation"]["id"]


@pytest.mark.asyncio
async def test_create_reservation_invalid_input():
    resp = await create_reservation({
        "restaurant_id": _REST_IDS[0],
        "guest_name": "",
        "guest_email": "",
        "guest_phone": "",
        "party_size": 2,
        "reservation_datetime": "2026-04-01T19:00:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_create_reservation_not_found():
    resp = await create_reservation({
        "restaurant_id": "nonexistent",
        "guest_name": "X",
        "guest_email": "x@x.com",
        "guest_phone": "+1",
        "party_size": 2,
        "reservation_datetime": "2026-04-01T19:00:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_create_reservation_with_hold():
    # First get a hold
    avail = await check_availability({
        "restaurant_id": _REST_IDS[2],
        "party_size": 2,
        "date": "2026-04-10",
        "preferred_time": "20:00",
    })
    assert avail["success"] is True
    hold_id = avail["data"]["hold_id"]

    # Convert hold
    resp = await create_reservation({
        "hold_id": hold_id,
        "restaurant_id": _REST_IDS[2],
        "guest_name": "Hold Guest",
        "guest_email": "hold@test.com",
        "guest_phone": "+1-555-333-3333",
        "party_size": 2,
        "reservation_datetime": "2026-04-10T20:00:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is True
    assert resp["data"]["reservation"]["status"] == "confirmed"


# ===================================================================
# modify_reservation
# ===================================================================

@pytest.mark.asyncio
async def test_modify_reservation_happy():
    # Create one first
    cr = await create_reservation({
        "restaurant_id": _REST_IDS[0],
        "table_id": _TABLE_IDS[_REST_IDS[0]][2],
        "guest_name": "Modify Me",
        "guest_email": "modify@test.com",
        "guest_phone": "+1-555-444-4444",
        "party_size": 2,
        "reservation_datetime": "2026-04-04T19:00:00",
        "idempotency_key": "idem-modify-test",
    })
    rid = cr["data"]["reservation"]["id"]

    resp = await modify_reservation({
        "reservation_id": rid,
        "changes": {"new_special_requests": "Need high chair"},
    })
    assert_tool_response(resp)
    assert resp["success"] is True
    assert "high chair" in resp["data"]["reservation"]["special_requests"]


@pytest.mark.asyncio
async def test_modify_reservation_not_found():
    resp = await modify_reservation({
        "reservation_id": "nonexistent",
        "changes": {"new_special_requests": "test"},
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "NOT_FOUND"


# ===================================================================
# cancel_reservation
# ===================================================================

@pytest.mark.asyncio
async def test_cancel_reservation_happy():
    cr = await create_reservation({
        "restaurant_id": _REST_IDS[0],
        "table_id": _TABLE_IDS[_REST_IDS[0]][3],
        "guest_name": "Cancel Me",
        "guest_email": "cancel@test.com",
        "guest_phone": "+1-555-555-5555",
        "party_size": 2,
        "reservation_datetime": "2026-04-05T19:00:00",
        "idempotency_key": "idem-cancel-test",
    })
    rid = cr["data"]["reservation"]["id"]

    resp = await cancel_reservation({
        "reservation_id": rid,
        "reason": "plans changed",
    })
    assert_tool_response(resp)
    assert resp["success"] is True


@pytest.mark.asyncio
async def test_cancel_reservation_already_cancelled():
    cr = await create_reservation({
        "restaurant_id": _REST_IDS[0],
        "table_id": _TABLE_IDS[_REST_IDS[0]][0],
        "guest_name": "Double Cancel",
        "guest_email": "dblcancel@test.com",
        "guest_phone": "+1-555-666-6666",
        "party_size": 2,
        "reservation_datetime": "2026-04-06T19:00:00",
        "idempotency_key": "idem-dblcancel",
    })
    rid = cr["data"]["reservation"]["id"]

    await cancel_reservation({"reservation_id": rid, "reason": "first"})
    resp = await cancel_reservation({"reservation_id": rid, "reason": "second"})
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_cancel_reservation_not_found():
    resp = await cancel_reservation({
        "reservation_id": "nonexistent",
        "reason": "test",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "NOT_FOUND"


# ===================================================================
# get_guest_history
# ===================================================================

@pytest.mark.asyncio
async def test_get_guest_history_happy():
    resp = await get_guest_history({"guest_email": "test@example.com"})
    assert_tool_response(resp)
    assert resp["success"] is True
    assert resp["data"]["guest"]["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_get_guest_history_not_found():
    resp = await get_guest_history({"guest_email": "nobody@nowhere.com"})
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_guest_history_invalid():
    resp = await get_guest_history({})
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "INVALID_INPUT"


# ===================================================================
# add_to_waitlist
# ===================================================================

@pytest.mark.asyncio
async def test_add_to_waitlist_happy():
    resp = await add_to_waitlist({
        "restaurant_id": _REST_IDS[0],
        "guest_name": "Waiter Test",
        "guest_email": "waiter2@test.com",
        "guest_phone": "+1-555-777-7777",
        "party_size": 4,
        "preferred_datetime": "2026-04-01T19:00:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is True
    assert resp["data"]["position"] >= 1


@pytest.mark.asyncio
async def test_add_to_waitlist_not_found():
    resp = await add_to_waitlist({
        "restaurant_id": "nonexistent",
        "guest_name": "X",
        "guest_email": "x@x.com",
        "guest_phone": "+1",
        "party_size": 2,
        "preferred_datetime": "2026-04-01T19:00:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_add_to_waitlist_invalid():
    resp = await add_to_waitlist({
        "restaurant_id": _REST_IDS[0],
        "guest_name": "",
        "guest_email": "",
        "guest_phone": "",
        "party_size": 0,
        "preferred_datetime": "2026-04-01T19:00:00",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "INVALID_INPUT"


# ===================================================================
# escalate_to_human
# ===================================================================

@pytest.mark.asyncio
async def test_escalate_to_human_happy():
    resp = await escalate_to_human({
        "reason": "Guest is hostile and demanding refund",
        "urgency_level": "high",
        "conversation_summary": "Guest complained about cold food.",
    })
    assert_tool_response(resp)
    assert resp["success"] is True
    assert "escalation_id" in resp["data"]
    assert "15 minutes" in resp["data"]["guest_message"]


@pytest.mark.asyncio
async def test_escalate_to_human_invalid_urgency():
    resp = await escalate_to_human({
        "reason": "test",
        "urgency_level": "extreme",
        "conversation_summary": "test",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_escalate_to_human_no_reason():
    resp = await escalate_to_human({
        "urgency_level": "low",
        "conversation_summary": "test",
    })
    assert_tool_response(resp)
    assert resp["success"] is False
    assert resp["error_code"] == "INVALID_INPUT"
