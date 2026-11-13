"""A6 technical grant provisioning; offline plan, authenticated explicit execution."""
import argparse
import getpass
import json
import os
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_batch import BatchManifest
from tapi_gate0.discovery_grants_a6 import provision
from tapi_gate0.discovery_local_db import validate_existing_database_url
from tapi_gate0.identity import IdentityFailure, IdentityStore
from tapi_gate0.sa_store import engine_for


def main(argv=None):
    p = argparse.ArgumentParser(description="Provision technical-only grants under DEC-018, no network")
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--source",action="append",required=True)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--output",type=Path)
    p.add_argument("--admin",default="admin")
    args=p.parse_args(argv)
    engine=None
    try:
        root=(Path(__file__).resolve().parents[1]/"artifacts"/"private").resolve()
        if args.execute != bool(args.output) or (args.output and (not args.output.resolve().is_relative_to(root) or args.output.suffix.lower()!=".json")):
            raise ConnectorError("BD_GRANT_PRIVATE_OUTPUT_REQUIRED_FOR_EXECUTION",422)
        manifest=BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        tenant,viewer=os.environ["TAPI_TENANT_ID"],os.environ["TAPI_META_IG_ID"]
        engine=engine_for(validate_existing_database_url(os.environ["TAPI_DATABASE_URL"]))
        if not args.execute:
            _,result=provision(engine,tenant,viewer,manifest,args.source)
        else:
            args.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            # Reserve the name before committing grants. A failed/crashed write can
            # leave an empty output; rerun from original manifest with a fresh name.
            fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as stream:
                identity=IdentityStore(engine)
                session=identity.login(args.admin,getpass.getpass("Admin password: "),tenant)
                principal=identity.resolve(session.access_token)
                try:
                    updated,result=provision(engine,tenant,viewer,manifest,args.source,principal=principal)
                    stream.write(updated.model_dump_json(indent=2))
                finally:
                    identity.revoke(session.access_token,principal)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (ConnectorError,IdentityFailure) as exc:
        print(json.dumps({"status":"BLOCKED","code":exc.code,"external_data_accessed":False}))
        return 3
    except (KeyError,OSError,ValueError,ValidationError,SQLAlchemyError):
        print(json.dumps({"status":"BLOCKED","code":"BD_GRANT_INVALID_INPUT_OR_DATABASE","external_data_accessed":False}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__=="__main__":
    raise SystemExit(main())
