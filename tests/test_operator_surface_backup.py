import shutil
from pathlib import Path

from utils import db as shared_db
from utils import operator_surface


def test_manual_backup_closes_sqlite_handles_before_cleanup(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("LOKI_DB_PATH", str(tmp_path / "bot.db"))

    shared_db.init_sync()

    result = operator_surface.create_manual_backup()

    assert result["ok"] is True
    backup_file = Path(result["backup"]["path"])
    assert backup_file.exists()
    shutil.rmtree(tmp_path)
    assert not tmp_path.exists()
