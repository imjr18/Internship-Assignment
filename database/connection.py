"""
Module: database/connection.py
Responsibility: Manages the async SQLite connection lifecycle with WAL mode,
foreign-key enforcement via aiosqlite.  Provides ``get_db`` (async context
manager) and ``initialize_database`` (runs all DDL from models.py).

Design: Each ``get_db()`` call opens a fresh connection and closes it on exit.
This avoids dangling-thread hangs that aiosqlite's background-thread model
causes when a connection is cached across asyncio.run() boundaries.
"""

from __future__ import annotations

import os
import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from config.settings import get_database_path
from database.models import get_all_ddl


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager — opens a connection, yields it, then closes.

    Usage::

        async with get_db() as db:
            cursor = await db.execute("SELECT ...")
    """
    db_path = get_database_path()
    if db_path != ":memory:":
        parent = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(parent, exist_ok=True)

    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row

    # Enable WAL only for file-backed databases
    if db_path != ":memory:":
        await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA foreign_keys=ON;")

    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        await conn.close()


async def initialize_database() -> None:
    """Run every CREATE TABLE / CREATE INDEX statement from models.py."""
    async with get_db() as db:
        for statement in get_all_ddl():
            await db.execute(statement)


async def close_connection() -> None:
    """No-op kept for API compatibility with tests."""
    pass
