"""
Module: tools/recommendations.py
Responsibility: Implements the search_restaurants tool — finds and ranks
restaurants using semantic search, structured filters, and a weighted
scoring matrix with diversity enforcement.
"""

from __future__ import annotations

import json
import traceback
from typing import Any

from database.queries import search_restaurants_structured, get_restaurant_by_id
from embeddings.semantic_search import semantic_search
from config.settings import get_faiss_index_path
from embeddings.embed_restaurants import load_index


def _safe_json_list(raw: Any) -> list[str]:
    """Parse a JSON-encoded list string, returning [] on failure."""
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _compute_scores(
    restaurant: dict,
    semantic_rank: int,
    total_candidates: int,
    dietary_requirements: list[str],
    ambiance_preferences: list[str],
    location_preference: str | None,
    price_hint: int | None,
    cuisine_preference: str | None = None,
    party_size: int | None = None,
) -> tuple[float, list[str]]:
    """Return (weighted_score, explanation_parts) for a restaurant.

    Scoring weights:
        Semantic similarity : 25%
        Dietary match       : 20%
        Cuisine match       : 15%
        Ambiance overlap    : 15%
        Location match      : 15%
        Price range fit     : 10%
    """

    explanations: list[str] = []

    # --- 1. Semantic similarity (25%) — inverse rank normalised ---
    sem_score = max(0.0, 1.0 - (semantic_rank / max(total_candidates, 1)))

    # --- 2. Dietary match (20%) ---
    certs = _safe_json_list(restaurant.get("dietary_certifications"))
    if dietary_requirements:
        matched_diet = [d for d in dietary_requirements if d in certs]
        diet_score = len(matched_diet) / len(dietary_requirements)
        for m in matched_diet:
            explanations.append(f"certified {m.replace('_', ' ')}")
    else:
        diet_score = 1.0  # no requirements = full match

    # --- 3. Cuisine type match (15%) ---
    rest_cuisine = (restaurant.get("cuisine_type") or "").lower()
    if cuisine_preference:
        pref_lower = cuisine_preference.lower()
        if pref_lower == rest_cuisine:
            cuisine_score = 1.0
            explanations.append(f"{restaurant.get('cuisine_type')} cuisine matches your preference")
        elif pref_lower in rest_cuisine or rest_cuisine in pref_lower:
            cuisine_score = 0.6  # partial match (e.g. "Indo-Chinese" vs "Chinese")
        else:
            cuisine_score = 0.0
    else:
        cuisine_score = 0.5  # neutral if no preference

    # --- 4. Ambiance overlap (15%) ---
    tags = _safe_json_list(restaurant.get("ambiance_tags"))
    if ambiance_preferences:
        matched_amb = [a for a in ambiance_preferences if a in tags]
        amb_score = len(matched_amb) / len(ambiance_preferences)
        for m in matched_amb:
            explanations.append(f"{m.replace('_', ' ')} setting")
    else:
        amb_score = 0.5

    # --- 5. Location match (15%) ---
    neighborhood = (restaurant.get("neighborhood") or "").lower()
    if location_preference:
        lp = location_preference.lower()
        if lp == neighborhood:
            loc_score = 1.0
            explanations.append(
                f"located in {restaurant.get('neighborhood')}"
            )
        elif lp in neighborhood or neighborhood in lp:
            loc_score = 0.6  # partial (e.g. "West" matches "West End")
        else:
            loc_score = 0.0
    else:
        loc_score = 0.5

    # --- 6. Price range (10%) ---
    price = restaurant.get("price_range", 2)
    if price_hint is not None:
        price_score = max(0.0, 1.0 - (abs(price - price_hint) / 3.0))
        price_labels = {1: "budget-friendly", 2: "moderately priced",
                        3: "upscale", 4: "fine dining"}
        if abs(price - price_hint) <= 1:
            explanations.append(price_labels.get(price, ""))
    else:
        price_score = 0.5

    # --- 7. Capacity awareness (bonus/penalty, not weighted) ---
    capacity = restaurant.get("total_capacity", 0)
    capacity_bonus = 0.0
    if party_size and capacity:
        if capacity >= party_size:
            capacity_bonus = 0.02  # small bonus for confirmed fit
        else:
            capacity_bonus = -0.10  # significant penalty if too small

    total = (
        0.25 * sem_score
        + 0.20 * diet_score
        + 0.15 * cuisine_score
        + 0.15 * amb_score
        + 0.15 * loc_score
        + 0.10 * price_score
        + capacity_bonus
    )
    total = max(0.0, min(1.0, total))  # clamp to [0, 1]

    if not explanations:
        explanations.append("matches your overall search criteria")

    return round(total, 4), explanations


