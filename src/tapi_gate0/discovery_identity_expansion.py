"""Offline CAP-001 expansion plan; never authorizes or executes a provider read."""
from collections import Counter, defaultdict

from sqlalchemy import select, func
from .business_discovery import IG_ID
from .connectors import ConnectorError, Platform
from .discovery_identity_a6 import identity_reserved_today, plan_identity
from .discovery_reconcile_a6 import _trace
from .discovery_auth_guard import require_auth_available
from .discovery_credential_expiry import expiry_status
from .discovery_recovery import inspect_recovery
from .ingestion import ingestion_runs, ingestion_records
from .sa_store import domain_events, outbox
from .storage import now_utc

VERSION = "bd-identity-expansion-coverage.v1"


def plan_expansion(engine, tenant, manifest, viewer, *, max_sources=3, daily_budget=80):
    """Rank unattempted candidates by coverage, preserving existing identity/grant guards."""
    if not IG_ID.fullmatch(viewer) or not 1 <= max_sources <= 5 or not 4 <= daily_budget <= 80:
        raise ConnectorError("BD_IDENTITY_INVALID_LIMITS",422)
    recovery=inspect_recovery(engine,tenant)
    if (recovery["lease"] or recovery["reserved_runs"] or recovery["orphan_runs_without_lease"]
            or recovery["quarantined_sources"]
            or any(not r["reviewed"] for r in recovery["latest_a5_blocked_runs"])):
        raise ConnectorError("BD_EXPANSION_RECOVERY_REQUIRED",409)
    day=now_utc().date().isoformat()
    with engine.connect() as db:
        require_auth_available(db,tenant)
        identity_used=identity_reserved_today(db,tenant,day)
        run_count=db.execute(select(func.count()).select_from(ingestion_runs).where(
            ingestion_runs.c.tenant_id==tenant,ingestion_runs.c.platform==Platform.INSTAGRAM.value,
            ingestion_runs.c.requested_at>=day)).scalar_one()
        counts=dict(db.execute(select(ingestion_records.c.source_account_id,func.count()).where(
            ingestion_records.c.tenant_id==tenant,ingestion_records.c.platform==Platform.INSTAGRAM.value,
            ingestion_records.c.metadata_only==1).group_by(ingestion_records.c.source_account_id)).all())
        rows=db.execute(select(domain_events,outbox.c.seq.label("outbox_seq")).outerjoin(
            outbox,outbox.c.seq==domain_events.c.seq).where(
            domain_events.c.tenant_id==tenant,domain_events.c.aggregate_type=="bd_identity")
            .order_by(domain_events.c.aggregate_id,domain_events.c.aggregate_version)).mappings().all()
    groups=defaultdict(list)
    for row in rows:
        groups[row["aggregate_id"]].append(row)
    attempted=defaultdict(list)
    known, ids = {}, {}
    for group in groups.values():
        reserve,result=_trace(group)
        name=reserve["username"].casefold()
        attempted[name].append((reserve,result))
        if result and result["status"]=="IDENTIFIED":
            ident=result["instagram_id"]
            if known.setdefault(name,ident)!=ident or ids.setdefault(ident,name)!=name:
                raise ConnectorError("BD_RECONCILE_IDENTITY_CONFLICT",409)
    approved=Counter()
    observed=Counter()
    posts=Counter()
    for source in manifest.sources:
        if source.status=="approved":
            approved[source.sampling_stratum]+=1
            count=counts.get(source.expected_ig_id,0)
            observed[source.sampling_stratum]+=int(count>0)
            posts[source.sampling_stratum]+=count
    eligible, deferred, pending = [], [], []
    for source in manifest.sources:
        name=source.username.casefold()
        if source.status not in ("candidate","review") or source.audience_intent=="not_mpe_targeted":
            continue
        if source.expected_ig_id==viewer or not source.audience_rationale_reference:
            deferred.append({"username":source.username,"reason":"MISSING_RATIONALE_OR_VIEWER"})
            continue
        previous=attempted.get(name,[])
        successes=[(p,r) for p,r in previous if r and r["status"]=="IDENTIFIED" and p["viewer_ig_id"]==viewer]
        if successes:
            ident=successes[0][1]["instagram_id"]
            if source.expected_ig_id and source.expected_ig_id!=ident:
                raise ConnectorError("BD_RECONCILE_IDENTITY_CONFLICT",409)
            matching_cycles=sorted({p["cycle_key"] for p,r in successes if p["manifest_sha256"]==manifest.fingerprint()})
            pending.append({"username":source.username,
                            "action":"PLAN_GRANT" if source.expected_ig_id else
                                     "RECONCILE_EXACT_MANIFEST" if matching_cycles else "REVIEW_PRIOR_MANIFEST",
                            "matching_cycles":matching_cycles})
            continue
        if previous:
            deferred.append({"username":source.username,"reason":"PRIOR_ATTEMPT_REVIEW_REQUIRED"})
            continue
        eligible.append(source)
    used=4*run_count+identity_used
    capacity=min(max_sources,max(0,10-identity_used),max(0,daily_budget-used))
    selected=[]
    selected_strata=Counter()
    while eligible and len(selected)<capacity:
        # Prefer a new stratum, then fewer observed/approved profiles and posts.
        # Declared audience only breaks ties; it is not a validated post label.
        source=min(eligible,key=lambda s:(selected_strata[s.sampling_stratum],
            observed[s.sampling_stratum],approved[s.sampling_stratum],
            s.audience_intent!="mpe_targeted",posts[s.sampling_stratum],s.username.casefold()))
        eligible.remove(source)
        selected.append(source)
        selected_strata[source.sampling_stratum]+=1
    names=[s.username for s in selected]
    if names:
        plan_identity(engine,tenant,manifest,viewer,names,daily_budget=daily_budget)
    return {"status":"EXPANSION_PLAN_READY" if names else "EXPANSION_NO_NEW_CANDIDATES",
            "policy_version":VERSION,"manifest_sha256":manifest.fingerprint(),"utc_day":day,
            "selected_sources":names,
            "selection_details":[{"username":s.username,"sampling_stratum":s.sampling_stratum,
                "declared_audience":s.audience_intent,"observed_profiles_in_stratum":observed[s.sampling_stratum],
                "approved_profiles_in_stratum":approved[s.sampling_stratum],
                "technical_posts_in_stratum":posts[s.sampling_stratum]} for s in selected],
            "pending_identity_actions":pending,
            "deferred":deferred,"remaining_unattempted_candidates":len(eligible),
            "identity_reserved_today":identity_used,"conservative_reserved_today":used,
            "daily_request_budget":daily_budget,"max_identity_requests":len(names),
            "meta_credential_expiry":expiry_status(),"external_data_accessed":False,
            "database_mutated":False,"grants_created":0,"scientific_admissions":0}
