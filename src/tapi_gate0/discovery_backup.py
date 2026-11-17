"""Local SQLite snapshot + isolated restore drill; no production restore or network."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import shutil
import struct
import tempfile
import time


class BackupError(ValueError):
    pass


REQUIRED = {"alembic_version", "tenants", "ingestion_records", "ingestion_runs",
            "ingestion_source_grants", "bd_cycle_leases", "bd_history_checkpoints",
            "domain_events", "event_outbox", "content_items", "metrics_snapshots"}


def _readonly(path: Path):
    return sqlite3.connect(path.resolve(strict=True).as_uri() + "?mode=ro", uri=True, timeout=5)


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_fingerprint(conn, name):
    """Compare logical values, not SQLite file layout or only row counts.

    Row hashes are sorted as bytes (multiset, including duplicates), then
    aggregated; no individual row, credential or row hash is returned.
    """
    hashes = []
    for row in conn.execute("SELECT * FROM " + _identifier(name)):
        h = hashlib.sha256()
        for value in row:
            if value is None:
                tag, raw = b"N", b""
            elif isinstance(value, bytes):
                tag, raw = b"B", value
            elif isinstance(value, str):
                tag, raw = b"T", value.encode("utf-8")
            elif isinstance(value, int):
                tag, raw = b"I", str(value).encode("ascii")
            elif isinstance(value, float):
                tag, raw = b"F", struct.pack(">d", value)
            else:
                raise BackupError("BACKUP_UNSUPPORTED_SQLITE_VALUE")
            h.update(tag)
            h.update(len(raw).to_bytes(8, "big"))
            h.update(raw)
        hashes.append(h.digest())
    total = hashlib.sha256(b"tapi-sqlite-table-multiset.v1")
    total.update(len(hashes).to_bytes(8, "big"))
    for digest in sorted(hashes):
        total.update(digest)
    return len(hashes), total.hexdigest()


def _inventory(conn, tenant: str) -> dict:
    schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                          "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
    tables = {name for kind, name, _, _ in schema if kind == "table"}
    if not REQUIRED <= tables:
        raise BackupError("BACKUP_SCHEMA_INCOMPLETE")
    if conn.execute("SELECT 1 FROM tenants WHERE tenant_id=?", (tenant,)).fetchone() is None:
        raise BackupError("BACKUP_TENANT_UNKNOWN")
    if (conn.execute("SELECT 1 FROM bd_cycle_leases LIMIT 1").fetchone() or
            conn.execute("SELECT 1 FROM ingestion_runs WHERE status='reserved' LIMIT 1").fetchone()):
        raise BackupError("BACKUP_ACTIVE_INGESTION")
    versions = [r[0] for r in conn.execute("SELECT version_num FROM alembic_version ORDER BY version_num")]
    if versions != ["0012_bd_history_checkpoints"]:
        raise BackupError("BACKUP_MIGRATION_NOT_EXPECTED")
    fingerprints = {name: _table_fingerprint(conn, name) for name in sorted(tables)}
    counts = {name: value[0] for name, value in fingerprints.items()}
    table_hashes = {name: value[1] for name, value in fingerprints.items()}
    records, unique, profiles = conn.execute(
        "SELECT count(*),count(DISTINCT source_item_id),count(DISTINCT source_account_id) "
        "FROM ingestion_records WHERE tenant_id=? AND platform='instagram' AND metadata_only=1",
        (tenant,)).fetchone()
    return {"schema_sha256": hashlib.sha256(json.dumps(schema, ensure_ascii=False).encode()).hexdigest(),
            "migration_versions": versions, "table_counts": counts,
            "table_content_sha256": table_hashes,
            "tenant_coverage": {"technical_records": records, "unique_media_ids": unique,
                                "profiles_with_technical_records": profiles,
                                "cross_source_duplicate_records": records - unique}}


def _integrity(conn):
    if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise BackupError("BACKUP_INTEGRITY_FAILED")
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise BackupError("BACKUP_FOREIGN_KEYS_FAILED")


def _copy(src, dst, timeout_seconds=120):
    deadline = time.monotonic() + timeout_seconds
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise BackupError("BACKUP_COPY_TIMEOUT")
    src.backup(dst, pages=128, progress=progress, sleep=0.05)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup_and_restore_drill(source: Path, destination: Path, tenant: str, *, stopped: bool) -> dict:
    """Copy all tenants as OS operator, verify a separate disposable restored DB.

    The caller must stop all writers, including non-ingestion processes. SQLite
    backup provides a consistent snapshot; this is not a distributed write lock.
    Never restores over the live source, and never overwrites an existing file.
    """
    if not stopped:
        raise BackupError("BACKUP_ALL_WRITERS_MUST_STOP")
    if not tenant or not source.is_file() or destination.suffix.lower() != ".sqlite3":
        raise BackupError("BACKUP_INVALID_TARGET")
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if destination.resolve() == source or not destination.parent.is_dir():
        raise BackupError("BACKUP_INVALID_TARGET")
    started = time.monotonic()
    captured_at = datetime.now(timezone.utc).isoformat()
    created = False
    try:
        with closing(_readonly(source)) as live:
            # Freeze one SQLite read snapshot for inventory and backup.
            live.execute("BEGIN")
            pages = live.execute("PRAGMA page_count").fetchone()[0]
            page_size = live.execute("PRAGMA page_size").fetchone()[0]
            # Reserve room for both the retained copy and disposable restore.
            if shutil.disk_usage(destination.parent).free < 2 * pages * page_size + 64 * 1024 * 1024:
                raise BackupError("BACKUP_STORAGE_INSUFFICIENT")
            inventory = _inventory(live, tenant)
            _integrity(live)
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            os.close(fd)
            with closing(sqlite3.connect(destination, timeout=5)) as target:
                _copy(live, target)
        with closing(_readonly(destination)) as saved:
            _integrity(saved)
            if _inventory(saved, tenant) != inventory:
                raise BackupError("BACKUP_INVENTORY_MISMATCH")
            backup_elapsed_ms = round((time.monotonic() - started) * 1000)
            restore_start = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="restore-drill-", dir=destination.parent) as tmp:
                restored = Path(tmp) / "restored.sqlite3"
                with closing(sqlite3.connect(restored, timeout=5)) as target:
                    _copy(saved, target)
                with closing(_readonly(restored)) as check:
                    _integrity(check)
                    if _inventory(check, tenant) != inventory:
                        raise BackupError("RESTORE_INVENTORY_MISMATCH")
            restore_elapsed_ms = round((time.monotonic() - restore_start) * 1000)
        return {"schema_version": "tapi-sqlite-backup-drill.v2", "status": "BACKUP_RESTORE_VERIFIED",
                "captured_at": captured_at, "backup_name": destination.name,
                "backup_sha256": _sha256(destination), "backup_bytes": destination.stat().st_size,
                "backup_elapsed_ms": backup_elapsed_ms, "restore_drill_elapsed_ms": restore_elapsed_ms,
                "integrity_check": "ok", "foreign_key_check": "ok", "inventory_matches": True,
                "logical_table_contents_match": True,
                "logical_fingerprint_kind": "typed_row_multiset_sha256.v1",
                "restore_target_disposable": True, "live_restore_performed": False,
                "scope": "all_tenants_private_os_operator", "all_writers_stopped_attested": True,
                "inventory": inventory, "external_data_accessed": False,
                "production_approved": False, "scientific_admissions": 0,
                "production_rpo_rto_measured": False}
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