def _extract_price_hint(query: str) -> int | None:
    """Heuristic: extract a rough price range from the query text."""
    q = query.lower()
    if any(k in q for k in ("cheap", "budget", "affordable", "inexpensive")):
        return 1
    if any(k in q for k in ("mid-range", "moderate", "casual")):
        return 2
    if any(k in q for k in ("upscale", "fine dining", "fancy", "luxury", "expensive")):
        return 4
    return None


def _apply_diversity(results: list[dict]) -> list[dict]:
    """If the top-3 all share the same cuisine, demote the 3rd."""
    if len(results) < 3:
        return results
    cuisines = [r["cuisine_type"] for r in results[:3]]
    if cuisines[0] == cuisines[1] == cuisines[2]:
        # Find next result with a different cuisine
        for i in range(3, len(results)):
            if results[i]["cuisine_type"] != cuisines[0]:
                demoted = results[2]
                results[2] = results[i]
                results[i] = demoted
                break
    return results


async def search_restaurants(params: dict) -> dict:
    """Search for restaurants matching guest preferences.

    Returns the standard tool response dict with up to 3 scored results.
    """
    try:
        query: str = params.get("query", "")
        party_size: int = params.get("party_size", 2)
        date: str = params.get("date", "")
        time: str = params.get("time", "")
        dietary_requirements: list[str] = params.get("dietary_requirements", [])
        location_preference: str | None = params.get("location_preference")
        cuisine_preference: str | None = params.get("cuisine_preference")
        ambiance_preferences: list[str] = params.get("ambiance_preferences", [])

        if not query:
            return {
                "success": False,
                "data": None,
                "error": "query is required",
                "error_code": "INVALID_INPUT",
            }

        # 1. Semantic search for candidates
        try:
            path = get_faiss_index_path()
            index, id_map = load_index(path)
            candidate_ids = semantic_search(
                query, top_k=20, index=index, restaurant_ids=id_map
            )
        except Exception:
            candidate_ids = []

        # 2. Structured filter
        structured = await search_restaurants_structured(
            cuisine_type=cuisine_preference,
            min_capacity=party_size,
            date=date,
            time=time,
            dietary_certifications=dietary_requirements,
        )
        structured_ids = {r["id"] for r in structured}
        structured_map = {r["id"]: r for r in structured}

        # Merge: keep candidates that also pass structured filter
        if candidate_ids and structured_ids:
            merged_ids = [cid for cid in candidate_ids if cid in structured_ids]
        elif candidate_ids:
            merged_ids = candidate_ids
        else:
            merged_ids = list(structured_ids)

        if not merged_ids:
            return {
                "success": True,
                "data": {"results": [], "total": 0},
                "error": None,
                "error_code": None,
            }

        # 3. Score and rank
        price_hint = _extract_price_hint(query)
        scored: list[dict] = []
        for rank, rid in enumerate(merged_ids):
            rest = structured_map.get(rid)
            if rest is None:
                rest = await get_restaurant_by_id(rid)
            if rest is None:
                continue

            score, explanation_parts = _compute_scores(
                rest, rank, len(merged_ids),
                dietary_requirements, ambiance_preferences,
                location_preference, price_hint,
                cuisine_preference=cuisine_preference,
                party_size=party_size,
            )
            scored.append({
                "restaurant_id": rest["id"],
                "name": rest["name"],
                "cuisine_type": rest.get("cuisine_type", ""),
                "neighborhood": rest.get("neighborhood", ""),
                "price_range": rest.get("price_range"),
                "ambiance_tags": _safe_json_list(rest.get("ambiance_tags")),
                "dietary_certifications": _safe_json_list(
                    rest.get("dietary_certifications")
                ),
                "description": rest.get("description", ""),
                "score": score,
                "explanation": "Recommended because: " + ", ".join(explanation_parts),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        # 4. Diversity penalty
        scored = _apply_diversity(scored)

        top_results = scored[:3]

        return {
            "success": True,
            "data": {"results": top_results, "total": len(scored)},
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
