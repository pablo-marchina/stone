import json
from types import SimpleNamespace as NS
import pytest
from tapi_gate0.asset_processor_results import (ProcessorResult,ASR,OCR,Temporal,VLM,Abstention,encode,decode,validate_binding)

FRAME={"time_ms":0,"frame_sha256":"b"*64,"timeline":"resampled_uniform"}
BASE=dict(tenant_id="t",job_id="job.1",object_id="a"*64,input_sha256="b"*64,attempt=1,purpose="research_analysis",method_version="fixture-v3",configuration_sha256="c"*64,origin="synthetic_fixture")

@pytest.mark.parametrize("processor",["asr_vad","ocr","temporal","vlm"])
def test_fixture_abstention_roundtrip(processor):
    r=ProcessorResult(**BASE,result=Abstention(processor=processor,reason="fixture_header_only"))
    data=encode(r)
    assert decode(data)==r and encode(decode(data))==data
    assert not r.scientific_evidence and not r.canonical_rubric and r.calibrated_probability is None

@pytest.mark.parametrize("result",[
    {"processor":"asr_vad","state":"observed","duration_ms":1000,"segments":[{"start_ms":0,"end_ms":500,"text":"fixture"}],"vad":[{"start_ms":0,"end_ms":600}]},
    {"processor":"ocr","state":"observed","frame":FRAME,"width":100,"height":100,"words":[{"text":"fixture","box_px":[1,1,20,20],"confidence_raw":50.0}]},
    {"processor":"temporal","state":"observed","samples":2,"threshold":0.2,"candidates":[{"previous":FRAME,"current":{**FRAME,"time_ms":250},"normalized_difference":0.5}]},
    {"processor":"vlm","state":"observed","frame":FRAME,"text_present":"yes","scene":"text_card"},
])
def test_candidate_shapes_not_scientific_and_header_denied(result):
    good={**BASE,"origin":"adapter_candidate","result":result}
    assert decode(encode(decode(json.dumps(good).encode()))).result.processor==result["processor"]
    with pytest.raises(ValueError,match="HEADER_FIXTURE_CANNOT_OBSERVE"):
        decode(json.dumps({**good,"origin":"synthetic_fixture"}).encode())

@pytest.mark.parametrize("result",[
    {"processor":"asr_vad","state":"observed","duration_ms":1000,"segments":[{"start_ms":500,"end_ms":100,"text":"x"}],"vad":[{"start_ms":0,"end_ms":600}]},
    {"processor":"asr_vad","state":"observed","duration_ms":1000,"segments":[{"start_ms":500,"end_ms":700,"text":"x"}],"vad":[{"start_ms":0,"end_ms":100}]},
    {"processor":"ocr","state":"observed","frame":FRAME,"width":10,"height":10,"words":[{"text":"x","box_px":[9,9,2,2]}]},
    {"processor":"ocr","state":"observed","frame":FRAME,"width":10,"height":10,"words":[{"text":"x","box_px":[0,0,1,1],"confidence_raw":101}]},
    {"processor":"temporal","state":"observed","samples":2,"threshold":0.9,"candidates":[{"previous":FRAME,"current":{**FRAME,"time_ms":250},"normalized_difference":0.5}]},
    {"processor":"vlm","state":"observed","frame":FRAME,"text_present":"yes","scene":"blank"},
    {"processor":"vlm","state":"observed","frame":FRAME,"text_present":"uncertain","scene":"uncertain"},
    {"processor":"ocr","state":"abstained","reason":"fixture_header_only","words":[]},
])
def test_invalid_result_shapes(result):
    with pytest.raises(ValueError):
        decode(json.dumps({**BASE,"origin":"adapter_candidate","result":result}).encode())

@pytest.mark.parametrize("change",[{"scientific_evidence":True},{"canonical_rubric":True},{"calibrated_probability":0.99},{"attempt":"1"},{"origin":"adapter_candidate"}])
def test_no_scientific_claim_or_coercion(change):
    data={**BASE,"result":{"processor":"ocr","state":"abstained","reason":"fixture_header_only"},**change}
    with pytest.raises(ValueError):
        decode(json.dumps(data).encode())


def test_duplicate_key_and_oversize_rejected():
    with pytest.raises(ValueError,match="DUPLICATE_KEY"):
        decode(b'{"x":1,"x":2}')
    with pytest.raises(ValueError,match="SIZE"):
        decode(b'x'*1_000_001)


def test_binding_and_unvalidated_copy():
    r=ProcessorResult(**BASE,result=Abstention(processor="ocr",reason="fixture_header_only"))
    spec=NS(**{k:BASE[k] for k in ("tenant_id","job_id","object_id","purpose","method_version","configuration_sha256")},processor="ocr")
    ref=NS(object_id=BASE["object_id"],target=NS(sha256=BASE["input_sha256"],tenant_id="t"))
    lease=NS(tenant_id="t",job_id="job.1",attempt=1)
    assert validate_binding(r,spec=spec,ref=ref,lease=lease)==r
    for bad in [r.model_copy(update={"attempt":2}),r.model_copy(update={"tenant_id":"other"}),r.model_copy(update={"input_sha256":"d"*64}),r.model_copy(update={"result":Abstention(processor="vlm",reason="fixture_header_only")})]:
        with pytest.raises(ValueError,match="BINDING"):
            validate_binding(bad,spec=spec,ref=ref,lease=lease)
    with pytest.raises(ValueError):
        encode(r.model_copy(update={"scientific_evidence":True}))
