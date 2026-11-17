"""A02.2: persistent asset-rights registry, trusted-host boundary only.

No HTTP write routes, no private keys, no automatic trust provisioning, no
download/processing. An independent trusted authority must be supplied by
the host; database rows alone cannot establish trust. Registry decisions
are preflights, not transferable credentials or a media PEP.
"""
from datetime import datetime
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import (Table, Column, String, Text, BigInteger, ForeignKeyConstraint,
                        select, insert, update)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from pydantic import ValidationError

from .asset_rights import (SignedGrant, SignedRevocations, TrustedAuthority,
    AssetIdentity, Permission, decide_asset, signed_bytes, _signature_ok, AssetRightsDenied)
from .sa_store import metadata, domain_events, outbox, content_items
from .ingestion import ingestion_records, source_grants
from .storage import now_utc
from .policy import Decision
from .domain import ContentItem

KEY = ("tenant_id","platform","issuer_id")
AUTH = "asset_rights_authorities"
REV = "asset_rights_revocations"
GRANTS = "asset_rights_grants"


def _key_columns():
    return [Column("tenant_id",String(128),primary_key=True),
            Column("platform",String(32),primary_key=True),
            Column("issuer_id",String(128),primary_key=True)]


def _authority_fk():
    return ForeignKeyConstraint(list(KEY),[AUTH+"."+k for k in KEY])


