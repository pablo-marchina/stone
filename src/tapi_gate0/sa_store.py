"""SQLAlchemy 2 transactional repository, shared by SQLite test and PostgreSQL.

All identifiers are scoped to a tenant by composite FKs. Domain events and outbox
are committed with each state mutation. No third party source is authorized here.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from sqlalchemy import (MetaData, Table, Column, String, Text, Integer, BigInteger,
                        ForeignKeyConstraint, UniqueConstraint, Index, create_engine,
                        event, select, insert, func, update, text)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from .storage import (LocalDomainStore, DuplicateDomainId, DomainIntegrityError,
                      DomainNotFound, now_utc)
from .domain import (Creator, ContentItem, MetricsCreate, RubricAssessment,
                     Insight, CreativeVersion, RankingRequest, RankingResult,
                     RankingRow)
from decimal import Decimal
from fractions import Fraction
from functools import cmp_to_key
from math import ceil

metadata = MetaData()
tenants = Table("tenants", metadata,
    Column("tenant_id", String(128), primary_key=True), Column("name", String(256), nullable=False))

def domain_table(name, *extra):
    cols=[Column("tenant_id",String(128),primary_key=True),
          Column("id",String(128),primary_key=True)]
    cols.extend(Column(field,String(256),nullable=False) for field in extra)
    cols.append(Column("payload",Text,nullable=False))
    constraints=[ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"],ondelete="RESTRICT")]
    if name=="content_items":
        constraints.append(ForeignKeyConstraint(["tenant_id","creator_id"],["creators.tenant_id","creators.id"]))
    if name in ("metrics_snapshots","rubric_assessments"):
        constraints.append(ForeignKeyConstraint(["tenant_id","content_id"],["content_items.tenant_id","content_items.id"]))
    if name=="creative_versions":
        constraints.append(ForeignKeyConstraint(["tenant_id","insight_id"],["insights.tenant_id","insights.id"]))
    return Table(name,metadata,*cols,*constraints)

creators=domain_table("creators","origin")
content_items=domain_table("content_items","creator_id","origin","published_at")
metrics_snapshots=domain_table("metrics_snapshots","content_id","observed_at")
rubric_assessments=domain_table("rubric_assessments","content_id","recorded_at")
insights=domain_table("insights")
creative_versions=domain_table("creative_versions","insight_id")
domain_events=Table("domain_events",metadata,
    Column("seq",BigInteger().with_variant(Integer,"sqlite"),primary_key=True,autoincrement=True),
    Column("event_id",String(36),nullable=False,unique=True),
    Column("tenant_id",String(128),nullable=False),
    Column("aggregate_type",String(80),nullable=False),
    Column("aggregate_id",String(128),nullable=False),
    Column("event_type",String(100),nullable=False),
    Column("aggregate_version",Integer,nullable=False),
    Column("occurred_at",String(40),nullable=False),
    Column("payload",Text,nullable=False),
    ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"]),
    UniqueConstraint("tenant_id","aggregate_type","aggregate_id","aggregate_version",name="uq_aggregate_version"))
Index("ix_domain_event_cursor",domain_events.c.tenant_id,domain_events.c.seq)
Index("ix_domain_metrics_timestamp",metrics_snapshots.c.tenant_id,metrics_snapshots.c.content_id,metrics_snapshots.c.observed_at)

outbox=Table("event_outbox",metadata,
    Column("seq",BigInteger,primary_key=True),
    Column("attempts",Integer,nullable=False,default=0),
    Column("delivered_at",String(40)),
    Column("last_error",String(200)),
    Column("dead_letter",Integer,nullable=False,default=0),
    ForeignKeyConstraint(["seq"],["domain_events.seq"],ondelete="CASCADE"))

TABLES={t.name:t for t in [creators,content_items,metrics_snapshots,rubric_assessments,insights,creative_versions]}


def engine_for(url: str) -> Engine:
    if not (url.startswith("sqlite:///") or url.startswith("postgresql+psycopg://")):
        raise ValueError("database URL must use SQLite for local tests or PostgreSQL psycopg for production")
    kwargs={"pool_pre_ping":True}
    if url=="sqlite:///:memory:": kwargs["poolclass"]=StaticPool
    engine=create_engine(url,**kwargs)
    if engine.dialect.name=="sqlite":
        @event.listens_for(engine,"connect")
        def set_fk(dbapi_conn, _):
            cur=dbapi_conn.cursor();cur.execute("PRAGMA foreign_keys=ON");cur.close()
    return engine


class SqlDomainStore(LocalDomainStore):
    """Full domain API backed by SQLAlchemy and a transactional event outbox.

    Inherits invariant validation and domain state transition methods, but NOT
    SQLite connection setup or any of its SQL operations.
    """
    def __init__(self, engine:Engine):
        self.engine=engine
        self.lock=RLock()

    def initialize(self):
        metadata.create_all(self.engine)

    def create_tenant(self, tenant_id:str, name:str):
        with self.engine.begin() as con:
            con.execute(insert(tenants).values(tenant_id=tenant_id,name=name))

    def _insert(self,table,item,aggregate_type,event_type,extra=()):
        id_value=next(getattr(item,k) for k in ("creator_id","content_id","snapshot_id","assessment_id","insight_id","creative_id") if hasattr(item,k) and
            ((table=="creators" and k=="creator_id") or (table=="content_items" and k=="content_id") or
             (table=="metrics_snapshots" and k=="snapshot_id") or (table=="rubric_assessments" and k=="assessment_id") or
             (table=="insights" and k=="insight_id") or (table=="creative_versions" and k=="creative_id")))
        values={"tenant_id":item.tenant_id,"id":id_value,"payload":item.model_dump_json()}
        values.update(dict(extra))
        try:
            with self.engine.begin() as con:
                con.execute(insert(TABLES[table]).values(**values))
                q=select(func.coalesce(func.max(domain_events.c.aggregate_version),0)).where(
                    domain_events.c.tenant_id==item.tenant_id,
                    domain_events.c.aggregate_type==aggregate_type,
                    domain_events.c.aggregate_id==id_value)
                next_v=con.execute(q).scalar_one()+1
                res=con.execute(insert(domain_events).values(
                    event_id=str(uuid4()),tenant_id=item.tenant_id,aggregate_type=aggregate_type,
                    aggregate_id=id_value,event_type=event_type,aggregate_version=next_v,
                    occurred_at=now_utc().isoformat(),payload=json.dumps({"source":"local_synthetic","record_id":id_value})))
                seq=res.inserted_primary_key[0]
                con.execute(insert(outbox).values(seq=seq,attempts=0,dead_letter=0))
        except IntegrityError as e:
            code=str(e.orig).lower()
            if "unique" in code or "duplicate" in code:
                raise DuplicateDomainId(f"{aggregate_type} identifier already exists") from e
            raise DomainIntegrityError("invalid domain relationship") from e
        return item

    def _get(self,table,model,tenant,id_value):
        t=TABLES[table]
        with self.engine.connect() as con:
            payload=con.execute(select(t.c.payload).where(t.c.tenant_id==tenant,t.c.id==id_value)).scalar_one_or_none()
        if payload is None:raise DomainNotFound(f"{table} record not found within tenant")
        return model.model_validate_json(payload)

    def latest_assessment(self,tenant,content_id):
        self.content(tenant,content_id)
        with self.engine.connect() as con:
            payload=con.execute(select(rubric_assessments.c.payload).where(
                rubric_assessments.c.tenant_id==tenant,rubric_assessments.c.content_id==content_id).order_by(
                rubric_assessments.c.recorded_at.desc(),rubric_assessments.c.id.desc()).limit(1)).scalar_one_or_none()
        if payload is None:raise DomainNotFound("no assessment found")
        return RubricAssessment.model_validate_json(payload)

    def events(self,tenant,after_seq=0,limit=100):
        with self.engine.connect() as con:
            rows=con.execute(select(domain_events).where(domain_events.c.tenant_id==tenant,
                domain_events.c.seq>after_seq).order_by(domain_events.c.seq).limit(limit)).mappings().all()
        return [{**dict(r),"payload":json.loads(r["payload"])} for r in rows]

    def ranking(self,request:RankingRequest, *, connection=None, lock_rows=False):
        if connection is None:
            with self.engine.connect() as con:
                return self.ranking(request, connection=con, lock_rows=False)
        if connection.engine is not self.engine:
            raise ValueError("RANKING_TRUSTED_CONNECTION_REQUIRED")
        # Locks are explicit opt-in for the atomic agent step. Existing
        # standalone ranking calls remain read-only and do not lock writers.
        con = connection
        posts_query=select(content_items.c.payload).where(
            content_items.c.tenant_id==request.tenant_id,
            content_items.c.origin==request.origin.value)
        metrics_query=select(metrics_snapshots.c.payload).where(
            metrics_snapshots.c.tenant_id==request.tenant_id)
        if lock_rows:
            posts_query=posts_query.with_for_update(read=True)
            metrics_query=metrics_query.with_for_update(read=True)
        posts=con.execute(posts_query).scalars().all()
        metrics=con.execute(metrics_query).scalars().all()
        latest={}
        for raw in metrics:
            m=MetricsCreate.model_validate_json(raw)
            if m.observed_at>request.as_of:continue
            old=latest.get(m.content_id)
            if old is None or (m.observed_at,m.snapshot_id)>(old.observed_at,old.snapshot_id):latest[m.content_id]=m
        excluded_recent=excluded_no_denom=excluded_no_metrics=0
        eligible=[]
        for raw in posts:
            c=ContentItem.model_validate_json(raw)
            if (request.as_of-c.published_at).total_seconds()<request.min_age_days*86400:
                excluded_recent+=1;continue
            m=latest.get(c.content_id)
            if m is None:excluded_no_metrics+=1;continue
            if m.follower_count==0:excluded_no_denom+=1;continue
            eligible.append((c,m,Fraction(m.likes+m.comments,m.follower_count)))
        def order(a,b):
            if a[2]!=b[2]:return -1 if a[2]>b[2] else 1
            return -1 if a[0].content_id<b[0].content_id else (1 if a[0].content_id>b[0].content_id else 0)
        eligible.sort(key=cmp_to_key(order))
        top=ceil(len(eligible)/10)
        rows=[RankingRow(content_id=c.content_id,creator_id=c.creator_id,likes=m.likes,comments=m.comments,
                         followers=m.follower_count,engagement_rate=Decimal(score.numerator)/Decimal(score.denominator),
                         snapshot_id=m.snapshot_id,is_top_decile=i<top)
              for i,(c,m,score) in enumerate(eligible)]
        return RankingResult(origin=request.origin,n_posts=len(rows),n_creators=len({r.creator_id for r in rows}),
            top_count=top,rows=rows,excluded_no_positive_denominator=excluded_no_denom,
            excluded_too_recent=excluded_recent,excluded_without_metrics=excluded_no_metrics)


class EventDispatcher:
    """At-least-once dispatcher; callbacks must be idempotent by event_id.

    Intended as an internal worker boundary, not a published external bus.
    Failed callbacks stay retryable until max_attempts; failures are dead-lettered.
    """
    def __init__(self,engine:Engine,max_attempts:int=5):
        self.engine=engine;self.max_attempts=max_attempts

    def deliver(self,handler,batch_size=100):
        if not 1<=batch_size<=500:raise ValueError("invalid batch_size")
        successes=failures=0
        with self.engine.connect() as con:
            rows=con.execute(select(domain_events,outbox.c.attempts).join(outbox,outbox.c.seq==domain_events.c.seq).where(
                outbox.c.delivered_at.is_(None),outbox.c.dead_letter==0).order_by(domain_events.c.seq).limit(batch_size)).mappings().all()
        for e in rows:
            try:
                handler({**{key:e[key] for key in ("seq","event_id","tenant_id","aggregate_type","aggregate_id","event_type","aggregate_version","occurred_at")},
                         "payload":json.loads(e["payload"])})
            except Exception as exc:
                with self.engine.begin() as con:
                    con.execute(update(outbox).where(outbox.c.seq==e["seq"],outbox.c.delivered_at.is_(None)).values(
                        attempts=e["attempts"]+1,last_error=type(exc).__name__,dead_letter=int(e["attempts"]+1>=self.max_attempts)))
                failures+=1
            else:
                with self.engine.begin() as con:
                    con.execute(update(outbox).where(outbox.c.seq==e["seq"],outbox.c.delivered_at.is_(None)).values(
                        delivered_at=now_utc().isoformat(),attempts=e["attempts"]+1))
                successes+=1
        return {"delivered":successes,"failed":failures}