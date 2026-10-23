"""Multi-tenant identity with revocable opaque sessions and least privilege.

No cloud/OAuth provider, credential export, automatic grants or paid integration.
Bootstrap is intentionally offline. Database is the authority for membership.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher, exceptions as argon_errors
from sqlalchemy import Table, Column, String, Text, Integer, BigInteger, ForeignKeyConstraint, UniqueConstraint, select, insert, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import and_
from pydantic import BaseModel, ConfigDict, Field

from .sa_store import metadata, tenants

users=Table("identity_users",metadata,
    Column("user_id",String(128),primary_key=True),
    Column("login",String(128),nullable=False,unique=True),
    Column("password_hash",Text,nullable=False),
    Column("disabled",Integer,nullable=False,default=0),
    Column("failed_attempts",Integer,nullable=False,default=0),
    Column("locked_until",String(48)))
memberships=Table("identity_memberships",metadata,
    Column("user_id",String(128),primary_key=True),
    Column("tenant_id",String(128),primary_key=True),
    Column("role",String(32),nullable=False),
    ForeignKeyConstraint(["user_id"],["identity_users.user_id"],ondelete="CASCADE"),
    ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"],ondelete="CASCADE"))
sessions=Table("identity_sessions",metadata,
    Column("token_hash",String(64),primary_key=True),
    Column("user_id",String(128),nullable=False),
    Column("tenant_id",String(128),nullable=False),
    Column("issued_at",String(48),nullable=False),
    Column("expires_at",String(48),nullable=False),
    Column("revoked_at",String(48)),
    ForeignKeyConstraint(["user_id","tenant_id"],["identity_memberships.user_id","identity_memberships.tenant_id"],ondelete="CASCADE"))

audit=Table("identity_audit",metadata,
    Column("seq",BigInteger().with_variant(Integer,"sqlite"),primary_key=True,autoincrement=True),
    Column("tenant_id",String(128)),
    Column("actor_id",String(128)),
    Column("action",String(80),nullable=False),
    Column("outcome",String(24),nullable=False),
    Column("recorded_at",String(48),nullable=False))

ROLES=frozenset({"admin","researcher","annotator","editor","viewer","service"})
# Roles are never supplied by API caller; they are read from durable memberships.
READ_ROLES=ROLES
WRITE_RESEARCH=frozenset({"admin","researcher","service"})
WRITE_ASSESSMENT=frozenset({"admin","researcher","annotator"})
WRITE_CREATIVE=frozenset({"admin","editor"})

class IdentityFailure(Exception):
    def __init__(self,code="UNAUTHORIZED",status=401):
        self.code,self.status=code,status
        super().__init__(code)

class Principal(BaseModel):
    model_config=ConfigDict(extra="forbid")
    actor_id:str
    tenant_id:str
    role:str

class LoginRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    username:str=Field(min_length=1,max_length=128)
    password:str=Field(min_length=1,max_length=1024)
    tenant_id:str=Field(min_length=1,max_length=128)

class SessionResponse(BaseModel):
    access_token:str
    token_type:str="bearer"
    expires_at:str

class MemberCreate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    user_id:str=Field(min_length=1,max_length=128)
    username:str=Field(min_length=3,max_length=128)
    password:str=Field(min_length=12,max_length=1024)
    role:str


def utcnow(): return datetime.now(timezone.utc)

def digest(token):return hashlib.sha256(token.encode("utf-8")).hexdigest()

class IdentityStore:
    def __init__(self,engine:Engine):
        self.engine=engine
        self.hasher=PasswordHasher(time_cost=2,memory_cost=10240,parallelism=2)

    def bootstrap(self,tenant_id,tenant_name,username,password,user_id="founder"):
        """Offline-only one-time command. Never expose as public HTTP endpoint."""
        if len(password)<12:raise ValueError("bootstrap password requires 12+ characters")
        with self.engine.begin() as db:
            # fail closed: never silently replace existing administrator credentials
            if db.execute(select(users.c.user_id).limit(1)).first():
                raise ValueError("identity already bootstrapped")
            db.execute(insert(tenants).values(tenant_id=tenant_id,name=tenant_name))
            db.execute(insert(users).values(user_id=user_id,login=username,password_hash=self.hasher.hash(password),
                                            disabled=0,failed_attempts=0))
            db.execute(insert(memberships).values(user_id=user_id,tenant_id=tenant_id,role="admin"))
            db.execute(insert(audit).values(tenant_id=tenant_id,actor_id=user_id,
                action="identity.bootstrap",outcome="succeeded",recorded_at=utcnow().isoformat()))

    def add_member(self,principal:Principal,payload:MemberCreate):
        if principal.role!="admin":raise IdentityFailure("FORBIDDEN",403)
        if payload.role not in ROLES:raise ValueError("invalid role")
        with self.engine.begin() as db:
            existing=db.execute(select(users.c.user_id).where(users.c.login==payload.username)).first()
            if existing:raise IdentityFailure("IDENTITY_CONFLICT",409)
            try:
                db.execute(insert(users).values(user_id=payload.user_id,login=payload.username,
                    password_hash=self.hasher.hash(payload.password),disabled=0,failed_attempts=0))
                db.execute(insert(memberships).values(user_id=payload.user_id,
                    tenant_id=principal.tenant_id,role=payload.role))
                db.execute(insert(audit).values(tenant_id=principal.tenant_id,actor_id=principal.actor_id,
                    action="identity.member_created",outcome="succeeded",recorded_at=utcnow().isoformat()))
            except IntegrityError as e:raise IdentityFailure("IDENTITY_CONFLICT",409) from e
        return {"user_id":payload.user_id,"role":payload.role,"tenant_id":principal.tenant_id}

    def login(self,username,password,tenant_id):
        # Generic error for nonexistent accounts, bad passwords or memberships.
        with self.engine.begin() as db:
            row=db.execute(select(users).where(users.c.login==username)).mappings().first()
            if row is None:raise IdentityFailure("INVALID_CREDENTIALS")
            now=utcnow()
            if row["disabled"] or (row["locked_until"] and datetime.fromisoformat(row["locked_until"])>now):
                raise IdentityFailure("INVALID_CREDENTIALS")
            try:
                self.hasher.verify(row["password_hash"],password)
            except (argon_errors.VerifyMismatchError,argon_errors.VerificationError,argon_errors.InvalidHashError):
                failed=row["failed_attempts"]+1
                db.execute(update(users).where(users.c.user_id==row["user_id"]).values(
                    failed_attempts=failed,locked_until=(now+timedelta(minutes=15)).isoformat() if failed>=5 else None))
                db.execute(insert(audit).values(tenant_id=tenant_id,actor_id=row["user_id"],
                    action="identity.login",outcome="denied",recorded_at=now.isoformat()))
                raise_after=True
            else:raise_after=False
            if raise_after:
                # Raising inside transaction would rollback brute-force counters.
                pass
            else:
                member=db.execute(select(memberships.c.role).where(memberships.c.user_id==row["user_id"],
                    memberships.c.tenant_id==tenant_id)).scalar_one_or_none()
                if member is None:raise IdentityFailure("INVALID_CREDENTIALS")
                db.execute(update(users).where(users.c.user_id==row["user_id"]).values(failed_attempts=0,locked_until=None))
                token=secrets.token_urlsafe(48)
                expiry=now+timedelta(hours=1)
                db.execute(insert(sessions).values(token_hash=digest(token),user_id=row["user_id"],
                    tenant_id=tenant_id,issued_at=now.isoformat(),expires_at=expiry.isoformat()))
                db.execute(insert(audit).values(tenant_id=tenant_id,actor_id=row["user_id"],
                    action="identity.login",outcome="succeeded",recorded_at=now.isoformat()))
        if raise_after:raise IdentityFailure("INVALID_CREDENTIALS")
        return SessionResponse(access_token=token,expires_at=expiry.isoformat())

    def resolve(self,token:str)->Principal:
        if not token or len(token)>256:raise IdentityFailure()
        with self.engine.connect() as db:
            row=db.execute(select(sessions.c.user_id,sessions.c.tenant_id,sessions.c.expires_at,
                                 sessions.c.revoked_at,users.c.disabled,memberships.c.role).join(
                users,users.c.user_id==sessions.c.user_id).join(
                memberships,and_(memberships.c.user_id==sessions.c.user_id,memberships.c.tenant_id==sessions.c.tenant_id)).where(
                sessions.c.token_hash==digest(token))).first()
        if not row or row.revoked_at or row.disabled or datetime.fromisoformat(row.expires_at)<=utcnow():
            raise IdentityFailure()
        return Principal(actor_id=row.user_id,tenant_id=row.tenant_id,role=row.role)

    def revoke(self,token:str,principal:Principal):
        with self.engine.begin() as db:
            db.execute(update(sessions).where(sessions.c.token_hash==digest(token),
                sessions.c.user_id==principal.actor_id,sessions.c.tenant_id==principal.tenant_id).values(
                revoked_at=utcnow().isoformat()))
            db.execute(insert(audit).values(tenant_id=principal.tenant_id,actor_id=principal.actor_id,
                action="identity.logout",outcome="succeeded",recorded_at=utcnow().isoformat()))


def permitted(principal:Principal,method:str,path:str)->bool:
    if method in {"GET","HEAD"}:
        return principal.role in READ_ROLES
    if method!="POST":return False
    if path=="/v1/policy/check":return principal.role in READ_ROLES
    if path.startswith("/v1/content/") and path.endswith("/assessments"):
        return principal.role in WRITE_ASSESSMENT
    if path=="/v1/creatives":return principal.role in WRITE_CREATIVE
    if path in {"/v1/creators","/v1/content","/v1/insights","/v1/analyses/rankings"} or (
        path.startswith("/v1/content/") and path.endswith("/metrics")):
        return principal.role in WRITE_RESEARCH
    # Explicitly deny all external actions regardless of role, until separate verified policy.
    return False