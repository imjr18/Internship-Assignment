"""
Module: database/models.py
Responsibility: Defines the complete SQLite schema as raw SQL CREATE TABLE
statements and index definitions for the GoodFoods reservation system.

Tables:
- restaurants: Restaurant profiles with cuisine, capacity, hours, etc.
- tables: Individual seating units per restaurant.
- reservations: Booking records with idempotency and status tracking.
- guests: Customer profiles with preferences and visit history.
- waitlist: Queue entries for fully-booked restaurants.
"""

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

CREATE_RESTAURANTS_TABLE = """
CREATE TABLE IF NOT EXISTS restaurants (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    neighborhood            TEXT,
    address                 TEXT,
    city                    TEXT,
    latitude                REAL,
    longitude               REAL,
    cuisine_type            TEXT,
    price_range             INTEGER CHECK (price_range BETWEEN 1 AND 4),
    operating_hours         TEXT,           -- JSON string
    total_capacity          INTEGER,
    dietary_certifications  TEXT,           -- JSON array string
    ambiance_tags           TEXT,           -- JSON array string
    phone                   TEXT,
    email                   TEXT,
    description             TEXT,
    created_at              TEXT            -- ISO-8601 datetime
);
"""

CREATE_TABLES_TABLE = """
CREATE TABLE IF NOT EXISTS tables (
    id              TEXT PRIMARY KEY,
    restaurant_id   TEXT NOT NULL,
    capacity        INTEGER NOT NULL,
    location_tag    TEXT CHECK (location_tag IN (
                        'window', 'patio', 'booth', 'bar',
                        'main_floor', 'private'
                    )),
    is_accessible   INTEGER DEFAULT 0,     -- boolean
    table_number    TEXT,
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
);
"""

CREATE_RESERVATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS reservations (
    id                      TEXT PRIMARY KEY,
    idempotency_key         TEXT UNIQUE,
    restaurant_id           TEXT NOT NULL,
    table_id                TEXT NOT NULL,
    guest_id                TEXT,
    party_size              INTEGER NOT NULL,
    reservation_datetime    TEXT NOT NULL,     -- ISO-8601 datetime
    status                  TEXT NOT NULL DEFAULT 'confirmed'
                            CHECK (status IN (
                                'confirmed', 'cancelled', 'completed',
                                'no_show', 'hold'
                            )),
    hold_expires_at         TEXT,              -- nullable ISO-8601
    special_requests        TEXT,
    confirmation_code       TEXT UNIQUE,
    created_at              TEXT,
    updated_at              TEXT,
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
    FOREIGN KEY (table_id)      REFERENCES tables(id),
    FOREIGN KEY (guest_id)      REFERENCES guests(id)
);
"""

CREATE_GUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS guests (
    id                      TEXT PRIMARY KEY,
    name                    TEXT,
    email                   TEXT UNIQUE,
    phone                   TEXT,
    dietary_restrictions    TEXT,              -- JSON array string
    preferences             TEXT,              -- JSON object string
    visit_count             INTEGER DEFAULT 0,
    lifetime_value          REAL DEFAULT 0.0,
    created_at              TEXT,
    consent_given           INTEGER DEFAULT 0  -- boolean
);
"""

CREATE_WAITLIST_TABLE = """
CREATE TABLE IF NOT EXISTS waitlist (
    id                  TEXT PRIMARY KEY,
    restaurant_id       TEXT NOT NULL,
    guest_id            TEXT NOT NULL,
    party_size          INTEGER NOT NULL,
    preferred_datetime  TEXT NOT NULL,
    added_at            TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'waiting'
                        CHECK (status IN (
                            'waiting', 'notified', 'converted', 'expired'
                        )),
    notified_at         TEXT,
    FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
    FOREIGN KEY (guest_id)      REFERENCES guests(id)
);
"""

# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_reservations_lookup "
    "ON reservations(restaurant_id, reservation_datetime, status);",

    "CREATE INDEX IF NOT EXISTS idx_reservations_idempotency "
    "ON reservations(idempotency_key);",

    "CREATE INDEX IF NOT EXISTS idx_reservations_confirmation "
    "ON reservations(confirmation_code);",

    "CREATE INDEX IF NOT EXISTS idx_guests_email "
    "ON guests(email);",

    "CREATE INDEX IF NOT EXISTS idx_waitlist_lookup "
    "ON waitlist(restaurant_id, preferred_datetime, status);",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_TABLE_STATEMENTS: list[str] = [
    CREATE_RESTAURANTS_TABLE,
    CREATE_TABLES_TABLE,
    CREATE_GUESTS_TABLE,       # guests before reservations (FK dependency)
    CREATE_RESERVATIONS_TABLE,
    CREATE_WAITLIST_TABLE,
]


def get_all_ddl() -> list[str]:
    """Return every DDL statement (tables + indexes) in dependency order."""
    return ALL_TABLE_STATEMENTS + CREATE_INDEXES
