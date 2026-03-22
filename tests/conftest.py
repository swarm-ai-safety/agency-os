"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def required_startup_env(monkeypatch, tmp_path):
    """Provide required startup env vars unless a test overrides them."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-key")
    if not os.environ.get("STRIPE_SECRET_KEY"):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_key")
    if not os.environ.get("DATABASE_PATH"):
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
