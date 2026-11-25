import hashlib
import json
from copy import deepcopy

import pytest

from tapi_gate0 import multimodal_evidence_replay as evidence
from tapi_gate0 import multimodal_fusion as fusion
from tapi_gate0 import multimodal_vlm as vlm
from tapi_gate0 import multimodal_vlm_single_scene as visual
from tapi_gate0.domain import RUBRIC_FIELD_NAMES

ASSET="a"*64
SOURCE="b"*64


def frag(modality,text,eligible=True):
    return fusion.fragment(ASSET,modality,text,{"fixture":True},semantic_eligible=eligible)


def visual_obs(scene,t):
    return {"timestamp_s":t,"prediction":visual.derived(scene),"image_png_sha256":"c"*64}


def row_fixture():
    return {"media_sha256":ASSET,"fragments":[frag("caption","Vendas. Guarde este vídeo.")],
            "ocr_frames":[{"timestamp_s":0,"frame_sha256":"d"*64,"words":[{"text":"Vendas"}]},
                          {"timestamp_s":3,"frame_sha256":"e"*64,"words":[]}],
            "duration_s":6,"caption":"Vendas. Guarde este vídeo.","caption_sha256":"f"*64,
            "temporal":{"opening_samples":[{"sample_time_s":0}],"timestamp_kind":"resampled",
                         "transition_candidates":[],"transition_candidate_count":0,"sample_fps":4},
            "audio":{"segments":[]}}


def test_fifteen_arms_and_directed_cta():
    assert len(evidence.ARMS)==15
    row=row_fixture()
    obs={0:visual_obs("text_card",0),3:visual_obs("blank",3)}
    result=evidence.compose(row,obs,evidence.MODALITIES)
    assert set(result)==set(RUBRIC_FIELD_NAMES)
    assert result["tipo_cta"]["value"]=="salvar"
    assert result["tem_cta"]["value"] is True
    assert result["tema_principal"]["value"]=="vendas"
    assert result["texto_na_tela"]["value"] is True
    assert {s["modality"] for s in result["texto_na_tela"]["supports"]}=={"ocr","vlm"}
    assert all(not f["canonical"] for f in result.values())
    row["fragments"].append(frag("audio","Comente sua dúvida abaixo."))
    result=evidence.compose(row,obs,evidence.MODALITIES)
    assert result["tipo_cta"]["value"] is None
    assert result["tem_cta"]["value"] is None


def test_screen_conflict_is_local_and_never_negative():
    row=row_fixture()
    obs={0:visual_obs("geometry",0),3:visual_obs("text_card",3)}
    result=evidence.compose(row,obs,evidence.MODALITIES)["texto_na_tela"]
    assert result["value"] is None and len(result["vetoes"])==1
    assert evidence.compose(row,obs,("ocr",))["texto_na_tela"]["value"] is True
    only=evidence.compose(row,obs,("vlm",))["texto_na_tela"]
    assert only["value"] is True and only["reason"]=="VLM_ONLY_EXPLORATORY"
    row["ocr_frames"][1]["words"]=[{"text":"Vendas"}]
    assert evidence.compose(row,obs,evidence.MODALITIES)["texto_na_tela"]["value"] is True
    row["ocr_frames"][0]["words"]=row["ocr_frames"][1]["words"]=[]
    assert evidence.compose(row,obs,evidence.MODALITIES)["texto_na_tela"]["value"] is None
    obs[3]=visual_obs("blank",3)
    assert evidence.compose(row,obs,("vlm",))["texto_na_tela"]["value"] is None


def test_measurements_not_rubric_scores():
    row=row_fixture()
    obs={0:visual_obs("text_card",0),3:visual_obs("blank",3)}
    result=evidence.measurements(row,evidence.compose(row,obs,evidence.MODALITIES))
    for field in ("duracao_faixa","legenda_tamanho","hook_primeiros_3s","ritmo_cortes_0a10"):
        assert result[field]["state"]=="measurement_only"
        assert result[field]["value"] is None
    assert result["duracao_faixa"]["measurement"]["duration_s"]==6
    assert result["forca_hook_0a10"]["state"]=="not_assessed"
    assert result["criador_e_empreendedor_real"]["value"] is None


