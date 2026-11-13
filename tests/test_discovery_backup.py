from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3

import pytest

from tapi_gate0.discovery_backup import BackupError, backup_and_restore_drill


def seed(path):
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
        CREATE TABLE alembic_version(version_num TEXT);
        INSERT INTO alembic_version VALUES ('0012_bd_history_checkpoints');
        CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);
        INSERT INTO tenants VALUES ('a'),('b');
        CREATE TABLE ingestion_records(tenant_id TEXT, platform TEXT, source_item_id TEXT,
             source_account_id TEXT, metadata_only INT);
        INSERT INTO ingestion_records VALUES ('a','instagram','p1','s1',1),
             ('a','instagram','p2','s1',1),('b','instagram','p3','s2',1);
        CREATE TABLE ingestion_runs(status TEXT);
        CREATE TABLE ingestion_source_grants(id INT);
        CREATE TABLE bd_cycle_leases(tenant_id TEXT);
        CREATE TABLE bd_history_checkpoints(id INT);
        CREATE TABLE domain_events(id INT);
        CREATE TABLE event_outbox(id INT);
        CREATE TABLE content_items(id INT PRIMARY KEY);
        CREATE TABLE metrics_snapshots(id INT REFERENCES content_items(id));
        INSERT INTO content_items VALUES (1);
        INSERT INTO metrics_snapshots VALUES (1);
        """)
        db.commit()
    return path


def modify(path, sql):
    with closing(sqlite3.connect(path)) as db:
        db.execute(sql)
        db.commit()


def test_backup_and_restore_verifies_counts_hash_and_original(tmp_path):
    source = seed(tmp_path / "source.sqlite3")
    before = source.read_bytes()
    dest = tmp_path / "backup.sqlite3"
    report = backup_and_restore_drill(source, dest, "a", stopped=True)
    assert report["status"] == "BACKUP_RESTORE_VERIFIED"
    assert report["backup_sha256"] == hashlib.sha256(dest.read_bytes()).hexdigest()
    assert report["inventory"]["tenant_coverage"]["unique_media_ids"] == 2
    assert report["inventory"]["table_counts"]["ingestion_records"] == 3
    assert source.read_bytes() == before and report["live_restore_performed"] is False
    assert list(tmp_path.glob("restore-drill-*")) == []


@pytest.mark.parametrize("sql,code", [
    ("INSERT INTO bd_cycle_leases VALUES ('b')", "BACKUP_ACTIVE_INGESTION"),
    ("INSERT INTO ingestion_runs VALUES ('reserved')", "BACKUP_ACTIVE_INGESTION"),
    ("UPDATE alembic_version SET version_num='old'", "BACKUP_MIGRATION_NOT_EXPECTED"),
    ("INSERT INTO metrics_snapshots VALUES (999)", "BACKUP_FOREIGN_KEYS_FAILED"),
    ("DROP TABLE bd_history_checkpoints", "BACKUP_SCHEMA_INCOMPLETE"),
])
def test_blocked_source_does_not_create_backup(tmp_path, sql, code):
    source = seed(tmp_path / "source.sqlite3")
    modify(source, sql)
    dest = tmp_path / "backup.sqlite3"
    with pytest.raises(BackupError, match=code):
        backup_and_restore_drill(source, dest, "a", stopped=True)
    assert not dest.exists()


def test_no_overwrite_or_live_restore(tmp_path):
    source = seed(tmp_path / "source.sqlite3")
    before = source.read_bytes()
    dest = tmp_path / "backup.sqlite3"
    dest.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        backup_and_restore_drill(source, dest, "a", stopped=True)
    assert dest.read_bytes() == b"existing"
    with pytest.raises(BackupError, match="BACKUP_INVALID_TARGET"):
        backup_and_restore_drill(source, source, "a", stopped=True)
    assert source.read_bytes() == before


def test_missing_confirmation_or_unknown_tenant(tmp_path):
    source = seed(tmp_path / "source.sqlite3")
    dest = tmp_path / "backup.sqlite3"
    with pytest.raises(BackupError, match="BACKUP_ALL_WRITERS_MUST_STOP"):
        backup_and_restore_drill(source, dest, "a", stopped=False)
    with pytest.raises(BackupError, match="BACKUP_TENANT_UNKNOWN"):
        backup_and_restore_drill(source, dest, "missing", stopped=True)
    assert not dest.exists()


def test_failed_copy_removes_only_new_destination(tmp_path, monkeypatch):
    source = seed(tmp_path / "source.sqlite3")
    before = source.read_bytes()
    dest = tmp_path / "backup.sqlite3"
    def fail(*args):
        raise BackupError("COPY_TEST_FAILURE")
    monkeypatch.setattr("tapi_gate0.discovery_backup._copy", fail)
    with pytest.raises(BackupError, match="COPY_TEST_FAILURE"):
        backup_and_restore_drill(source, dest, "a", stopped=True)
    assert not dest.exists() and source.read_bytes() == before


def test_wal_snapshot_includes_committed_data(tmp_path):
    source = seed(tmp_path / "source.sqlite3")
    dest = tmp_path / "backup.sqlite3"
    with closing(sqlite3.connect(source)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO ingestion_records VALUES ('a','instagram','p4','s1',1)")
        conn.commit()
        report = backup_and_restore_drill(source, dest, "a", stopped=True)
    assert report["inventory"]["tenant_coverage"]["unique_media_ids"] == 3


def test_cli_private_target_and_no_network(tmp_path, monkeypatch, capsys):
    import json
    from scripts import a6_backup_restore_drill as cli
    source = seed(tmp_path / "source.sqlite3")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setenv("TAPI_DATABASE_URL", "sqlite:///" + source.as_posix())
    monkeypatch.setenv("TAPI_TENANT_ID", "a")
    assert cli.main(["--output-name", "verified.sqlite3", "--confirm-all-writers-stopped"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "BACKUP_RESTORE_VERIFIED" and not report["external_data_accessed"]
    assert (tmp_path / "artifacts/private/verified.sqlite3").is_file()


def test_cli_rejects_path_traversal_and_missing_confirmation(tmp_path, monkeypatch, capsys):
    import json
    from scripts import a6_backup_restore_drill as cli
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    assert cli.main(["--output-name", "../outside.sqlite3", "--confirm-all-writers-stopped"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "BACKUP_PRIVATE_BASENAME_REQUIRED"
    assert cli.main(["--output-name", "valid.sqlite3"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "BACKUP_ALL_WRITERS_MUST_STOP"
    assert not (tmp_path / "artifacts").exists()
