import json
import pytest

from tapi_gate0 import multimodal_semantic_replay as replay
from tapi_gate0 import multimodal_fusion as fusion
from tapi_gate0.discovery_rubric_grounded import UNKNOWN

ASSET="a"*64


def pred(modality,rule=UNKNOWN,model=UNKNOWN,reason="NO_UNAMBIGUOUS_ANCHOR"):
    return {"modality":modality,"rule":{"rule_value":rule,"reason":reason},
            "model_consensus":model,"grounded_hybrid":model if rule==model else UNKNOWN}


def test_model_only_can_explore_without_promoting_hybrid():
    rows=[pred("audio",model="salvar")]
    assert replay.select_field(rows,("audio",),"model_consensus")["value"]=="salvar"
    assert replay.select_field(rows,("audio",),"grounded_hybrid")["value"] is None
    assert replay.select_field(rows,("caption",),"model_consensus")["value"] is None


def test_lexical_conflict_survives_model_abstention():
    rows=[pred("caption","comentar","comentar"),pred("ocr","salvar")]
    for variant in replay.VARIANTS:
        assert replay.select_field(rows,fusion.MODALITIES,variant)["value"] is None


def test_context_and_model_disagreement():
    rows=[pred("audio","salvar","salvar"),pred("caption",reason="CONTEXT_GUARD")]
    assert replay.select_field(rows,fusion.MODALITIES,"grounded_hybrid")["reason"]=="CONTEXT_VETO"
    rows=[pred("audio","salvar","seguir")]
    assert replay.select_field(rows,fusion.MODALITIES,"model_consensus")["value"] is None
    assert replay.select_field(rows,fusion.MODALITIES,"lexical")["value"]=="salvar"


def test_prediction_pt_en_agreement(monkeypatch):
    f=fusion.fragment(ASSET,"audio","Salve este post.",{"test":True})
    monkeypatch.setattr(replay,"candidate",lambda *args:"salvar")
    r=replay.fragment_predictions(None,f,"tipo_cta")
    assert r["grounded_hybrid"]=="salvar"
    assert r["text_sha256"]==f["text_sha256"]
    monkeypatch.setattr(replay,"candidate",lambda model,field,text,language:"salvar" if language=="pt" else "seguir")
    assert replay.fragment_predictions(None,f,"tipo_cta")["model_consensus"]==UNKNOWN


def test_invalid_report_refused_before_model(tmp_path,monkeypatch,capsys):
    from scripts import a6_semantic_replay as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    private=tmp_path/"artifacts"/"private"
    private.mkdir(parents=True)
    (private/"input.json").write_text(json.dumps({"synthetic_only":False}))
    args=["--input-name","input.json","--report-name","out.json","--model-dir",str(tmp_path)]
    assert cli.main(args)==2
    result=json.loads(capsys.readouterr().out)
    assert result["stage"]=="report_validation"
    assert not (private/"out.json").exists()
    assert cli.main(["--input-name","../bad.json","--report-name","out.json","--model-dir",str(tmp_path)])==2


def test_existing_output_refused(tmp_path):
    from scripts import a6_semantic_replay as cli
    p=cli.local_report(tmp_path,"out.json",existing=False)
    p.write_text("old")
    with pytest.raises(ValueError,match="PRIVATE_REPORT_PATH_INVALID"):
        cli.local_report(tmp_path,"out.json",existing=False)
    assert p.read_text()=="old"
