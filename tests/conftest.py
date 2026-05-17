"""Pytest configuration: keep tests free of the FastAPI test client where possible.

We use plain HTTP calls against a `TestClient` instance so the tests look the
same whether you're hitting the running uvicorn process or the in-process app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session")
def app_client():
    from fastapi.testclient import TestClient

    from app.backend.main import app

    # Drive the startup hooks (services init) by entering the context manager.
    with TestClient(app) as client:
        yield client
