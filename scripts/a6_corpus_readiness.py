"""Offline aggregate evidence-readiness report. Never reads provider or writes DB."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_corpus_readiness import readiness_report
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.sa_store import engine_for


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    engine = None
    try:
        url = validate_existing_database_url(os.environ.get("TAPI_DATABASE_URL", ""))
        tenant = os.environ.get("TAPI_TENANT_ID", "")
        viewer = os.environ.get("TAPI_META_IG_ID", "")
        if not tenant or not viewer:
            raise ValueError("MISSING_SCOPE")
        manifest = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        engine = engine_for(url)
        report = readiness_report(engine, tenant, manifest, viewer)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except ConnectorError as exc:
        code = exc.code
    except (OSError, ValueError, SQLAlchemyError, KeyError, TypeError, ImportError):
        code = "BD_CORPUS_READINESS_LOCAL_ERROR"
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status": "BLOCKED", "code": code, "external_data_accessed": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
