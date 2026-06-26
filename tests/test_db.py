from app.core import db


def test_metrics_empty_tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'test.db'))
    db.init_db()
    summary = db.metrics_summary()
    assert 'total_runs' in summary