authorities = Table(AUTH,metadata,*_key_columns(),
    Column("key_sha256",String(64),nullable=False),
    Column("revision",BigInteger,nullable=False),
    Column("claims_sha256",String(64),nullable=False),
    ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"]))
revocations = Table(REV,metadata,*_key_columns(),
    Column("revision",BigInteger,primary_key=True),
    Column("claims_sha256",String(64),nullable=False),
    Column("payload",Text,nullable=False),_authority_fk())
grants = Table(GRANTS,metadata,*_key_columns(),
    Column("grant_id",String(128),primary_key=True),
    Column("content_id",String(128),nullable=False),
    Column("asset_id",String(128),nullable=False),
    Column("claims_sha256",String(64),nullable=False),
    Column("payload",Text,nullable=False),_authority_fk(),
    ForeignKeyConstraint(["tenant_id","content_id"],["content_items.tenant_id","content_items.id"]))


def _hash(claims):
    return sha256(signed_bytes(claims)).hexdigest()


def _fail(code):
    raise AssetRightsDenied(code)


def _where(table,key):
    return [table.c[k]==v for k,v in key.items()]


def _scope(anchor,tenant,platform):
    if anchor is None or (tenant,platform) not in anchor.tenant_platform_scope or len(anchor.public_key)!=32:
        _fail("ASSET_REGISTRY_TRUST_REQUIRED")
    return dict(tenant_id=tenant,platform=platform,issuer_id=anchor.issuer_id)


def _event(db,key,kind,identity,revision=None):
    # Only opaque identifiers and scope; no signed claims, paths, keys or proof.
    aggregate_id="rights."+sha256(json.dumps([key,kind,identity],sort_keys=True).encode()).hexdigest()[:40]
    seq=db.execute(insert(domain_events).values(event_id=str(uuid4()),
        tenant_id=key["tenant_id"],aggregate_type="asset_rights",
        aggregate_id=aggregate_id,event_type="asset_rights."+kind,
        aggregate_version=1,occurred_at=now_utc().isoformat(),
        payload=json.dumps({"platform":key["platform"],"revision":revision,
            "policy":"asset-rights.v1","operational_media_enabled":False}))).inserted_primary_key[0]
    db.execute(insert(outbox).values(seq=seq,attempts=0,dead_letter=0))


def _verify_state(anchor, state, now):
    rv=state.claims
    if rv.issuer_id!=anchor.issuer_id or not _signature_ok(anchor.public_key,rv,state.signature):
        _fail("ASSET_REGISTRY_SIGNATURE_INVALID")
    if not rv.issued_at<=now<rv.valid_until:
        _fail("ASSET_REGISTRY_REVOCATION_STALE")
    if rv.revision>2**63-1:
        _fail("ASSET_REGISTRY_REVISION_INVALID")


def _load_head(db,key,anchor,*,lock=False):
    query=select(authorities).where(*_where(authorities,key))
    if lock:
        query=query.with_for_update()
    row=db.execute(query).mappings().one_or_none()
    if row is None:
        _fail("ASSET_REGISTRY_AUTHORITY_NOT_REGISTERED")
    if row["key_sha256"]!=sha256(anchor.public_key).hexdigest():
        _fail("ASSET_REGISTRY_KEY_MISMATCH")
    # Exact independent host pin; no use while host/DB disagree (including
    # the interval between advancing DB state and persisting the host pin).
    if (row["revision"]!=anchor.min_revocation_revision or
        row["claims_sha256"]!=anchor.revocation_claims_sha256):
        _fail("ASSET_REGISTRY_ROLLBACK")
    item=db.execute(select(revocations).where(*_where(revocations,key),
        revocations.c.revision==row["revision"])).mappings().one_or_none()
    if item is None:
        _fail("ASSET_REGISTRY_STATE_MISSING")
    state=SignedRevocations.model_validate_json(item["payload"])
    if (state.claims.revision!=row["revision"] or _hash(state.claims)!=row["claims_sha256"]
            or item["claims_sha256"]!=row["claims_sha256"]
            or state.claims.issuer_id!=anchor.issuer_id
            or not _signature_ok(anchor.public_key,state.claims,state.signature)):
        _fail("ASSET_REGISTRY_STATE_CORRUPT")
    return row,state


def _source_bound(db,target,now):
    r,g,c=ingestion_records,source_grants,content_items
    join=r.join(g,(r.c.tenant_id==g.c.tenant_id)&(r.c.platform==g.c.platform)&
        (r.c.source_account_id==g.c.source_account_id)).join(c,
        (r.c.tenant_id==c.c.tenant_id)&(r.c.content_id==c.c.id))
    row=db.execute(select(g.c.approved_at,g.c.expires_at,g.c.technical_verified_at,g.c.enabled,
        c.c.origin,c.c.payload).select_from(join).where(r.c.tenant_id==target.tenant_id,
        r.c.platform==target.platform,r.c.source_account_id==target.source_account_id,
        r.c.source_item_id==target.source_item_id,r.c.content_id==target.content_id,
        r.c.metadata_only==1)).mappings().one_or_none()
    if row is None or row["origin"]!=target.platform or row["enabled"]!=1:
        return False
    try:
        approved,verified,expires=(datetime.fromisoformat(row[k]) for k in
            ("approved_at","technical_verified_at","expires_at"))
        post=ContentItem.model_validate_json(row["payload"])
        return (approved<=verified<=now<expires and post.tenant_id==target.tenant_id
            and post.content_id==target.content_id and post.origin.value==target.platform
            and not post.is_synthetic)
    except (ValueError,TypeError):
        return False


def _effective_anchor(anchor,row):
    return TrustedAuthority(anchor.issuer_id,anchor.public_key,anchor.tenant_platform_scope,
        row["revision"],row["claims_sha256"])


class AssetRightsRegistry:
    """Offline trusted host only; callers must never supply anchors via HTTP.

    The independent host pin must match the exact current DB head; persist
    it outside the DB after a verified advance. Recovery mismatch denies.
    No PEP is wired.
    """
    def __init__(self,engine):
        self.engine=engine

    def provision(self,anchor,tenant,platform,state:SignedRevocations):
        key=_scope(anchor,tenant,platform)
        _verify_state(anchor,state,now_utc())
        rv=state.claims
        digest=_hash(rv)
        if rv.revision!=anchor.min_revocation_revision or digest!=anchor.revocation_claims_sha256:
            _fail("ASSET_REGISTRY_INITIAL_PIN_MISMATCH")
        try:
            with self.engine.begin() as db:
                db.execute(insert(authorities).values(**key,key_sha256=sha256(anchor.public_key).hexdigest(),
                    revision=rv.revision,claims_sha256=digest))
                db.execute(insert(revocations).values(**key,revision=rv.revision,
                    claims_sha256=digest,payload=state.model_dump_json()))
                _event(db,key,"authority_registered",rv.revision,rv.revision)
        except IntegrityError as exc:
            raise AssetRightsDenied("ASSET_REGISTRY_PROVISION_CONFLICT") from exc

    def advance(self,anchor,tenant,platform,state:SignedRevocations):
        key=_scope(anchor,tenant,platform)
        _verify_state(anchor,state,now_utc())
        rv=state.claims
        digest=_hash(rv)
        try:
            with self.engine.begin() as db:
                old,previous=_load_head(db,key,anchor,lock=True)
                if rv.revision==old["revision"] and digest==old["claims_sha256"]:
                    return False
                if rv.revision<=old["revision"]:
                    _fail("ASSET_REGISTRY_REVISION_NOT_MONOTONIC")
                # Revocations are permanent in v1; reauthorization requires a
                # separate reviewed policy, not omission from the next list.
                for name in ("revoked_grant_ids","revoked_asset_ids","revoked_sources"):
                    if not set(getattr(previous.claims,name))<=set(getattr(rv,name)):
                        _fail("ASSET_REGISTRY_REVOCATION_REMOVAL")
                if rv.issued_at<previous.claims.issued_at:
                    _fail("ASSET_REGISTRY_REVOCATION_CLOCK_REGRESSION")
                changed=db.execute(update(authorities).where(*_where(authorities,key),
                    authorities.c.revision==old["revision"],
                    authorities.c.claims_sha256==old["claims_sha256"]).values(
                    revision=rv.revision,claims_sha256=digest))
                if changed.rowcount!=1:
                    _fail("ASSET_REGISTRY_CONCURRENT_UPDATE")
                db.execute(insert(revocations).values(**key,revision=rv.revision,
                    claims_sha256=digest,payload=state.model_dump_json()))
                _event(db,key,"revocations_advanced",rv.revision,rv.revision)
                return True
        except IntegrityError as exc:
            raise AssetRightsDenied("ASSET_REGISTRY_CONCURRENT_UPDATE") from exc

    def register_grant(self,anchor,grant:SignedGrant,*,verified_approval_digest:str):
        g=grant.claims
        t=g.target
        key=_scope(anchor,t.tenant_id,t.platform)
        # Digest is supplied by trusted host after external evidence review,
        # not derived from an untrusted caller's declaration.
        if verified_approval_digest!=g.approval_evidence_sha256:
            _fail("ASSET_REGISTRY_APPROVAL_MISMATCH")
        now=now_utc()
        try:
            with self.engine.begin() as db:
                head,state=_load_head(db,key,anchor,lock=True)
                if not _source_bound(db,t,now):
                    _fail("ASSET_REGISTRY_SOURCE_DENIED")
                decision=decide_asset(authority=_effective_anchor(anchor,head),
                    grant=grant,revocations=state,target=t,permission=g.permissions[0],now=now)
                if not decision.permitted:
                    _fail(decision.code)
                existing=db.execute(select(grants).where(*_where(grants,key),
                    grants.c.grant_id==g.grant_id)).mappings().one_or_none()
                if existing is not None:
                    if existing["payload"]!=grant.model_dump_json():
                        _fail("ASSET_REGISTRY_GRANT_ID_CONFLICT")
                    return False
                db.execute(insert(grants).values(**key,grant_id=g.grant_id,
                    content_id=t.content_id,asset_id=t.asset_id,claims_sha256=_hash(g),
                    payload=grant.model_dump_json()))
                _event(db,key,"grant_registered",g.grant_id)
                return True
        except IntegrityError as exc:
            raise AssetRightsDenied("ASSET_REGISTRY_GRANT_CONFLICT") from exc

    def decide(self,anchor,grant_id,target:AssetIdentity,permission:Permission):
        try:
            key=_scope(anchor,target.tenant_id,target.platform)
            now=now_utc()
            with self.engine.connect() as db:
                head,state=_load_head(db,key,anchor)
                if not _source_bound(db,target,now):
                    _fail("ASSET_REGISTRY_SOURCE_DENIED")
                row=db.execute(select(grants).where(*_where(grants,key),
                    grants.c.grant_id==grant_id)).mappings().one_or_none()
                if row is None:
                    _fail("ASSET_REGISTRY_GRANT_NOT_FOUND")
                grant=SignedGrant.model_validate_json(row["payload"])
                if (grant.claims.grant_id!=grant_id or _hash(grant.claims)!=row["claims_sha256"]
                        or grant.claims.target.content_id!=row["content_id"]
                        or grant.claims.target.asset_id!=row["asset_id"]):
                    _fail("ASSET_REGISTRY_GRANT_CORRUPT")
                return decide_asset(authority=_effective_anchor(anchor,head),
                    grant=grant,revocations=state,target=target,permission=permission,now=now)
        except AssetRightsDenied as exc:
            return Decision(False,str(exc),"Registro de direitos não permite a operação.")
        except (ValidationError,ValueError,TypeError,SQLAlchemyError):
            return Decision(False,"ASSET_REGISTRY_INVALID_STATE","Registro de direitos inválido.")
