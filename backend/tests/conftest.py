import pytest
from pathlib import Path
from app.core.db import set_db_path
from app.tools.migrate import migrate
from app.core.clock import Clock


@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path: Path):
    """Ensure every test runs in an isolated temporary SQLite database."""
    test_db = tmp_path / "test_mcvms.db"
    set_db_path(test_db)
    migrate(Clock())
    yield
    set_db_path(None)

