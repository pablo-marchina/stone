import copy
from collections import Counter

import pytest

from tapi_gate0.discovery_rubric_benchmark import CASES,FIELDS,UNKNOWN
from tapi_gate0.discovery_rubric_grounded import CHECK_CASES,VERSION,grounded_field,run_grounded_rubric_challenge
from tapi_gate0.discovery_rubric_contrasts import report_rows,revalidate_row,analyze_rubric

MANIFEST="c"*64
REVISION="a"*40
WEIGHTS="b"*64
FIELDS_REQUESTED=["tema_principal","tipo_cta"]
CAPTION="Comente sua dúvida sobre vendas."


class FixtureExtractor:
    """Synthetic oracle only for wiring; not model performance evidence."""
    def classify_text(self,text,heads):
        result={}
        for head,options in heads.items():
            field=next(f for f,(pt,en,_) in FIELDS.items() if head in (pt,en))
            labels=FIELDS[field][2]
            expected=next((label for _,f,label,t in CASES+CHECK_CASES if f==field and t==text),
                          {"tema_principal":"vendas","tipo_cta":"comentar"}.get(field,UNKNOWN))
            result[head]=next((label[1 if head==FIELDS[field][0] else 2]
                               for label in labels if label[0]==expected),options[-1])
        return result


def pilot_report():
    extractor=FixtureExtractor()
    challenge=run_grounded_rubric_challenge(extractor)
    cases=challenge.pop("cases")
    fields=[grounded_field(extractor,f,CAPTION) for f in FIELDS_REQUESTED]
    counts={v["field"]:{v["candidate_value"]:1} for v in fields}
    return {"status":"GROUNDED_RUBRIC_PILOT_COMPLETED","rubric_policy":VERSION,
            "manifest_sha256":MANIFEST,"model_revision":REVISION,"model_weights_sha256":WEIGHTS,
            "local_caption_scope_allowed":True,"local_caption_scope_policy":"dec018-bd-caption-research.v1",
            **dict.fromkeys(("synthetic_only","database_mutated","external_data_accessed",
                             "scientifically_validated","candidate_labels_validated",
                             "automatic_variant_selected","media_modalities_assessed"),False),
            "scientific_admissions":0,"human_reviews":0,"rubric_assessments_written":0,
            "requested_fields":FIELDS_REQUESTED,"synthetic_benchmark":challenge,"cases":cases,
            "assessed_captions":1,"private_evidence":[{"content_id":"post1","snapshot_id":"snapshot1",
             "username":"source1","fields":fields}],"field_candidate_counts":counts,
            "per_source":{"source1":counts}}


def parse(report):
    return report_rows(report,MANIFEST,model_revision=REVISION,model_weights_sha256=WEIGHTS)


def test_exact_report_and_candidate_replay():
    fields,rows=parse(pilot_report())
    assert fields==FIELDS_REQUESTED
    assert revalidate_row(CAPTION,"post1","source1","snapshot1",rows["post1"],fields)=={
        "tema_principal":"vendas","tipo_cta":"comentar"}


@pytest.mark.parametrize("change",["manifest","model","gate","fixture","counts","partition","scope"])
def test_report_rejects_unmatched_or_tampered_inputs(change):
    report=pilot_report()
    if change=="manifest":
        report["manifest_sha256"]="e"*64
    elif change=="model":
        report["model_weights_sha256"]="e"*64
    elif change=="gate":
        report["synthetic_benchmark"]["field_engineering_gate"]["tom"]=True
    elif change=="fixture":
        report["cases"][0]["evidence_spans"][0]["sha256"]="e"*64
    elif change=="counts":
        report["field_candidate_counts"]={}
    elif change=="partition":
        report["private_evidence"]*=2
    elif change=="scope":
        report["local_caption_scope_allowed"]=False
    with pytest.raises(ValueError,match="BD_EXPLORATORY_RUBRIC"):
        parse(report)


@pytest.mark.parametrize("change",["snapshot","caption","span","source","consensus"])
def test_row_rejects_stale_or_forged_evidence(change):
    fields,rows=parse(pilot_report())
    row=rows["post1"]
    caption,snapshot,username=CAPTION,"snapshot1","source1"
    if change=="snapshot":
        snapshot="new-snapshot"
    elif change=="caption":
        caption+="!"
    elif change=="span":
        row["fields"][0]["evidence_spans"][0]["end"]+=1
    elif change=="source":
        username="source2"
    elif change=="consensus":
        row["fields"][0]["predictions"]["consensus"]="marketing"
    with pytest.raises(ValueError,match="BD_EXPLORATORY_RUBRIC"):
        revalidate_row(caption,"post1",username,snapshot,row,fields)


def test_contrasts_keep_unknowns_and_rank_population():
    rows=[{"content_id":str(i),"username":"source1","tier":"semantic_consensus_only" if i<10 else "unresolved",
           "likes":100-i,"comments":0,"followers":1000,
           "topic":"vendas" if i<3 else None,"cta":None,
           "grounded_rubric":{"tema_principal":"vendas" if i==0 else None,"tipo_cta":None}}
          for i in range(20)]
    before=copy.deepcopy(rows)
    result=analyze_rubric(rows,FIELDS_REQUESTED)
    assert rows==before
    assert not result["agent_inputs_changed"] and not result["candidate_labels_validated"]
    technical=result["cohorts"]["technical_all"]
    assert technical["posts"]==20 and technical["global_top_count"]==2
    theme=technical["fields"]["tema_principal"]
    assert theme["global"]["top"]["observed"]==1 and theme["global"]["top"]["unknown"]==1
    assert theme["global"]["rest"]["unknown"]==18
    assert theme["global"]["comparisons"][0]["difference_percentage_points"] is None
    assert theme["baseline_agreement"]=={"both_unknown":17,"baseline_only":2,"grounded_only":0,"agree":1,"disagree":0}
    assert result["cohorts"]["semantic_exploratory"]["posts"]==10


def test_missingness_bounds_are_not_confidence_intervals():
    from tapi_gate0.discovery_rubric_contrasts import _candidate_distribution
    rows=[{"content_id":"a","username":"s","x":"positive_claim"},
          {"content_id":"b","username":"s","x":None},
          {"content_id":"c","username":"t","x":None},
          {"content_id":"d","username":"t","x":None}]
    r=_candidate_distribution(rows,{"a","b"},"x")
    assert r["top"]["coverage_fraction"]==0.5 and r["rest"]["coverage_fraction"]==0
    comparison=r["comparisons"][0]
    assert comparison["difference_percentage_points"] is None
    assert comparison["top_full_population_share_bounds"]==[0.5,1.0]
    assert comparison["rest_full_population_share_bounds"]==[0.0,1.0]
    assert comparison["difference_missingness_bounds_pp"]==[-50.0,100.0]


def test_cli_rubric_contrasts_cannot_write_studio(capsys):
    import json
    from scripts.a6_exploratory_ranking import main
    assert main(["--persist-studio-drafts","--rubric-input-name","pilot.json",
                 "--manifest","unused.json","--input-name","audience.json",
                 "--report-name","out.json"])==2
    report=json.loads(capsys.readouterr().out)
    assert report["code"]=="BD_EXPLORATORY_RUBRIC_READ_ONLY_REQUIRED"
    assert not report["database_mutated"] and not report["studio_write_attempted"]
