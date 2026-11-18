"""Candidate processor result contract. Not a rubric, evidence admission or model.

The first integrated runner accepts only a fixed header fixture and an
explicit abstention. Observed types are candidate interfaces for later
validated adapters; validation checks structure, not truth of observations.
"""
from hashlib import sha256
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator, model_serializer

VERSION = "asset-processor-result.v1"
MAX_BYTES = 1_000_000
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Id = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
Ms = Annotated[int, Field(ge=0, le=86_400_000)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)]
Processor = Literal["asr_vad", "ocr", "temporal", "vlm"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class Interval(Contract):
    start_ms: Ms
    end_ms: Ms

    @model_validator(mode="after")
    def ordered(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("INTERVAL_ORDER")
        return self


class Speech(Interval):
    text: Text


class ASR(Contract):
    processor: Literal["asr_vad"] = "asr_vad"
    state: Literal["observed"] = "observed"
    timeline: Literal["decoded_pcm"] = "decoded_pcm"
    duration_ms: Annotated[int, Field(gt=0, le=86_400_000)]
    segments: tuple[Speech, ...] = Field(min_length=1, max_length=256)
    vad: tuple[Interval, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def times(self):
        for seq in (self.segments, self.vad):
            if any(x.end_ms > self.duration_ms for x in seq) or any(
                a.end_ms > b.start_ms for a,b in zip(seq,seq[1:])
            ):
                raise ValueError("ASR_TIMELINE")
        if any(not any(v.start_ms < s.end_ms and s.start_ms < v.end_ms for v in self.vad) for s in self.segments):
            raise ValueError("ASR_VAD_NO_OVERLAP")
        return self


class Frame(Contract):
    time_ms: Ms
    frame_sha256: Digest
    timeline: Literal["resampled_uniform", "image"]

    @model_validator(mode="after")
    def image_time(self):
        if self.timeline == "image" and self.time_ms != 0:
            raise ValueError("IMAGE_TIME")
        return self


class Word(Contract):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,max_length=256)]
    box_px: tuple[int,int,int,int]
    confidence_raw: Annotated[float, Field(ge=0,le=100)] | None = None


class OCR(Contract):
    processor: Literal["ocr"] = "ocr"
    state: Literal["observed"] = "observed"
    frame: Frame
    width: Annotated[int,Field(gt=0,le=16384)]
    height: Annotated[int,Field(gt=0,le=16384)]
    words: tuple[Word,...] = Field(min_length=1,max_length=256)

    @model_validator(mode="after")
    def boxes(self):
        for word in self.words:
            x,y,w,h=word.box_px
            if x<0 or y<0 or w<=0 or h<=0 or x+w>self.width or y+h>self.height:
                raise ValueError("OCR_BOX_OUTSIDE_FRAME")
        return self


class Transition(Contract):
    previous: Frame
    current: Frame
    normalized_difference: Annotated[float,Field(ge=0,le=1)]

    @model_validator(mode="after")
    def order(self):
        if self.previous.timeline != "resampled_uniform" or self.current.timeline != "resampled_uniform" or self.previous.time_ms >= self.current.time_ms:
            raise ValueError("TRANSITION_TIMELINE")
        return self


class Temporal(Contract):
    processor: Literal["temporal"] = "temporal"
    state: Literal["observed"] = "observed"
    samples: Annotated[int,Field(ge=2,le=4096)]
    threshold: Annotated[float,Field(gt=0,le=1)]
    candidates: tuple[Transition,...] = Field(max_length=4095)

    @model_validator(mode="after")
    def candidates_valid(self):
        if len(self.candidates)>=self.samples or any(x.normalized_difference<self.threshold for x in self.candidates) or any(a.current.time_ms>=b.current.time_ms for a,b in zip(self.candidates,self.candidates[1:])):
            raise ValueError("TEMPORAL_CANDIDATES")
        return self


class VLM(Contract):
    processor: Literal["vlm"] = "vlm"
    state: Literal["observed"] = "observed"
    frame: Frame
    text_present: Literal["yes","no","uncertain"]
    scene: Literal["blank","text_card","geometry","uncertain"]

    @model_validator(mode="after")
    def consistent(self):
        if self.text_present=="uncertain" and self.scene=="uncertain":
            raise ValueError("VLM_FULL_ABSTENTION_REQUIRED")
        if (self.text_present=="yes" and self.scene in ("blank","geometry")) or (self.text_present=="no" and self.scene=="text_card"):
            raise ValueError("VLM_CONTRADICTION")
        return self


class Abstention(Contract):
    processor: Processor
    state: Literal["abstained"] = "abstained"
    reason: Literal["fixture_header_only","no_observable_signal","unsupported_modality","insufficient_evidence","fixture_quality_rejected"]


# Distinct identity; existing v1 payloads omit the optional source binding.
SHARED_AV_METHOD = "synthetic-shared-av-v1"
STRICT_QUALITY = "strict"
PARTIAL_QUALITY = "allow_wer_abstention"
SharedAVQualityPolicy = Literal["strict", "allow_wer_abstention"]


class SharedAVSource(Contract):
    schema_version: Literal["shared-av-source.v1"] = "shared-av-source.v1"
    container_sha256: Digest
    decoder_sha256: Digest
    rgb_stream_sha256: Digest
    pcm_sha256: Digest
    frame_sha256: Digest
    frame_png_sha256: Digest
    frame_time_ms: Literal[1000] = 1000
    frame_width: Literal[960] = 960
    frame_height: Literal[540] = 540
    sample_fps: Literal[4] = 4
    frame_count: Annotated[int, Field(ge=5,le=60)]
    pcm_samples: Annotated[int, Field(gt=0,le=240000)]
    temporal_sample_sha256: tuple[Digest,...] = Field(min_length=5,max_length=32)
    temporal_sampling: Literal["gray64_point_first_8s"] = "gray64_point_first_8s"
    synthetic_only: Literal[True] = True

    @model_validator(mode="after")
    def duration_binding(self):
        if (self.frame_count!=(self.pcm_samples+3999)//4000 or
                len(self.temporal_sample_sha256)!=min(self.frame_count,32)):
            raise ValueError("SHARED_AV_DURATION")
        return self


class SharedAVBinding(Contract):
    source: SharedAVSource
    adapter_configuration_sha256: Digest
    quality_policy: SharedAVQualityPolicy = STRICT_QUALITY

    @model_serializer(mode="wrap")
    def preserve_strict_encoding(self,handler):
        result=handler(self)
        if self.quality_policy==STRICT_QUALITY:
            result.pop("quality_policy",None)
        return result

    def configuration(self,processor):
        config={"method":SHARED_AV_METHOD,"processor":processor,
            "source":self.source.model_dump(mode="json"),
            "adapter_configuration_sha256":self.adapter_configuration_sha256}
        if self.quality_policy!=STRICT_QUALITY:
            config["quality_policy"]=self.quality_policy
        raw=json.dumps(config,sort_keys=True,separators=(",",":")).encode()
        return sha256(raw).hexdigest()


class SharedAVQualityRejection(Contract):
    """Authored-fixture WER rejection; no hypothesis, tokens, or text digest."""
    reason: Literal["ASR_FIXTURE_WER_GATE"] = "ASR_FIXTURE_WER_GATE"
    wer: float = Field(gt=0.50,allow_inf_nan=False)
    vad_iou: float = Field(ge=0.60,le=1,allow_inf_nan=False)
    vad_boundary_error_s: float = Field(ge=0,le=0.75,allow_inf_nan=False)
    reference_words: int = Field(gt=0,le=20000)
    hypothesis_words: int = Field(ge=0,le=256000)
    vad_calls: Literal[1]
    asr_calls: int = Field(ge=1,le=64)

    @model_validator(mode="after")
    def failed_gate(self):
        edits=self.wer*self.reference_words
        if (abs(edits-round(edits))>1e-7 or
                not abs(self.reference_words-self.hypothesis_words)<=round(edits)<=max(self.reference_words,self.hypothesis_words)):
            raise ValueError("SHARED_AV_QUALITY_WER_INCONSISTENT")
        return self


class ProcessorResult(Contract):
    schema_version: Literal["asset-processor-result.v1"] = VERSION
    tenant_id: Id
    job_id: Id
    object_id: Digest
    input_sha256: Digest
    attempt: Annotated[int,Field(ge=1,le=3)]
    purpose: Literal["research_analysis","studio_creation"]
    method_version: Id
    configuration_sha256: Digest
    origin: Literal["synthetic_fixture","adapter_candidate"]
    result: ASR | OCR | Temporal | VLM | Abstention
    shared_av: SharedAVBinding | None = None
    shared_av_quality_rejection: SharedAVQualityRejection | None = None
    scientific_evidence: Literal[False] = False
    canonical_rubric: Literal[False] = False
    calibrated_probability: None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_encoding(self,handler):
        result=handler(self)
        if self.shared_av is None:
            result.pop("shared_av",None)
        if self.shared_av_quality_rejection is None:
            result.pop("shared_av_quality_rejection",None)
        return result

    @model_validator(mode="after")
    def origin_consistent(self):
        binding=self.shared_av
        rejected=isinstance(self.result,Abstention) and self.result.reason=="fixture_quality_rejected"
        if rejected!=(self.shared_av_quality_rejection is not None):
            raise ValueError("SHARED_AV_QUALITY_REJECTION_BINDING")
        if rejected and (binding is None or binding.quality_policy!=PARTIAL_QUALITY
                or self.result.processor!="asr_vad" or self.origin!="adapter_candidate"):
            raise ValueError("SHARED_AV_QUALITY_POLICY")
        if (binding is not None)!=(self.method_version==SHARED_AV_METHOD):
            raise ValueError("SHARED_AV_METHOD")
        if binding is not None:
            src=binding.source
            r=self.result
            if (self.input_sha256!=src.container_sha256 or self.origin!="adapter_candidate" or
                    self.configuration_sha256!=binding.configuration(r.processor)):
                raise ValueError("SHARED_AV_BINDING")
            if isinstance(r,(OCR,VLM)) and (r.frame.time_ms,r.frame.frame_sha256,r.frame.timeline)!=(src.frame_time_ms,src.frame_sha256,"resampled_uniform"):
                raise ValueError("SHARED_AV_FRAME")
            if isinstance(r,OCR) and (r.width,r.height)!=(src.frame_width,src.frame_height):
                raise ValueError("SHARED_AV_FRAME_DIMENSIONS")
            if isinstance(r,ASR) and r.duration_ms!=(src.pcm_samples*1000+15999)//16000:
                raise ValueError("SHARED_AV_PCM_DURATION")
            if isinstance(r,Temporal):
                if r.samples!=len(src.temporal_sample_sha256):
                    raise ValueError("SHARED_AV_SAMPLE_COUNT")
                for transition in r.candidates:
                    for frame in (transition.previous,transition.current):
                        i,rem=divmod(frame.time_ms,250)
                        if rem or i>=r.samples or frame.frame_sha256!=src.temporal_sample_sha256[i]:
                            raise ValueError("SHARED_AV_SAMPLE_BINDING")
        if isinstance(self.result,Abstention):
            if (self.result.reason=="fixture_header_only") != (self.origin=="synthetic_fixture"):
                raise ValueError("FIXTURE_ORIGIN_MISMATCH")
        elif self.origin=="synthetic_fixture":
            raise ValueError("HEADER_FIXTURE_CANNOT_OBSERVE")
        return self


def encode(result: ProcessorResult) -> bytes:
    if type(result) is not ProcessorResult:
        raise ValueError("PROCESSOR_RESULT_TYPE")
    # Revalidate even objects produced via model_construct/model_copy.
    data=json.dumps(result.model_dump(mode="json"),ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
    decode(data)
    return data


def decode(data: bytes) -> ProcessorResult:
    if type(data) is not bytes or not 0<len(data)<=MAX_BYTES:
        raise ValueError("PROCESSOR_RESULT_SIZE")
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:
                raise ValueError("PROCESSOR_RESULT_DUPLICATE_KEY")
            d[k]=v
        return d
    # Pydantic JSON validates tuple representation; reject duplicate JSON keys first.
    json.loads(data.decode("utf-8"),object_pairs_hook=unique)
    return ProcessorResult.model_validate_json(data)


def validate_persisted_binding(result, *, spec, ref, attempt):
    """Bind a candidate to an authenticated completed attempt, not a live lease."""
    if type(attempt) is not int or (result.tenant_id,result.job_id,result.object_id,result.input_sha256,result.attempt,
        result.purpose,result.method_version,result.configuration_sha256,result.result.processor) != (
        spec.tenant_id,spec.job_id,spec.object_id,ref.target.sha256,attempt,
        spec.purpose,spec.method_version,spec.configuration_sha256,spec.processor):
        raise ValueError("PROCESSOR_RESULT_BINDING")
    if result.shared_av is not None and (ref.target.media_kind,ref.mime)!=("video","video/mp4"):
        raise ValueError("SHARED_AV_ROOT_KIND")
    if (ref.target.tenant_id,ref.object_id)!=(spec.tenant_id,spec.object_id):
        raise ValueError("PROCESSOR_RESULT_BINDING")
    return result


def validate_binding(result, *, spec, ref, lease):
    if (lease.tenant_id,lease.job_id)!=(spec.tenant_id,spec.job_id):
        raise ValueError("PROCESSOR_RESULT_BINDING")
    return validate_persisted_binding(result,spec=spec,ref=ref,attempt=lease.attempt)
