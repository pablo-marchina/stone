import pytest

from tapi_gate0 import multimodal_cta_challenge as challenge
from tapi_gate0 import multimodal_semantic_replay as replay
from tapi_gate0.discovery_rubric_grounded import UNKNOWN


def ideal_rows():
    return [{"case_id":cid,"stratum":stratum,"expected":expected,
             "values":{v:expected for v in replay.VARIANTS}}
            for cid,stratum,expected,_ in challenge.CASES]


def test_fixed_partition_and_stratified_gate():
    rows=ideal_rows()
    assert len(rows)==24
    assert len({r["case_id"] for r in rows})==24
    assert all(x["engineering_gate_passed"] for x in challenge.score(rows).values())
    rows[6]["values"]["model_consensus"]=None
    rows[7]["values"]["model_consensus"]=None
    scores=challenge.score(rows)
    assert scores["model_consensus"]["strata"]["all"]["candidate_recall"]==10/12
    assert not scores["model_consensus"]["engineering_gate_passed"]
    assert scores["grounded_hybrid"]["engineering_gate_passed"]
    with pytest.raises(ValueError,match="PARTITION_MISMATCH"):
        challenge.score(rows[:-1])


def test_negative_false_candidate_blocks_variant():
    rows=ideal_rows()
    rows[-1]["values"]["model_consensus"]="seguir"
    r=challenge.score(rows)
    assert r["model_consensus"]["strata"]["negative"]["wrong_nonabstained"]==1
    assert not r["model_consensus"]["engineering_gate_passed"]


def test_real_rules_with_model_abstention(monkeypatch):
    monkeypatch.setattr(replay,"candidate",lambda *args:UNKNOWN)
    r=challenge.run_challenge(None)
    assert len(r["cases"])==24
    assert r["variants"]["grounded_hybrid"]["strata"]["all"]["correct_candidates"]==0
    assert not r["engineering_gate_passed"]
    assert not r["automatic_variant_selected"] and not r["real_media_processing_allowed"]
    assert r["reference_kind"]=="authored_text_surrogates_not_extracted_media"
    conflict=next(x for x in r["cases"] if x["case_id"]=="n09")
    assert all(v is None for v in conflict["values"].values())
    assert conflict["decisions"]["lexical"]["reason"]=="CONFLICTING_ANCHORS"


def test_cli_challenge_exclusive_and_refuses_existing_output(tmp_path,monkeypatch,capsys):
    from scripts import a6_semantic_replay as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    out=cli.local_report(tmp_path,"out.json",existing=False)
    out.write_text("preserved")
    args=["--cta-challenge","--report-name","out.json","--model-dir",str(tmp_path)]
    assert cli.main(args)==2
    assert out.read_text()=="preserved"
    assert "PRIVATE_REPORT_PATH_INVALID" in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        cli.main(args+["--input-name","input.json"])
    assert error.value.code==2
