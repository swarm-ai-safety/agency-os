"""Waitlist signup endpoint — public, no auth required."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/waitlist", tags=["waitlist"])

# Simple in-memory rate limit: max 5 signups per IP per hour
_rate_limit: OrderedDict[str, list[float]] = OrderedDict()
_rate_limit_lock = threading.Lock()
_RATE_LIMIT_WINDOW = 3600  # 1 hour
_RATE_LIMIT_MAX = 25
_MAX_IPS = 10_000

# Module-level DB connection — set via set_db()
_db: Any = None


def set_db(db: Any) -> None:
    global _db
    _db = db


class WaitlistSignup(BaseModel):
    email: EmailStr


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    with _rate_limit_lock:
        # LRU eviction
        while len(_rate_limit) > _MAX_IPS:
            _rate_limit.popitem(last=False)
        hits = _rate_limit.get(client_ip, [])
        hits = [t for t in hits if now - t < _RATE_LIMIT_WINDOW]
        if len(hits) >= _RATE_LIMIT_MAX:
            raise HTTPException(
                status_code=429, detail="Too many signups, try again later"
            )
        hits.append(now)
        _rate_limit[client_ip] = hits
        _rate_limit.move_to_end(client_ip)


@router.post("")
async def signup(body: WaitlistSignup, request: Request) -> dict[str, str]:
    """Add an email to the waitlist."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    if _db is not None:
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]
        _db.save_waitlist_signup(body.email, ip_hash)
    else:
        logger.info("Waitlist signup (no DB): %s", body.email)

    return {"status": "ok"}
