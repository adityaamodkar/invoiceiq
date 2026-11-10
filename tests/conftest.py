import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from database.db import reset_demo_data  # noqa: E402

SAMPLE = ROOT / "sample_documents" / "dell_inv_00418.pdf"


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """Isolated, freshly seeded SQLite database per test."""
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "test.db")
    reset_demo_data()
    return tmp_path / "test.db"


@pytest.fixture(scope="session")
def sample_bytes():
    return SAMPLE.read_bytes()
