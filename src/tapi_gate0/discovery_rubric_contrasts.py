"""CAP-002/003: reaudited rubric candidates as a separate descriptive view.

Saved model outputs are not attested. Recompute deterministic spans, labels,
benchmark gates and partitions. Never replace canonical rubric or agent input.
"""
from collections import Counter, defaultdict
from hashlib import sha256
import re

from .discovery_rubric_benchmark import CASES, FIELDS, UNKNOWN
from .discovery_rubric_grounded import CHECK_CASES, VERSION, _metrics, rule_evidence
from .discovery_editorial_descriptive import _distribution, _top, MIN_PROFILE_POSTS

POLICY = "bd-exploratory-rubric-contrasts.v1"
VARIANTS = ("pt", "en", "consensus", "rule", "hybrid")


def _require(ok, code="BD_EXPLORATORY_RUBRIC_EVIDENCE_MISMATCH"):
    if not ok:
        raise ValueError(code)


def validate_field(text, field, saved):
    """Recreate the exact candidate record from caption and saved PT/EN labels."""
    _require(field in FIELDS and isinstance(saved, dict))
    rule = rule_evidence(field, text)
    allowed = {label[0] for label in FIELDS[field][2]} | {UNKNOWN}
    predictions = saved["predictions"]
    pt, en = predictions["pt"], predictions["en"]
    _require(isinstance(pt,str) and isinstance(en,str) and pt in allowed and en in allowed)
    consensus = pt if pt == en else UNKNOWN
    hybrid = consensus if consensus == rule["rule_value"] else UNKNOWN
    expected = {**rule, "field":field, "policy_version":VERSION,
                "predictions":{"pt":pt,"en":en,"consensus":consensus,
                               "rule":rule["rule_value"],"hybrid":hybrid},
                "candidate_value":hybrid,"candidate_kind":"caption_only_not_validated",
                "human_review":False,"scientific_admission":False}
    _require(saved == expected and saved["human_review"] is False and saved["scientific_admission"] is False)
    return hybrid


def _benchmark_gates(report):
    summary = report["synthetic_benchmark"]
    cases = report["cases"]
    _require(summary["rubric_benchmark_version"] == VERSION
             and summary["synthetic_cases"] == len(CASES)+len(CHECK_CASES)
             and summary["independent_gold"] is False and summary["scientifically_validated"] is False
             and summary["automatic_variant_selected"] is False
             and summary["real_caption_inference_allowed"] is False
             and summary["rubric_assessments_written"] == summary["scientific_admissions"] == 0)
    expected = {cid:(split,field,label,text)
                for split, fixtures in (("development",CASES),("additional_authored",CHECK_CASES))
                for cid,field,label,text in fixtures}
    _require(len(cases)==len(expected) and {r["case_id"] for r in cases}==set(expected))
    groups = defaultdict(list)
    for row in cases:
        split,field,label,text = expected[row["case_id"]]
        _require(row["split"]==split and row["field"]==field and row["expected"]==label)
        validate_field(text,field,{k:v for k,v in row.items() if k not in ("case_id","split","expected")})
        groups[split].append(row)
    splits = {split:{field:{v:_metrics([r for r in rows if r["field"]==field],v)
                            for v in VARIANTS} for field in FIELDS} for split,rows in groups.items()}
    gates = {field:all(m["expected_candidates"]>=2 and m["wrong_nonabstained"]==0
                      and 2*m["correct_candidates"]>=m["expected_candidates"]
                      for m in (s[field]["hybrid"] for s in splits.values())) for field in FIELDS}
    _require(splits==summary["splits"] and gates==summary["field_engineering_gate"])
    return gates


def report_rows(report, manifest_sha, *, model_revision, model_weights_sha256):
    _require(report["status"]=="GROUNDED_RUBRIC_PILOT_COMPLETED"
             and report["rubric_policy"]==VERSION and report["manifest_sha256"]==manifest_sha
             and report["model_revision"]==model_revision and report["model_weights_sha256"]==model_weights_sha256
             and bool(re.fullmatch(r"[a-f0-9]{40}",model_revision))
             and bool(re.fullmatch(r"[a-f0-9]{64}",model_weights_sha256))
             and report["local_caption_scope_allowed"] is True
             and report["local_caption_scope_policy"]=="dec018-bd-caption-research.v1"
             and all(report[k] is False for k in ("synthetic_only","database_mutated","external_data_accessed",
                        "scientifically_validated","candidate_labels_validated","automatic_variant_selected","media_modalities_assessed"))
             and all(report[k]==0 for k in ("scientific_admissions","human_reviews","rubric_assessments_written")),
             "BD_EXPLORATORY_RUBRIC_SCOPE_MISMATCH")
    fields = report["requested_fields"]
    _require(isinstance(fields,list) and fields and fields==sorted(set(fields)) and set(fields)<=set(FIELDS))
    gates = _benchmark_gates(report)
    _require(all(gates[f] for f in fields),"BD_EXPLORATORY_RUBRIC_GATE_MISMATCH")
    rows = report["private_evidence"]
    by_id = {r["content_id"]:r for r in rows}
    _require(rows and len(rows)==len(by_id)==report["assessed_captions"],
             "BD_EXPLORATORY_RUBRIC_PARTITION_MISMATCH")
    counts = {f:Counter() for f in fields}
    by_source = defaultdict(lambda:{f:Counter() for f in fields})
    for r in rows:
        _require(isinstance(r["username"],str) and r["username"] and isinstance(r["snapshot_id"],str)
                 and r["snapshot_id"] and [v["field"] for v in r["fields"]]==fields)
        for value in r["fields"]:
            field,label = value["field"],value["candidate_value"]
            _require(label in {x[0] for x in FIELDS[field][2]}|{UNKNOWN})
            counts[field][label]+=1
            by_source[r["username"]][field][label]+=1
    _require(counts==report["field_candidate_counts"] and by_source==report["per_source"])
    return fields,by_id


