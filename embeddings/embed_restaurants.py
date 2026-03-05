"""
Module: embeddings/embed_restaurants.py
Responsibility: Generates sentence-transformer embeddings for every restaurant
profile, builds a FAISS IndexFlatL2 index, and persists both the index file
and a JSON id-map alongside it.
"""

from __future__ import annotations

import json
import os
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from config.settings import get_database_path, get_faiss_index_path
from database.connection import get_db, initialize_database

# ---------------------------------------------------------------------------
# Model loader (cached at module level)
# ---------------------------------------------------------------------------
_model: SentenceTransformer | None = None


def load_embedding_model() -> SentenceTransformer:
    """Load (and cache) the all-MiniLM-L6-v2 sentence-transformer model."""
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def generate_restaurant_embedding(restaurant: dict) -> np.ndarray:
    """Create a single embedding vector for a restaurant by concatenating
    key text fields: name, cuisine_type, ambiance_tags,
    dietary_certifications, description.

    Returns:
        1-D numpy float32 array.
    """
    parts: list[str] = [
        restaurant.get("name", ""),
        restaurant.get("cuisine_type", ""),
    ]

    # ambiance_tags and dietary_certifications are stored as JSON strings
    for field in ("ambiance_tags", "dietary_certifications"):
        raw = restaurant.get(field, "[]")
        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            items = []
        parts.extend(items)

    parts.append(restaurant.get("description", ""))

    text = " ".join(p for p in parts if p)
    model = load_embedding_model()
    embedding: np.ndarray = model.encode(text, convert_to_numpy=True)
    return embedding.astype(np.float32)


def build_faiss_index(restaurants: list[dict]) -> tuple[faiss.Index, list[str]]:
    """Build a FAISS IndexFlatL2 from a list of restaurant dicts.

    Returns:
        (index, restaurant_ids) — the index and a parallel list of UUIDs.
    """
    embeddings: list[np.ndarray] = []
    ids: list[str] = []

    for r in restaurants:
        vec = generate_restaurant_embedding(r)
        embeddings.append(vec)
        ids.append(r["id"])

    matrix = np.vstack(embeddings).astype(np.float32)
    dim = matrix.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(matrix)
    return index, ids


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_index(index: faiss.Index, restaurant_ids: list[str], path: str) -> None:
    """Save a FAISS index to *path* and a companion ``<path>.ids.json``."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    faiss.write_index(index, path)
    ids_path = path + ".ids.json"
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump(restaurant_ids, f)


def load_index(path: str) -> tuple[faiss.Index, list[str]]:
    """Load a FAISS index and its companion id-map from disk.

    Returns:
        (index, restaurant_ids)
    """
    index = faiss.read_index(path)
    ids_path = path + ".ids.json"
    with open(ids_path, "r", encoding="utf-8") as f:
        restaurant_ids: list[str] = json.load(f)
    return index, restaurant_ids


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_embedding_pipeline() -> None:
    """End-to-end: load restaurants from DB, embed, build index, save."""
    import asyncio

    async def _fetch_all() -> list[dict]:
        await initialize_database()
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM restaurants")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    restaurants = asyncio.run(_fetch_all())
    if not restaurants:
        print("No restaurants found in DB — run seed first.")
        return

    print(f"Embedding {len(restaurants)} restaurants …")
    index, ids = build_faiss_index(restaurants)

    path = get_faiss_index_path()
    save_index(index, ids, path)
    print(f"FAISS index saved to {path}  ({index.ntotal} vectors, dim={index.d})")
