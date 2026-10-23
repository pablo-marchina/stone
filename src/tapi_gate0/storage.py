"""SQLite transactional local repository for the unified content domain.

No external data ingestion, services, cloud, or paid infrastructure. Audit events are
persisted atomically with mutations; SQLite is a local reference backend only.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
from functools import cmp_to_key
from math import ceil
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .domain import (
    ContentCreate, ContentItem, Creator, CreatorCreate, CreativeCreate, CreativeVersion,
    Insight, InsightCreate, MetricsCreate, Origin, RankingRequest, RankingResult,
    RankingRow, RubricAssessment, RubricAssessmentCreate,
)


class DuplicateDomainId(Exception):
    pass


class DomainNotFound(Exception):
    pass


class DomainIntegrityError(Exception):
    pass


def now_utc():
    return datetime.now(timezone.utc)


def serialized(obj):
    return obj.model_dump_json()


class LocalDomainStore:
    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript((Path(__file__).parent / "sql" / "0001_unified_local_domain.sql").read_text(encoding="utf-8"))
        self.conn.execute("INSERT OR IGNORE INTO tenants(tenant_id,name) VALUES (?,?)", ("local-research", "Local synthetic research only"))
        self.conn.commit()

    @contextmanager
    def transaction(self):
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def _event(self, conn, tenant, aggregate_type, aggregate_id, event_type, payload):
        latest = conn.execute(
            "SELECT COALESCE(MAX(aggregate_version), 0) FROM domain_events WHERE tenant_id=? AND aggregate_type=? AND aggregate_id=?",
            (tenant, aggregate_type, aggregate_id),
        ).fetchone()[0]
        conn.execute("""INSERT INTO domain_events(event_id,tenant_id,aggregate_type,aggregate_id,event_type,aggregate_version,occurred_at,payload)
                     VALUES(?,?,?,?,?,?,?,?)""",
            (str(uuid4()),tenant,aggregate_type,aggregate_id,event_type,latest+1,now_utc().isoformat(),json.dumps(payload)),
        )

    def _insert(self, table, item, aggregate_type, event_type, extra=()):
        id_value = (
            getattr(item, "creator_id", None) if table == "creators" else
            getattr(item, "content_id", None) if table == "content_items" else
            getattr(item, "snapshot_id", None) if table == "metrics_snapshots" else
            getattr(item, "assessment_id", None) if table == "rubric_assessments" else
            getattr(item, "insight_id", None) if table == "insights" else
            getattr(item, "creative_id", None)
        )
        columns = ["tenant_id", "id", *[x[0] for x in extra], "payload"]
        values = [item.tenant_id, id_value, *[x[1] for x in extra], serialized(item)]
        try:
            with self.transaction() as db:
                db.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join(['?']*len(columns))})", values)
                self._event(db,item.tenant_id,aggregate_type,id_value,event_type,{"source":"local_synthetic", "record_id":id_value})
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint" in str(exc):
                raise DuplicateDomainId(f"{aggregate_type} identifier already exists") from exc
            raise DomainIntegrityError("invalid domain relationship") from exc
        return item

    def _get(self, table, model, tenant, id_value):
        with self.lock:
            row = self.conn.execute(f"SELECT payload FROM {table} WHERE tenant_id=? AND id=?",(tenant,id_value)).fetchone()
        if row is None:
            raise DomainNotFound(f"{table} record not found within tenant")
        return model.model_validate_json(row[0])

    def creator(self, tenant, id_value):
        return self._get("creators",Creator,tenant,id_value)

    def content(self, tenant, id_value):
        return self._get("content_items",ContentItem,tenant,id_value)

    def insight(self, tenant, id_value):
        return self._get("insights",Insight,tenant,id_value)

    def creative(self, tenant, id_value):
        return self._get("creative_versions",CreativeVersion,tenant,id_value)

    def create_creator(self, item: CreatorCreate):
        obj=Creator(**item.model_dump(),created_at=now_utc())
        return self._insert("creators",obj,"creator","creator.created",[("origin",obj.origin.value)])

    def create_content(self, item: ContentCreate):
        creator=self.creator(item.tenant_id,item.creator_id)
        if creator.origin != item.origin:
            raise DomainIntegrityError("creator and content origin mismatch")
        obj=ContentItem(**item.model_dump(),created_at=now_utc())
        return self._insert("content_items",obj,"content_item","content.created",[("creator_id",obj.creator_id),("origin",obj.origin.value),("published_at",obj.published_at.isoformat())])

    def create_metrics(self,item: MetricsCreate):
        self.content(item.tenant_id,item.content_id)
        return self._insert("metrics_snapshots",item,"metrics_snapshot","metrics.observed",[("content_id",item.content_id),("observed_at",item.observed_at.isoformat())])

    def create_assessment(self,item: RubricAssessmentCreate):
        self.content(item.tenant_id,item.content_id)
        obj=RubricAssessment(**item.model_dump(),recorded_at=now_utc())
        return self._insert("rubric_assessments",obj,"rubric_assessment","rubric.assessed",[("content_id",item.content_id),("recorded_at",obj.recorded_at.isoformat())])

    def latest_assessment(self,tenant,content_id):
        self.content(tenant,content_id)
        with self.lock:
            row=self.conn.execute("SELECT payload FROM rubric_assessments WHERE tenant_id=? AND content_id=? ORDER BY recorded_at DESC,id DESC LIMIT 1",(tenant,content_id)).fetchone()
        if row is None: raise DomainNotFound("no assessment found")
        return RubricAssessment.model_validate_json(row[0])

    def create_insight(self,item: InsightCreate):
        for content_id in set(item.source_content_ids):
            self.content(item.tenant_id,content_id)
        obj=Insight(**item.model_dump(),created_at=now_utc())
        return self._insert("insights",obj,"insight","insight.created")

    def create_creative(self,item: CreativeCreate):
        insight=self.insight(item.tenant_id,item.based_on_insight_id)
        if not set(item.reference_content_ids).issubset(set(insight.source_content_ids)):
            raise DomainIntegrityError("creative references must come from the supporting insight")
        for content_id in set(item.reference_content_ids):
            self.content(item.tenant_id,content_id)
        obj=CreativeVersion(**item.model_dump(),created_at=now_utc())
        return self._insert("creative_versions",obj,"creative_version","creative.created",[("insight_id",obj.based_on_insight_id)])

    def lineage(self,tenant,creative_id):
        creative=self.creative(tenant,creative_id)
        insight=self.insight(tenant,creative.based_on_insight_id)
        return {"creative":creative,"insight":insight,
                "reference_content":[self.content(tenant,c) for c in creative.reference_content_ids]}

    def events(self,tenant,after_seq=0,limit=100):
        with self.lock:
            rows=self.conn.execute("""SELECT seq,event_id,aggregate_type,aggregate_id,event_type,aggregate_version,occurred_at,payload
                                      FROM domain_events WHERE tenant_id=? AND seq>? ORDER BY seq LIMIT ?""",(tenant,after_seq,limit)).fetchall()
        return [{**dict(row),"payload":json.loads(row["payload"])} for row in rows]

    def ranking(self,request: RankingRequest):
        with self.lock:
            posts=self.conn.execute("SELECT payload FROM content_items WHERE tenant_id=? AND origin=?",(request.tenant_id,request.origin.value)).fetchall()
            metrics=self.conn.execute("SELECT payload FROM metrics_snapshots WHERE tenant_id=?",(request.tenant_id,)).fetchall()
        parsed_metrics=[MetricsCreate.model_validate_json(x[0]) for x in metrics]
        latest={}
        for m in parsed_metrics:
            if m.observed_at > request.as_of:
                continue
            old=latest.get(m.content_id)
            if old is None or (m.observed_at,m.snapshot_id) > (old.observed_at,old.snapshot_id):
                latest[m.content_id]=m
        age_excluded, denominator_excluded, no_metrics=0,0,0
        eligible=[]
        for r in posts:
            c=ContentItem.model_validate_json(r[0])
            if (request.as_of-c.published_at).total_seconds() < request.min_age_days*86400:
                age_excluded+=1
                continue
            m=latest.get(c.content_id)
            if m is None:
                no_metrics+=1
                continue
            if m.follower_count == 0:
                denominator_excluded+=1
                continue
            eligible.append((c,m,Fraction(m.likes+m.comments,m.follower_count)))
        def compare(a,b):
            if a[2] != b[2]:
                return -1 if a[2] > b[2] else 1
            return -1 if a[0].content_id < b[0].content_id else (1 if a[0].content_id > b[0].content_id else 0)
        eligible.sort(key=cmp_to_key(compare))
        n_top=ceil(len(eligible)/10)
        rows=[RankingRow(content_id=c.content_id,creator_id=c.creator_id,likes=m.likes,comments=m.comments,
                         followers=m.follower_count,engagement_rate=Decimal(frac.numerator)/Decimal(frac.denominator),
                         snapshot_id=m.snapshot_id,is_top_decile=i<n_top)
              for i,(c,m,frac) in enumerate(eligible)]
        return RankingResult(origin=request.origin,n_posts=len(rows),n_creators=len({r.creator_id for r in rows}),
                             top_count=n_top,rows=rows,excluded_no_positive_denominator=denominator_excluded,
                             excluded_too_recent=age_excluded,excluded_without_metrics=no_metrics)
