"""Create a private identity-only scope from an existing authorization, offline."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from pydantic import ValidationError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_identity_a6 import IdentityScope


def build_scope(manifest, tenant, viewer, handles, reference, expiry):
    names = [name.casefold() for name in handles]
    by_name = {source.username.casefold(): source for source in manifest.sources}
    if not 1 <= len(names) <= 5 or len(names) != len(set(names)):
        raise ValueError("SELECT_ONE_TO_FIVE_DISTINCT_SOURCES")
    if any(name not in by_name or by_name[name].status not in {"candidate", "review"}
           or by_name[name].audience_intent == "not_mpe_targeted"
           or by_name[name].expected_ig_id == viewer for name in names):
        raise ValueError("SOURCE_NOT_ELIGIBLE")
    expires_at = datetime.fromisoformat(expiry.strip())
    if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
        raise ValueError("FUTURE_TIMEZONE_AWARE_EXPIRY_REQUIRED")
    return IdentityScope(
        tenant_id=tenant, viewer_ig_id=viewer, manifest_sha256=manifest.fingerprint(),
        usernames=[by_name[name].username for name in names],
        approval_reference=reference.strip(), expires_at=expires_at,
        operation="business_discovery_identity_read",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create identity scope offline; not an authorization grant")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source", required=True, action="append")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        root = (Path(__file__).resolve().parents[1] / "artifacts" / "private").resolve()
        if not args.output.resolve().is_relative_to(root) or args.output.suffix.lower() != ".json":
            raise ValueError("PRIVATE_OUTPUT_REQUIRED")
        if args.output.exists():
            print(json.dumps({"status":"BLOCKED","code":"OUTPUT_ALREADY_EXISTS"}))
            return 2
        manifest = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        tenant, viewer = os.environ["TAPI_TENANT_ID"], os.environ["TAPI_META_IG_ID"]
        print("Use somente uma autorizacao existente, que cubra estes perfis e a operacao de identidade.")
        print("Perfis:", ", ".join(args.source))
        reference = input("Referencia real da autorizacao (Enter para cancelar): ").strip()
        if not reference:
            print("CANCELADO: nenhuma autorizacao informada.")
            return 2
        if len(reference) < 12:
            print("BLOQUEADO: referencia deve ter pelo menos 12 caracteres.")
            return 2
        expiry = input("Validade real (AAAA-MM-DDTHH:MM:SS-03:00; Enter para cancelar): ").strip()
        if not expiry:
            print("CANCELADO: nenhuma validade informada.")
            return 2
        scope = build_scope(manifest, tenant, viewer, args.source, reference, expiry)
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(scope.model_dump_json(indent=2))
        print(json.dumps({"status":"ESCOPO_VALIDADO","profiles":len(scope.usernames),
                          "operation":scope.operation,"external_data_accessed":False,"grants_created":0}))
        return 0
    except (EOFError, KeyboardInterrupt):
        print("\nCANCELADO: entrada interrompida.")
        return 2
    except (KeyError, ValueError, ValidationError, OSError):
        print(json.dumps({"status":"BLOCKED","code":"INVALID_SCOPE_INPUT_OR_OUTPUT",
                          "external_data_accessed":False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
