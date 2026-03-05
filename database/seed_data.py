"""
Module: database/seed_data.py
Responsibility: Generates and inserts 75 realistic, varied restaurant profiles
along with 4-15 individual table records per restaurant. Includes an
idempotency guard—if the restaurants table already contains >= 75 rows the
seed is skipped.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone

from database.connection import get_db, initialize_database

# ---------------------------------------------------------------------------
# Constants — pools for randomisation
# ---------------------------------------------------------------------------

CUISINE_TYPES: list[str] = [
    "Italian", "Japanese", "Indian", "Mexican", "French", "American",
    "Thai", "Mediterranean", "Chinese", "Korean", "Ethiopian",
    "Middle Eastern", "Spanish", "Vietnamese",
]

NEIGHBORHOODS: list[str] = [
    "Downtown", "Midtown", "West End", "East Village",
    "Harbor District", "University Quarter",
]

DIETARY_POOL: list[str] = [
    "vegan_friendly", "vegetarian_friendly", "gluten_free_kitchen",
    "halal_certified", "kosher_certified", "nut_free_kitchen",
]

AMBIANCE_POOL: list[str] = [
    "romantic", "business_friendly", "family_friendly", "quiet", "lively",
    "rooftop", "waterfront", "historic", "private_dining", "live_music",
    "outdoor_seating", "pet_friendly",
]

TABLE_SIZES: list[int] = [2, 2, 2, 4, 4, 4, 6, 6, 8]
LOCATION_TAGS: list[str] = ["window", "patio", "booth", "bar", "main_floor", "private"]

# ---------------------------------------------------------------------------
# Restaurant name generator
# ---------------------------------------------------------------------------

_FIRST = [
    "The Golden", "Casa", "Sakura", "Spice", "Le Petit", "Blue",
    "Red", "Green", "Silver", "Copper", "Iron", "Jade", "Pearl",
    "Olive", "Saffron", "Basil", "Cedar", "Lotus", "Tidal",
    "Ember", "Azure", "Coral", "Ivory", "Onyx", "Maple",
    "Mango", "Fig", "Sage", "Thyme", "Rosemary", "Mint",
    "Crimson", "Violet", "Indigo", "Amber", "Terra", "Luna",
    "Sol", "Nova", "Stellar", "Grand",
]

_SECOND = [
    "Garden", "Kitchen", "Table", "House", "Room", "Bistro",
    "Grill", "Tavern", "Café", "Lounge", "Terrace", "Brasserie",
    "Palace", "Corner", "Harbor", "Flame", "Spoon", "Plate",
    "Fork", "Vine", "Nest", "Bay", "Pier", "Hearth",
    "Stone", "Market", "Oven", "Wok", "Pot", "Bowl",
]

_DESCRIPTION_TEMPLATES: list[str] = [
    "An intimate {cuisine} restaurant nestled in {neighborhood}, known for its {adj1} atmosphere and {adj2} dishes.",
    "A {adj1} {cuisine} eatery offering {adj2} flavors in the heart of {neighborhood}.",
    "{adj1} and {adj2} {cuisine} dining experience in {neighborhood}—perfect for special occasions.",
    "Bringing the best of {cuisine} cuisine to {neighborhood} with a {adj1}, {adj2} setting.",
    "A beloved {neighborhood} gem serving {adj1} {cuisine} creations in a {adj2} space.",
]

_ADJECTIVES = [
    "cozy", "elegant", "vibrant", "modern", "rustic", "charming",
    "sophisticated", "warm", "contemporary", "authentic", "artisan",
    "seasonal", "organic", "inventive", "traditional", "creative",
]


def _make_hours(closed_monday: bool = False) -> dict:
    """Generate realistic operating hours as a dict."""
    days = ["monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday"]
    hours: dict[str, dict[str, str] | str] = {}
    for d in days:
        if d == "monday" and closed_monday:
            hours[d] = "closed"
        elif d in ("friday", "saturday"):
            hours[d] = {"open": "11:00", "close": "23:00"}
        elif d == "sunday":
            hours[d] = {"open": "10:00", "close": "21:00"}
        else:
            hours[d] = {"open": "11:00", "close": "22:00"}
    return hours


# Price-range distribution: 15 × $, 25 × $$, 25 × $$$, 10 × $$$$
_PRICE_DISTRIBUTION: list[int] = (
    [1] * 15 + [2] * 25 + [3] * 25 + [4] * 10
)


def _generate_restaurants() -> list[dict]:
    """Return a list of 75 unique restaurant dicts."""
    random.seed(42)  # deterministic

    # Pre-shuffle price distribution
    prices = _PRICE_DISTRIBUTION[:75]
    random.shuffle(prices)

    # Ensure at least 5 closed-on-monday flags
    closed_monday_flags = [True] * 7 + [False] * 68
    random.shuffle(closed_monday_flags)

    used_names: set[str] = set()
    restaurants: list[dict] = []

    for i in range(75):
        # Unique name
        while True:
            name = f"{random.choice(_FIRST)} {random.choice(_SECOND)}"
            if name not in used_names:
                used_names.add(name)
                break

        neighborhood = NEIGHBORHOODS[i % len(NEIGHBORHOODS)]
        cuisine = CUISINE_TYPES[i % len(CUISINE_TYPES)]
        price = prices[i]

        # Random subsets
        dietary = random.sample(DIETARY_POOL, k=random.randint(0, 3))
        ambiance = random.sample(AMBIANCE_POOL, k=random.randint(2, 5))
        num_tables = random.randint(4, 15)
        total_cap = 0
        table_records: list[dict] = []
        for t in range(num_tables):
            cap = random.choice(TABLE_SIZES)
            total_cap += cap
            table_records.append({
                "id": str(uuid.uuid4()),
                "capacity": cap,
                "location_tag": random.choice(LOCATION_TAGS),
                "is_accessible": 1 if random.random() < 0.3 else 0,
                "table_number": f"T{t+1:02d}",
            })

        adj1, adj2 = random.sample(_ADJECTIVES, 2)
        desc_tpl = random.choice(_DESCRIPTION_TEMPLATES)
        description = desc_tpl.format(
            cuisine=cuisine, neighborhood=neighborhood,
            adj1=adj1, adj2=adj2,
        )

        restaurants.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "neighborhood": neighborhood,
            "address": f"{random.randint(1,999)} {random.choice(['Main','Oak','Elm','Park','River','Lake','Hill','Bay'])} St",
            "city": "Metropolis",
            "latitude": round(40.7 + random.uniform(-0.05, 0.05), 6),
            "longitude": round(-74.0 + random.uniform(-0.05, 0.05), 6),
            "cuisine_type": cuisine,
            "price_range": price,
            "operating_hours": json.dumps(_make_hours(closed_monday_flags[i])),
            "total_capacity": total_cap,
            "dietary_certifications": json.dumps(dietary),
            "ambiance_tags": json.dumps(ambiance),
            "phone": f"+1-555-{random.randint(100,999)}-{random.randint(1000,9999)}",
            "email": f"info@{name.lower().replace(' ', '')}.com",
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_tables": table_records,
        })

    return restaurants


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_seed() -> None:
    """Seed the database with 75 restaurants and their tables.

    Idempotent: skips if ``restaurants`` already has >= 75 rows.
    """
    await initialize_database()

    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM restaurants")
        row = await cursor.fetchone()
        count = row[0] if row else 0

        if count >= 75:
            print(f"Seed skipped — already {count} restaurants in DB.")
            return

        restaurants = _generate_restaurants()

        for r in restaurants:
            tables = r.pop("_tables")
            cols = list(r.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_str = ", ".join(cols)
            await db.execute(
                f"INSERT INTO restaurants ({col_str}) VALUES ({placeholders})",
                tuple(r[c] for c in cols),
            )
            for t in tables:
                await db.execute(
                    """INSERT INTO tables (id, restaurant_id, capacity,
                       location_tag, is_accessible, table_number)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (t["id"], r["id"], t["capacity"], t["location_tag"],
                     t["is_accessible"], t["table_number"]),
                )

        await db.commit()
        print(f"Seeded {len(restaurants)} restaurants with tables.")
