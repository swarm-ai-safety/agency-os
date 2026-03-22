"""Public pricing API router."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/pricing", tags=["pricing"])

# Cache the pricing schema in memory to avoid repeated file I/O
_pricing_schema: dict[str, Any] | None = None


def _load_pricing_schema() -> dict[str, Any]:
    """Load pricing schema from repo root pricing.schema.json."""
    global _pricing_schema

    if _pricing_schema is not None:
        return _pricing_schema

    # Find repo root (where pricing.schema.json lives)
    # Walk up from this file until we find pricing.schema.json
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        schema_path = parent / "pricing.schema.json"
        if schema_path.exists():
            with open(schema_path) as f:
                _pricing_schema = json.load(f)
            return _pricing_schema

    raise FileNotFoundError(
        "pricing.schema.json not found in repo root. "
        "This file should exist at the repository root."
    )


def _get_pricing_data() -> dict[str, Any]:
    """Internal function to load and format pricing data."""
    schema = _load_pricing_schema()
    # Return everything except the JSON Schema metadata fields ($schema, title, description)
    return {
        "plans": schema.get("plans", []),
        "models": schema.get("models", {}),
        "executionPricing": schema.get("executionPricing", []),
        "volumeDiscounts": schema.get("volumeDiscounts", []),
        "commonFeatures": schema.get("commonFeatures", {}),
        "metadata": schema.get("metadata", {}),
    }


@router.get("")
async def get_pricing() -> dict[str, Any]:
    """Get current pricing information (public endpoint, no auth required).

    Returns:
        Pricing schema with plans, models, execution pricing, volume discounts, and metadata.

    Example:
        GET /api/pricing

        Returns:
        {
          "plans": [...],
          "models": {...},
          "executionPricing": [...],
          "volumeDiscounts": [...],
          "commonFeatures": {...},
          "metadata": {...}
        }
    """
    try:
        return _get_pricing_data()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500, detail=f"Invalid pricing schema JSON: {e}"
        ) from e
