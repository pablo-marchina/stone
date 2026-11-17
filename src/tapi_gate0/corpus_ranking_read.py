"""Read-only ranking of the exact reaudited caption population.

Uses the existing ER and contrast algorithms; never a canonical scientific
ranking. Refuse the entire ranking if its pinned population is stale.
"""
from hashlib import sha256

from .connectors import ConnectorError
from .discovery_caption_research import require_scoped_research
from .discovery_corpus_readiness import readiness_report
from .discovery_audience_exploratory import summarize
from .discovery_editorial_descriptive import er, analyze_editorial, age_band, caption_features
from .discovery_rubric_contrasts import analyze_rubric
from .discovery_audience_signals import sampling_sector
from .classification import TOPICS, CTA

COHORTS = ("technical_all", "semantic_exploratory")
FIELDS = ("tema_principal","tipo_cta","prova_social","oferta_ou_beneficio_explicito")
VERSION = "external-exploratory-ranking-read.v1"


def _require(condition):
    if not condition:
        raise ConnectorError("EXPLORATORY_RANKING_STALE_REPLAY",409)


def rank_rows(rows, *, cohort, top_only, offset, limit):
    if cohort not in COHORTS or not 0 <= offset <= 10000 or not 1 <= limit <= 100:
        raise ConnectorError("EXPLORATORY_RANKING_QUERY_INVALID",422)
    _require(bool(rows) and len({r["content_id"] for r in rows}) == len(rows))
    summary = summarize(rows)
    editorial = analyze_editorial(rows)
    contrasts = analyze_rubric(rows,list(FIELDS))
    group = rows if cohort == COHORTS[0] else [
        r for r in rows if r["tier"] in ("grounded_positive","semantic_consensus_only")]
    ordered = sorted(group,key=lambda r:(-er(r),r["content_id"]))
    top = set(summary["top_ids_private"][cohort])
    within = set(editorial["private_rankings"][cohort].get("within_profile_top",[]))
    supported = set(editorial["private_rankings"][cohort].get("percentiles",{}))
    ranked = [{**{k:r[k] for k in ("content_id","username","format","tier","likes","comments","followers",
                "snapshot_id","observed_at","followers_measured_at","published_at")},
               "rank":i+1,"er_percent":round(float(er(r))*100,6),
               "top_decile":r["content_id"] in top,"within_profile_top":r["content_id"] in within,
               "within_profile_supported":r["content_id"] in supported}
              for i,r in enumerate(ordered)]
    visible = [r for r in ranked if r["top_decile"]] if top_only else ranked
    page = visible[offset:offset+limit]
    e = editorial["cohorts"][cohort]
    sensitivity = {k:e.get(k) for k in ("within_profile_min_posts","within_profile_supported_posts",
        "within_profile_supported_profiles","within_profile_top_count","top_overlap_count","top_jaccard",
        "global_top_profiles","leave_one_profile_out")}
    return {"schema_version":VERSION,"status":"ready","cohort":cohort,
        "ranking_policy":summary["policy_version"],"cohorts":{k:summary["cohorts"][k] for k in COHORTS},
        "audience_tiers":summary["tier_counts"],"sensitivity":sensitivity,
        "grounded_contrasts":contrasts["cohorts"][cohort]["fields"],
        "top_only":top_only,"total":len(visible),"offset":offset,"limit":limit,
        "next_offset":offset+len(page) if offset+len(page)<len(visible) else None,"items":page,
        "canonical":False,"scientific_admissions":0,"causal_claims":False,
        "model_predictions_reexecuted":False,"model_predictions_independently_verified":False,
        "database_mutated":False,"external_data_accessed":False}


def read_ranking(engine, tenant, replay, *, cohort, top_only, offset, limit):
    if replay is None or tenant != replay.config.tenant:
        return {"schema_version":VERSION,"status":"disabled"}
    config = replay.config
    require_scoped_research(engine,tenant,replay.frame,config.viewer)
    entries = replay._entries
    rows = []
    seen = set()
    from .corpus_inventory import _base, _snapshots
    from .storage import now_utc
    # Recheck the same visible inventory contract used by the detail route.
    now = now_utc()
    with engine.connect() as db:
        visible,_ = _base(db,tenant,now)
        visible = {p.content_id:(r,p,c) for r,p,c in visible if p.content_id in entries}
        _require(set(visible)==set(entries))
        snapshots = _snapshots(db,tenant,list(visible),now)
    def observe(source, post, metric):
        cid = post.content_id
        entry = entries.get(cid)
        _require(entry is not None and cid not in seen and cid in visible)
        r,p,c = visible[cid]
        current = snapshots[cid]
        _require(entry["source_account_id"]==source.expected_ig_id==r["source_account_id"]
            and post.caption==p.caption and post.media_type==p.media_type and post.published_at==p.published_at
            and sha256(post.caption.encode()).hexdigest()==entry["caption_sha256"]
            and metric.snapshot_id==entry["snapshot_id"] and bool(current)
            and sha256(metric.model_dump_json().encode()).hexdigest()==entry["snapshot_payload_sha256"]
            and current[0].model_dump_json()==metric.model_dump_json())
        seen.add(cid)
        rows.append({"content_id":cid,"username":source.username,"tier":entry["audience_tier"],
            "format":post.media_type.value,"published_at":post.published_at.isoformat(),
            "sector":sampling_sector(source.sampling_stratum),"likes":metric.likes,"comments":metric.comments,
            "followers":metric.follower_count,"snapshot_id":metric.snapshot_id,
            "observed_at":metric.observed_at.isoformat(),"followers_measured_at":metric.followers_measured_at.isoformat(),
            "grounded_rubric":{k:entry["fields"][k]["value"] for k in FIELDS},
            **caption_features(post.caption,TOPICS,CTA)})
    ready=readiness_report(engine,tenant,replay.frame,config.viewer,_record_observer=observe)
    _require(seen==set(entries) and len(seen)==ready["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"])
    require_scoped_research(engine,tenant,replay.frame,config.viewer)
    from datetime import datetime
    as_of=datetime.fromisoformat(ready["as_of"])
    for row in rows:
        row["age_band"]=age_band((as_of-datetime.fromisoformat(row["published_at"])).days)
    result=rank_rows(rows,cohort=cohort,top_only=top_only,offset=offset,limit=limit)
    return {**result,"as_of":ready["as_of"],"manifest_sha256":replay._provenance["manifest_sha256"],
            "audience_report_sha256":replay._provenance["audience_report_sha256"],
            "population_reaudited":len(seen),"denominator":"latest_observed_followers",
            "full_population_rechecked":True,
            "rubric_report_sha256":{k:config.topic_cta.digest if k in ("tema_principal","tipo_cta") else config.proof_offer.digest for k in FIELDS}}
