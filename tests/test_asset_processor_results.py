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


# The shared binding is additive, but legacy canonical bytes must not drift.
def test_shared_av_legacy_encoding_unchanged():
    r=ProcessorResult(**BASE,result=Abstention(processor="ocr",reason="fixture_header_only"))
    expected={**BASE,"schema_version":"asset-processor-result.v1",
        "result":{"processor":"ocr","state":"abstained","reason":"fixture_header_only"},
        "scientific_evidence":False,"canonical_rubric":False,"calibrated_probability":None}
    assert encode(r)==json.dumps(expected,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    assert "shared_av" not in r.model_dump(mode="json")


def _shared_result():
    from tapi_gate0.asset_processor_results import SharedAVSource,SharedAVBinding,SHARED_AV_METHOD,Frame
    source=SharedAVSource(container_sha256=BASE["input_sha256"],decoder_sha256="d"*64,
        rgb_stream_sha256="e"*64,pcm_sha256="f"*64,frame_sha256="1"*64,frame_png_sha256="2"*64,
        frame_count=12,pcm_samples=48000,temporal_sample_sha256=("3"*64,)*12)
    binding=SharedAVBinding(source=source,adapter_configuration_sha256="4"*64)
    result=VLM(frame=Frame(time_ms=1000,frame_sha256=source.frame_sha256,timeline="resampled_uniform"),
        scene="text_card",text_present="yes")
    return ProcessorResult(**{**BASE,"method_version":SHARED_AV_METHOD,"origin":"adapter_candidate",
        "configuration_sha256":binding.configuration("vlm")},result=result,shared_av=binding)


def test_shared_av_result_roundtrip_and_binding():
    r=_shared_result()
    assert decode(encode(r))==r
    assert r.shared_av.source.pcm_samples==48000
    for change,code in [
        ({"shared_av":None},"SHARED_AV_METHOD"),
        ({"method_version":"old"},"SHARED_AV_METHOD"),
        ({"configuration_sha256":"c"*64},"SHARED_AV_BINDING"),
        ({"input_sha256":"9"*64},"SHARED_AV_BINDING"),
        ({"result":r.result.model_copy(update={"frame":r.result.frame.model_copy(update={"time_ms":2000})})},"SHARED_AV_FRAME"),
    ]:
        with pytest.raises(ValueError,match=code):
            encode(r.model_copy(update=change))


def test_shared_av_temporal_samples_bound_to_manifest():
    from tapi_gate0.asset_processor_results import Frame,Transition
    r=_shared_result()
    binding=r.shared_av
    obs=Temporal(samples=12,threshold=0.2,candidates=(Transition(
        previous=Frame(time_ms=750,frame_sha256="3"*64,timeline="resampled_uniform"),
        current=Frame(time_ms=1000,frame_sha256="3"*64,timeline="resampled_uniform"),
        normalized_difference=0.5),))
    r=r.model_copy(update={"result":obs,"configuration_sha256":binding.configuration("temporal")})
    assert decode(encode(r))==r
    bad=obs.candidates[0].model_copy(update={"current":obs.candidates[0].current.model_copy(update={"frame_sha256":"9"*64})})
    with pytest.raises(ValueError,match="SHARED_AV_SAMPLE_BINDING"):
        encode(r.model_copy(update={"result":obs.model_copy(update={"candidates":(bad,)})}))


def test_shared_av_bundle_rejects_mixed_source_and_legacy():
    from hashlib import sha256
    from tapi_gate0.asset_candidate_evidence import CandidateEvidence,CandidateEvidenceBundle
    from tapi_gate0.asset_processor_results import SharedAVBinding,Abstention
    r=_shared_result()
    def entry(result):
        digest=sha256(encode(result)).hexdigest()
        ident="artifact."+sha256((result.job_id+":"+digest).encode()).hexdigest()
        return CandidateEvidence(artifact_id=ident,payload_sha256=digest,observation=result)
    def bundle(first):
        return CandidateEvidenceBundle(tenant_id=r.tenant_id,content_id="content",object_id=r.object_id,
            input_sha256=r.input_sha256,media_kind="video",purpose=r.purpose,entries=(entry(first),entry(r)))
    legacy=ProcessorResult(**{**BASE,"job_id":"job.2"},result=Abstention(processor="ocr",reason="fixture_header_only"))
    with pytest.raises(ValueError,match="EVIDENCE_SHARED_AV_SOURCE_MISMATCH"):
        bundle(legacy)
    source=r.shared_av.source.model_copy(update={"pcm_sha256":"8"*64})
    binding=SharedAVBinding(source=source,adapter_configuration_sha256="5"*64)
    other=r.model_copy(update={"job_id":"job.3","shared_av":binding,
        "configuration_sha256":binding.configuration("ocr"),
        "result":Abstention(processor="ocr",reason="no_observable_signal")})
    with pytest.raises(ValueError,match="EVIDENCE_SHARED_AV_SOURCE_MISMATCH"):
        bundle(other)


def test_partial_shared_av_contract_rejects_mixed_policy_and_missing_rejection():
    from tapi_gate0.asset_processor_results import (Abstention,SharedAVQualityRejection,
        PARTIAL_QUALITY,STRICT_QUALITY)
    from tapi_gate0.asset_candidate_evidence import CandidateEvidence,CandidateEvidenceBundle
    from hashlib import sha256
    r=_shared_result()
    binding=r.shared_av.model_copy(update={"quality_policy":PARTIAL_QUALITY})
    quality=SharedAVQualityRejection(wer=4/7,vad_iou=.93,vad_boundary_error_s=.18,
        reference_words=7,hypothesis_words=8,vad_calls=1,asr_calls=1)
    rejected=r.model_copy(update={"job_id":"job.partial","shared_av":binding,
        "configuration_sha256":binding.configuration("asr_vad"),
        "result":Abstention(processor="asr_vad",reason="fixture_quality_rejected"),
        "shared_av_quality_rejection":quality})
    assert decode(encode(rejected))==rejected
    assert "shared_av_quality_rejection" not in r.model_dump(mode="json")
    assert "quality_policy" not in r.shared_av.model_dump(mode="json")
    assert r.shared_av.quality_policy==STRICT_QUALITY
    assert binding.configuration("vlm")!=r.shared_av.configuration("vlm")
    with pytest.raises(ValueError,match="QUALITY_REJECTION_BINDING"):
        encode(rejected.model_copy(update={"shared_av_quality_rejection":None}))
    with pytest.raises(ValueError,match="QUALITY_POLICY"):
        encode(rejected.model_copy(update={"shared_av":r.shared_av,
            "configuration_sha256":r.shared_av.configuration("asr_vad")}))
    with pytest.raises(ValueError):
        SharedAVQualityRejection(**{**quality.model_dump(),"wer":.5})
    with pytest.raises(ValueError,match="WER_INCONSISTENT"):
        SharedAVQualityRejection(**{**quality.model_dump(),"wer":.6})
    def entry(obs):
        digest=sha256(encode(obs)).hexdigest()
        ident="artifact."+sha256((obs.job_id+":"+digest).encode()).hexdigest()
        return CandidateEvidence(artifact_id=ident,payload_sha256=digest,observation=obs)
    with pytest.raises(ValueError,match="QUALITY_POLICY_MISMATCH"):
        CandidateEvidenceBundle(tenant_id=r.tenant_id,content_id="content",object_id=r.object_id,
            input_sha256=r.input_sha256,media_kind="video",purpose=r.purpose,
            entries=(entry(rejected),entry(r)))