def test_partial_ocr_cannot_supply_cta():
    row=row_fixture()
    row["fragments"]=[frag("ocr","Guarde este vídeo.",False)]
    obs={0:visual_obs("text_card",0),3:visual_obs("blank",3)}
    result=evidence.compose(row,obs,evidence.MODALITIES)
    assert result["tipo_cta"]["value"] is None
    assert result["texto_na_tela"]["value"] is True


def test_visual_report_binding_and_tamper(monkeypatch):
    from PIL import Image
    def frames(suite,count):
        rows=[]
        for i in range(count):
            scene=("blank","geometry","text_card")[i%3]
            img=Image.new("RGB",(960,540),(i,i,i))
            if scene!="blank":
                img.putpixel((20,20),(250,250,250))
            rows.append({"case_id":suite+str(i),"suite":suite,"image":img,
                         "media_sha256":ASSET if suite=="shared" else None,
                         "timestamp_s":i if suite=="shared" else None,
                         "expected":visual.derived(scene),"ocr_positive_candidate":None})
        return rows
    monkeypatch.setattr(vlm,"make_frames",lambda _:frames("shared",14)+frames("challenge",6))
    monkeypatch.setattr(visual,"extra_frames",lambda:frames("additional_authored",6))
    observations=[]
    cache={}
    for frame in vlm.make_frames({})+visual.extra_frames():
        img=frame.pop("image")
        digest=hashlib.sha256(vlm.encode_image(img)).hexdigest()
        uniform=visual.exact_uniform(img)
        obs={"prediction":frame["expected"],"model_scene":None if uniform else frame["expected"]["scene"],
             "response_sha256":None if uniform else "a"*64,"inference_attempted":not uniform,
             "guard_reason":"EXACT_UNIFORM_PIXELS" if uniform else None,
             "reused_identical_image_result":digest in cache}
        cache[digest]=obs
        observations.append({**frame,**obs,"image_png_sha256":digest})
    report={"policy_version":visual.VERSION,"source_report_sha256":SOURCE,"model_id":vlm.MODEL_ID,
            "model_revision":vlm.MODEL_REVISION,"prompt_sha256":fusion.digest(visual.PROMPT),
            "runtime":{"build":vlm.RUNTIME_BUILD,"commit_prefix":vlm.RUNTIME_COMMIT},
            "checkpoint":{k:{"sha256":v} for k,v in vlm.FILES.items()},
            "synthetic_only":True,"shared_pixels_hash_matched":True,"external_data_accessed":False,
            "database_mutated":False,"production_approved":False,"real_media_processing_allowed":False,
            "real_media_processed":0,"scientific_admissions":0,"rubric_assessments_written":0,
            "cases":observations,"unique_images":len(cache),
            "unique_model_calls":sum(x["inference_attempted"] for x in cache.values()),
            "uniform_guard_unique_images":sum(x["guard_reason"]=="EXACT_UNIFORM_PIXELS" for x in cache.values()),
            **visual.metrics(observations)}
    assert len(evidence.validate_visual({},report,SOURCE))==14
    for key,value in (("source_report_sha256","d"*64),("unique_images",100)):
        tampered=deepcopy(report)
        tampered[key]=value
        with pytest.raises(fusion.FusionError):
            evidence.validate_visual({},tampered,SOURCE)
    tampered=deepcopy(report)
    tampered["cases"][0]["prediction"]=visual.derived("text_card")
    with pytest.raises(fusion.FusionError,match="PREDICTION_INVALID"):
        evidence.validate_visual({},tampered,SOURCE)


def test_cli_rejects_missing_and_existing_report(tmp_path,monkeypatch,capsys):
    from scripts import a6_evidence_replay as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    args=["--shared-name","shared.json","--vlm-name","vlm.json","--report-name","out.json"]
    assert cli.main(args)==2
    assert json.loads(capsys.readouterr().out)["stage"]=="input"
    target=tmp_path/"artifacts"/"private"/"out.json"
    target.write_text("keep")
    assert cli.main(args)==2
    assert target.read_text()=="keep"
