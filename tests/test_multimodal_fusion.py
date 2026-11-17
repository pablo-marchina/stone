import hashlib
import json
import shutil

import pytest

from tapi_gate0 import multimodal_fusion as fusion
from tapi_gate0 import multimodal_shared_fixture as shared
from tapi_gate0.domain import RUBRIC_FIELD_NAMES

ASSET="a"*64


def frag(modality,text,eligible=True):
    return fusion.fragment(ASSET,modality,text,{"synthetic_test":True},semantic_eligible=eligible)


def test_separate_modalities_conflict_and_ablation():
    parts=[frag("caption","Comente sua dúvida abaixo."),frag("ocr","Salve para revisar depois")]
    result=fusion.fuse(ASSET,parts)
    assert result["tipo_cta"]["value"] is None
    assert result["tipo_cta"]["reason"]=="CONFLICTING_ANCHORS"
    assert result["tem_cta"]["value"] is None
    assert fusion.fuse(ASSET,parts,("caption",))["tipo_cta"]["value"]=="comentar"
    assert fusion.fuse(ASSET,parts,("ocr",))["tipo_cta"]["value"]=="salvar"
    assert result["texto_na_tela"]["value"] is True
    assert set(result)==set(RUBRIC_FIELD_NAMES)


def test_agreement_supports_and_context_veto():
    parts=[frag("caption","Salve este post."),frag("audio","Salve este conteúdo.")]
    result=fusion.fuse(ASSET,parts)
    assert result["tipo_cta"]["value"]=="salvar" and result["tem_cta"]["value"] is True
    assert {s["modality"] for s in result["tipo_cta"]["supports"]}=={"caption","audio"}
    parts.append(frag("ocr","Não salve este post."))
    assert fusion.fuse(ASSET,parts)["tipo_cta"]["reason"]=="CONTEXT_VETO"


def test_partial_ocr_does_not_become_semantic_or_negative():
    result=fusion.fuse(ASSET,[frag("ocr","Salve",False)])
    assert result["tipo_cta"]["value"] is None
    assert result["texto_na_tela"]["value"] is True
    empty=fusion.fuse(ASSET,[])
    assert empty["texto_na_tela"]["value"] is None
    assert empty["tem_cta"]["value"] is None
    assert empty["hook_primeiros_3s"]["state"]=="not_assessed"


def test_no_concat_across_segments():
    parts=[frag("audio","Clique no link"),frag("audio","na bio")]
    assert fusion.fuse(ASSET,parts)["tipo_cta"]["value"] is None


def test_asset_mismatch_and_text_tamper_rejected():
    f=frag("caption","Salve este post.")
    with pytest.raises(fusion.FusionError,match="ASSET_MISMATCH"):
        fusion.fuse("b"*64,[f])
    f["text"]="Siga este perfil."
    with pytest.raises(fusion.FusionError,match="FRAGMENT_INVALID"):
        fusion.fuse(ASSET,[f])


def test_lexical_gate_metrics():
    rows=[]
    for i,(caption,expected) in enumerate((("Salve este post.","salvar"),("Siga este perfil.","seguir"),("Não salve.",None))):
        parts=[frag("caption",caption)]
        rows.append({"expected":{"tipo_cta":expected,"tema_principal":None,"texto_na_tela":None},
                     "arms":{name:fusion.fuse(ASSET,parts,mods) for name,mods in fusion.ARMS.items()}})
    m=fusion.score_arm(rows,"all","tipo_cta")
    assert m["candidate_recall"]==1 and m["candidate_precision"]==1
    assert m["wrong_nonabstained"]==0 and m["abstentions"]==1
    assert not fusion.evaluate(rows)["engineering_gate_passed"]  # other fields lack support


def test_shared_lossless_mux_and_timeline(tmp_path):
    binary=shutil.which("ffmpeg")
    if not binary:
        pytest.skip("local FFmpeg required")
    row=shared.build_decode_fixture(shared.CASES[2],tmp_path,binary,None)
    assert row["source_pixels_and_pcm_verified"]
    assert row["temporal_passed"] and row["expected_transitions_s"]==[3.0]
    assert len(row["pcm"])==192000 and not any(row["pcm"])
    assert row["decoded_pcm_sha256"]==hashlib.sha256(row["pcm"]).hexdigest()
    assert [t for t,_ in row["frames"]]==[0,3]
    assert row["frames"][0][1]!=row["frames"][1][1]


def test_shared_cli_requires_explicit_models(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    monkeypatch.setattr(shared,"run_shared_fixture_benchmark",lambda *_:{"cases":[],"engineering_gate_passed":True})
    args=["--synthetic-shared-multimodal","--model-dir",str(tmp_path),"--report-name","shared.json"]
    assert cli.main(args)==2
    assert json.loads(capsys.readouterr().out)["code"]=="FUSION_MEDIUM_REQUIRED"
    args+=["--asr-candidate","medium"]
    assert cli.main(args)==2
    assert json.loads(capsys.readouterr().out)["code"]=="FUSION_LOCAL_MODELS_REQUIRED"
    args+=["--tessdata-dir",str(tmp_path)]
    assert cli.main(args)==0
    assert json.loads(capsys.readouterr().out)["report_name"]=="shared.json"
    assert cli.main(args)==2
