"""Offline CLI: schema initialize and first admin; no network provisioning."""
from __future__ import annotations
import argparse
import getpass
import os
from pathlib import Path
from .sa_store import engine_for,SqlDomainStore
from .identity import IdentityStore


def main():
    cli=argparse.ArgumentParser(description="TAPI secure database offline operations")
    cli.add_argument("operation",choices=["init-db","bootstrap-admin"])
    cli.add_argument("--tenant",default="local-research")
    cli.add_argument("--tenant-name",default="Local synthetic research")
    cli.add_argument("--username",default="admin")
    cli.add_argument("--user-id",default="founder")
    args=cli.parse_args()
    url=os.environ.get("TAPI_DATABASE_URL")
    if not url:raise SystemExit("TAPI_DATABASE_URL must be set")
    engine=engine_for(url)
    if args.operation=="init-db":
        if os.getenv("TAPI_ALLOW_SCHEMA_INIT")!="1":
            raise SystemExit("Set TAPI_ALLOW_SCHEMA_INIT=1 explicitly for this schema operation")
        SqlDomainStore(engine).initialize()
        print("Database schema initialized. Review migrations before production use.")
    else:
        password=getpass.getpass("New admin password (12+ characters): ")
        IdentityStore(engine).bootstrap(args.tenant,args.tenant_name,args.username,password,args.user_id)
        print("Admin initialized; password never printed or persisted in plaintext.")

if __name__=="__main__":main()