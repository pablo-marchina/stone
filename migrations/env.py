"""Alembic migration runner: never store credentials in alembic.ini."""
import os
from alembic import context
from sqlalchemy import pool
from tapi_gate0.sa_store import metadata, engine_for
# import identity to register its tables in the shared metadata
from tapi_gate0 import identity, asset_rights_registry  # noqa: F401

config=context.config
target_metadata=metadata
url=os.environ.get("TAPI_DATABASE_URL")
if not url:
    raise RuntimeError("TAPI_DATABASE_URL must be set for migrations")

def run_offline():
    context.configure(url=url,target_metadata=target_metadata,literal_binds=True,compare_type=True)
    with context.begin_transaction():context.run_migrations()

def run_online():
    supplied=config.attributes.get("connection")
    if supplied is not None:
        # Trusted offline operator may own an explicit SQLite write transaction.
        # Alembic must not open another connection or commit that transaction.
        context.configure(connection=supplied,target_metadata=target_metadata,compare_type=True,
                          transactional_ddl=True)
        with context.begin_transaction():context.run_migrations()
        return
    engine=engine_for(url)
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction():context.run_migrations()
    engine.dispose()

if context.is_offline_mode():run_offline()
else:run_online()