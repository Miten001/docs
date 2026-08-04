"""Shared pytest fixtures/configuration for the test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    """Ensure tests never pick up real credentials from the environment."""
    for var in (
        "FB_PAGE_ID",
        "FB_ACCESS_TOKEN",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "POSTS_PER_DAY",
        "OUTPUT_DIR",
        "TIMEZONE",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
