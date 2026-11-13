"""Offline A6.3: read persisted identities; optionally write an exclusive private manifest."""
import argparse
import json
import os
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.discovery_reconcile_a6 import reconcile_identities
from tapi_gate0.sa_store import engine_for


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reconcile A6 identities without network or database mutation")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cycle", action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    engine = None
    try:
        root = (Path(__file__).resolve().parents[1] / "artifacts" / "private").resolve()
        if args.output and (not args.output.resolve().is_relative_to(root) or args.output.suffix.lower() != ".json"):
            raise ConnectorError("BD_RECONCILE_PRIVATE_OUTPUT_REQUIRED", 422)
        manifest = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        engine = engine_for(validate_existing_database_url(os.environ["TAPI_DATABASE_URL"]))
        updated, result = reconcile_identities(engine, os.environ["TAPI_TENANT_ID"],
            os.environ["TAPI_META_IG_ID"], manifest, args.cycle)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(updated.model_dump_json(indent=2))
            result["status"] = "IDENTITIES_RECONCILED"
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ConnectorError as exc:
        print(json.dumps({"status":"BLOCKED", "code":exc.code, "external_data_accessed":False}))
        return 3
    except (KeyError, OSError, ValueError, ValidationError, SQLAlchemyError):
        print(json.dumps({"status":"BLOCKED", "code":"BD_RECONCILE_INVALID_INPUT_OR_DATABASE", "external_data_accessed":False}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
