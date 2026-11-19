"""Shared pytest fixtures for Topo_Logic tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from topo_logic.infrastructure.config import AppSettings
from topo_logic.interfaces.api.app import create_app


@pytest.fixture()
def app_client(tmp_path: Path) -> Iterator[TestClient]:
    """Create an isolated FastAPI TestClient backed by a temporary Local-First directory."""
    settings = AppSettings(data_dir=tmp_path / "topo_data", max_upload_mb=10)
    app = create_app(settings)
    with TestClient(app) as client:
        yield client
