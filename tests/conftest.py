"""Fixtures every test module shares."""
from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Async tests run on asyncio, as the shop does under uvicorn."""
    return "asyncio"