def revalidate_row(caption, content_id, username, snapshot_id, saved, fields):
    _require(saved["content_id"]==content_id and saved["username"]==username
             and saved["snapshot_id"]==snapshot_id and [v["field"] for v in saved["fields"]]==fields,
             "BD_EXPLORATORY_RUBRIC_STALE_OR_WRONG_SNAPSHOT")
    return {v["field"]:None if (label:=validate_field(caption,v["field"],v))==UNKNOWN else label
            for v in saved["fields"]}


def _agreement(rows, field, baseline):
    counts=Counter()
    for row in rows:
        a,b=row[baseline],row["grounded_rubric"][field]
        state = ("both_unknown" if a is None and b is None else
                 "baseline_only" if b is None else "grounded_only" if a is None else
                 "agree" if a==b else "disagree")
        counts[state]+=1
    return {k:counts[k] for k in ("both_unknown","baseline_only","grounded_only","agree","disagree")}



def _candidate_distribution(rows, top_ids, field):
    """Observed-only contrasts plus worst-case missingness bounds, not CIs.

    Unknowns can belong to any candidate category. For claim-only fields,
    a lack of detected claim cannot be interpreted as absence of the claim.
    """
    result = _distribution(rows,top_ids,field)
    top,rest = result["top"],result["rest"]
    for group in (top,rest):
        group["coverage_fraction"] = round(group["observed"]/group["posts"],6) if group["posts"] else None
    for comparison in result["comparisons"]:
        def bounds(group,count):
            if not group["posts"]:
                return None
            return [count/group["posts"],(count+group["unknown"])/group["posts"]]
        a,b = bounds(top,comparison["top_count"]),bounds(rest,comparison["rest_count"])
        comparison["top_full_population_share_bounds"] = [round(v,6) for v in a] if a is not None else None
        comparison["rest_full_population_share_bounds"] = [round(v,6) for v in b] if b is not None else None
        comparison["difference_missingness_bounds_pp"] = [round((a[0]-b[1])*100,6),
                                                           round((a[1]-b[0])*100,6)] if a is not None and b is not None else None
    return result

def analyze_rubric(rows, fields):
    """Same ER populations/top ranks, separate candidate-only observables."""
    _require(rows and len({r["content_id"] for r in rows})==len(rows)
             and all(set(r["grounded_rubric"])==set(fields) for r in rows))
    cohorts={"technical_all":rows,"semantic_exploratory":[r for r in rows
             if r["tier"] in ("grounded_positive","semantic_consensus_only")]}
    result={}
    for name, group in cohorts.items():
        flattened=[{**r,**{"rubric:"+f:r["grounded_rubric"][f] for f in fields}} for r in group]
        source=defaultdict(list)
        for r in flattened:
            source[r["username"]].append(r)
        supported=[r for g in source.values() if len(g)>=MIN_PROFILE_POSTS for r in g]
        global_ids={r["content_id"] for r in _top(flattened)}
        within_ids={r["content_id"] for g in source.values() if len(g)>=MIN_PROFILE_POSTS for r in _top(g)}
        result[name]={"posts":len(group),"profiles":len(source),"global_top_count":len(global_ids),
                      "within_profile_supported_posts":len(supported),"within_profile_top_count":len(within_ids),
                      "fields":{f:{"global":_candidate_distribution(flattened,global_ids,"rubric:"+f),
                                  "within_profile":_candidate_distribution(supported,within_ids,"rubric:"+f),
                                  "candidate_semantics":"caption_claim_only" if f in ("prova_social","oferta_ou_beneficio_explicito") else "caption_candidate",
                                  **({"baseline_agreement":_agreement(group,f,{"tema_principal":"topic","tipo_cta":"cta"}[f])}
                                     if f in ("tema_principal","tipo_cta") else {})}
                                for f in fields}}
    return {"policy_version":POLICY,"cohorts":result,"requested_fields":fields,
            "candidate_labels_validated":False,"model_predictions_reexecuted":False,
            "model_predictions_independently_verified":False,"scientific_admissions":0,
            "rubric_assessments_written":0,"causal_claims":False,"editorial_recommendations_generated":False,
            "agent_inputs_changed":False,"unknown_is_not_negative":True}
