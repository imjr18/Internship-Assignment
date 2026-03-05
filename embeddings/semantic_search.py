"""
Module: embeddings/semantic_search.py
Responsibility: Accepts a natural-language query, embeds it with the same
sentence-transformer model used at index time, and returns the top-k
nearest restaurant IDs from the FAISS index.
"""

from __future__ import annotations

import numpy as np
import faiss

from config.settings import get_faiss_index_path
from embeddings.embed_restaurants import load_embedding_model, load_index


def semantic_search(
    query: str,
    top_k: int = 10,
    index: faiss.Index | None = None,
    restaurant_ids: list[str] | None = None,
) -> list[str]:
    """Return up to *top_k* restaurant IDs ordered by semantic similarity
    to *query*.

    If *index* / *restaurant_ids* are not provided they are loaded from the
    default ``FAISS_INDEX_PATH``.

    Returns:
        List of restaurant UUID strings (length <= top_k).
    """
    if index is None or restaurant_ids is None:
        path = get_faiss_index_path()
        index, restaurant_ids = load_index(path)

    model = load_embedding_model()
    query_vec: np.ndarray = model.encode(query, convert_to_numpy=True)
    query_vec = query_vec.astype(np.float32).reshape(1, -1)

    # Clamp top_k to the number of indexed vectors
    k = min(top_k, index.ntotal)
    distances, indices = index.search(query_vec, k)

    results: list[str] = []
    for idx in indices[0]:
        if 0 <= idx < len(restaurant_ids):
            results.append(restaurant_ids[idx])
    return results
