from tapi_gate0.discovery_rubric_coverage import rubric_coverage
from tapi_gate0.domain import RUBRIC_FIELD_NAMES
import pytest


def row(cid,topic=None,cta=None,tier="unresolved"):
    return {"content_id":cid,"username":"fixture","format":"reels","caption_chars":42,
            "topic":topic,"cta":cta,"tier":tier}


def test_full_field_partition_and_unknown_not_false():
    r=rubric_coverage([row("a","vendas","salvar","semantic_consensus_only"),row("b")])
    assert r["field_count"]==20 and not r["candidate_labels_validated"]
    group=r["cohorts"]["technical_all"]
    fields={f["field"]:f["counts"] for f in group["fields"]}
    assert tuple(fields)==RUBRIC_FIELD_NAMES and all(sum(c.values())==2 for c in fields.values())
    assert group["total_rubric_cells"]==40
    assert group["metadata_observed_cells"]==2 and group["lexical_candidate_cells"]==3
    assert group["measurement_only_cells"]==2 and group["not_assessed_cells"]==33
    assert fields["tem_cta"]["not_assessed"]==1
    assert fields["tem_rosto"]["not_assessed"]==2
    assert fields["legenda_tamanho"]["measurement_only"]==2
    assert r["cohorts"]["semantic_exploratory"]["posts"]==1
    assert r["rubric_assessments_written"]==0


def test_empty_cohort_and_invalid_input():
    r=rubric_coverage([row("a")])
    assert r["cohorts"]["semantic_exploratory"]["total_rubric_cells"]==0
    with pytest.raises(ValueError,match="BD_EXPLORATORY_RUBRIC_INPUT_INVALID"):
        rubric_coverage([row("a"),row("a")])
    with pytest.raises(ValueError,match="BD_EXPLORATORY_RUBRIC_INPUT_INVALID"):
        rubric_coverage([{**row("a"),"caption_chars":0}])
