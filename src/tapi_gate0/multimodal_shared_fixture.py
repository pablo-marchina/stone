"""IMP-063/064: real execution on internally authored, shared synthetic clips.

FFV1 + PCM lossless mux, decoded pixels and PCM verified. No arbitrary input
media, network inference, VLM, canonical rubric writes or external grants.
"""
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
import gc
import os
import shutil
import tempfile

from . import multimodal_asr as asr
from . import multimodal_vad as vad
from . import multimodal_vad_asr as joint
from . import multimodal_temporal as temporal
from . import multimodal_ocr as ocr
from . import multimodal_ocr_consensus as consensus
from . import multimodal_fusion as fusion

VERSION="bd-multimodal-shared-fixture.v1"
DURATION=6
FPS=4
FRAME_BYTES=ocr.WIDTH*ocr.HEIGHT
FRAMES=DURATION*FPS
BEST_HASHES={"por":"711de9dbb8052067bd42f16b9119967f30bada80d57e2ef24f65d09f531adb04",
             "eng":"8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba"}
VAD_HASH="4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2"
# caption, speech, screen, late screen, geometry, expected topic, CTA, OCR presence.
CASES=(
    ("caption_only","Vendas. Comente sua dúvida abaixo.","","",False,False,"vendas","comentar",None),
    ("audio_only","","Salve este conteúdo para revisar mais tarde.","",False,False,None,"salvar",None),
    ("ocr_only","","","Siga nosso perfil",True,False,None,"seguir",True),
    ("agreement","Fluxo de caixa. Salve este post.","Salve este conteúdo para revisar mais tarde.",
        "Salve para revisar depois",False,False,"finanças","salvar",True),
    ("conflict","Comente sua dúvida abaixo.","","Salve para revisar depois",False,False,None,None,True),
    ("negative","Não salve este post.","","",False,True,None,None,None),
    ("audio_topic","","Calcule os custos fixos e a margem de contribuição.","",False,False,"finanças",None,None),
)


def _sha(data):
    return sha256(data).hexdigest()


def _pixels(text,inverted=False,geometry=False):
    from PIL import Image,ImageDraw,ImageFont
    bg,fg=(20,240) if inverted else (250,15)
    im=Image.new("L",(ocr.WIDTH,ocr.HEIGHT),bg)
    draw=ImageDraw.Draw(im)
    if text:
        draw.text((64,ocr.HEIGHT//2),text,font=ImageFont.load_default(size=48),fill=fg,anchor="lm")
    if geometry:
        draw.rectangle((80,90,250,210),fill=fg)
        draw.ellipse((420,160,600,340),outline=fg,width=8)
    return im.tobytes()


def _command(ffmpeg,args,**kwargs):
    return temporal._run(ffmpeg,["-hide_banner","-loglevel","error","-nostdin",*args],**kwargs)


def build_decode_fixture(case,root,ffmpeg,espeak):
    cid,caption,speech,screen,late,geometry,topic,cta,has_text=case
    first=_pixels("" if late else screen,geometry=geometry)
    second=_pixels(screen,inverted=True) if late else first
    raw_video=first*(3*FPS)+second*(3*FPS)
    speech_pcm=asr._speech_pcm(espeak,ffmpeg,root,cid,speech,155) if speech else b""
    target_bytes=2*asr.SAMPLE_RATE*DURATION
    prefix=bytes(asr.SAMPLE_RATE) if speech else b""  # 0.5 s
    if len(prefix)+len(speech_pcm)>target_bytes:
        raise fusion.FusionError("FUSION_FIXTURE_DURATION_INVALID")
    raw_audio=prefix+speech_pcm+bytes(target_bytes-len(prefix)-len(speech_pcm))
    video_file=root/(cid+".gray")
    audio_file=root/(cid+".pcm")
    asset=root/(cid+".mkv")
    video_file.write_bytes(raw_video)
    audio_file.write_bytes(raw_audio)
    _command(ffmpeg,["-n","-protocol_whitelist","file,pipe","-f","rawvideo","-pixel_format","gray",
        "-video_size",f"{ocr.WIDTH}x{ocr.HEIGHT}","-framerate",str(FPS),"-i",str(video_file),
        "-f","s16le","-ar",str(asr.SAMPLE_RATE),"-ac","1","-i",str(audio_file),
        "-map","0:v:0","-map","1:a:0","-c:v","ffv1","-pix_fmt","gray","-threads","1",
        "-c:a","pcm_s16le","-t",str(DURATION),str(asset)])
    video_file.unlink()
    audio_file.unlink()
    if not asset.is_file() or not 0<asset.stat().st_size<=4_000_000:
        raise fusion.FusionError("FUSION_ASSET_SIZE_INVALID")
    media_hash=asr._file_hash(asset)
    decoded=_command(ffmpeg,["-protocol_whitelist","file,pipe","-i",str(asset),"-map","0:v:0",
        "-pix_fmt","gray","-threads","1","-f","rawvideo","pipe:1"],output_limit=FRAMES*FRAME_BYTES)
    pcm=_command(ffmpeg,["-protocol_whitelist","file,pipe","-i",str(asset),"-map","0:a:0",
        "-vn","-ar",str(asr.SAMPLE_RATE),"-ac","1","-f","s16le","pipe:1"],output_limit=target_bytes)
    if decoded!=raw_video or pcm!=raw_audio or media_hash!=asr._file_hash(asset):
        raise fusion.FusionError("FUSION_LOSSLESS_DECODE_MISMATCH")
    sampled=_command(ffmpeg,["-protocol_whitelist","file,pipe","-i",str(asset),"-map","0:v:0",
        "-vf","fps=4,scale=64:64,format=gray","-threads","1","-f","rawvideo","pipe:1"],
        output_limit=FRAMES*temporal.FRAME_BYTES)
    measure=temporal.sample_measurements(sampled)
    actual=[r["sample_time_s"] for r in measure["transition_candidates"]]
    expected=[3.0] if late else []
    passed=measure["samples"]==FRAMES and actual==expected
    frames=[]
    for t in (0,3):
        i=t*FPS
        raw=decoded[i*FRAME_BYTES:(i+1)*FRAME_BYTES]
        frames.append((t,raw))
    return {"case_id":cid,"media_sha256":media_hash,"caption_sha256":fusion.digest(caption),
            "caption":caption,"pcm":pcm,"frames":frames,"temporal":measure,"temporal_passed":passed,
            "expected_transitions_s":expected,"expected":{"tema_principal":topic,"tipo_cta":cta,"texto_na_tela":has_text},
            "duration_s":DURATION,"decoded_video_sha256":_sha(decoded),"decoded_pcm_sha256":_sha(pcm),
            "source_pixels_and_pcm_verified":True}


def extract_ocr(row,root,binary,tessdata):
    from PIL import Image
    result=[]
    observations=[]
    for timestamp,raw in row["frames"]:
        stem=row["case_id"]+"_"+str(timestamp)
        path=root/(stem+".png")
        view=root/(stem+"_view.png")
        Image.frombytes("L",(ocr.WIDTH,ocr.HEIGHT),raw).save(path)
        source_hash=asr._file_hash(path)
        provenance=consensus.prepare_view(path,view)
        first=ocr.parse_tsv(ocr.ocr_tsv(binary,path,tessdata))
        second=ocr.parse_tsv(consensus.supporting_tsv(binary,view,tessdata))
        words=consensus.consensus_words(first,second)
        complete=bool(words) and len(words)==len(first)==len(second) and [w["supporting_index"] for w in words]==list(range(len(second)))
        if asr._file_hash(path)!=source_hash or asr._file_hash(view)!=provenance["view_sha256"]:
            raise fusion.FusionError("FUSION_FRAME_CHANGED")
        locator={"timestamp_s":timestamp,"timestamp_kind":"decoded_uniform_frame_index",
                 "frame_sha256":_sha(raw),"frame_png_sha256":source_hash,
                 "view_sha256":provenance["view_sha256"],"words":words,
                 "complete_text_verified":False}
        observations.append({**locator,"media_sha256":row["media_sha256"],
                             "primary_words":first,"supporting_words":second,
                             "complete_primary_and_supporting_sequence_retained":complete,
                             "observation_status":"candidate" if words else "abstained"})
        if words:
            result.append(fusion.fragment(row["media_sha256"],"ocr"," ".join(w["text"] for w in words),
                locator,semantic_eligible=complete))
    return result,observations


def validate_asset_binding(row):
    fusion.validate_fragments(row["media_sha256"],row["fragments"])
    if (row["caption_sha256"]!=fusion.digest(row["caption"])
            or row["audio"]["pcm_sha256"]!=row["decoded_pcm_sha256"]
            or row["vad"]["pcm_sha256"]!=row["decoded_pcm_sha256"]
            or [frame["timestamp_s"] for frame in row["ocr_frames"]]!=[0,3]):
        raise fusion.FusionError("FUSION_SOURCE_BINDING_INVALID")
    for f in row["fragments"]:
        loc=f["locator"]
        if f["modality"]=="caption":
            valid=f["text"]==row["caption"] and loc["caption_sha256"]==row["caption_sha256"]
        elif f["modality"]=="audio":
            valid=loc["source_pcm_sha256"]==row["decoded_pcm_sha256"] and any(
                seg["text"]==f["text"] and seg["text_sha256"]==f["text_sha256"]
                and seg["start_s"]==loc["start_s"] and seg["end_s"]==loc["end_s"]
                and seg["chunk_pcm_sha256"]==loc["chunk_pcm_sha256"]
                for seg in row["audio"]["segments"])
        else:
            valid=any(frame["media_sha256"]==row["media_sha256"]
                and frame["timestamp_s"]==loc["timestamp_s"]
                and frame["frame_sha256"]==loc["frame_sha256"]
                and frame["frame_png_sha256"]==loc["frame_png_sha256"]
                and frame["view_sha256"]==loc["view_sha256"]
                and frame["words"]==loc["words"]
                and f["text"]==" ".join(w["text"] for w in frame["words"])
                and f["semantic_eligible"]==frame["complete_primary_and_supporting_sequence_retained"]
                for frame in row["ocr_frames"])
        if not valid:
            raise fusion.FusionError("FUSION_SOURCE_BINDING_INVALID")
    return True


def run_shared_fixture_benchmark(model_dir,tessdata_dir):
    os.environ.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_HUB_DISABLE_TELEMETRY="1")
    asr.require_temp_capacity()
    checkpoint=asr.verify_checkpoint(model_dir,"medium")
    languages=ocr.verify_tessdata(tessdata_dir)
    if languages!=BEST_HASHES:
        raise fusion.FusionError("FUSION_SELECTED_OCR_HASH_MISMATCH")
    if version("faster-whisper")!=asr.ASR_VERSION:
        raise asr.ASRError("ASR_RUNTIME_VERSION_MISMATCH")
    binaries={name:shutil.which(name) for name in ("ffmpeg","espeak-ng","tesseract")}
    if not all(binaries.values()):
        raise fusion.FusionError("FUSION_LOCAL_BINARY_UNAVAILABLE")
    from faster_whisper.utils import get_assets_path
    from faster_whisper.vad import VadOptions,get_speech_timestamps,get_vad_model
    asset=Path(get_assets_path())/"silero_vad_v6.onnx"
    if not asset.is_file() or asset.is_symlink() or not 0<asset.stat().st_size<=30_000_000 or asr._file_hash(asset)!=VAD_HASH:
        raise fusion.FusionError("FUSION_SELECTED_VAD_HASH_MISMATCH")
    prepared=[]
    with tempfile.TemporaryDirectory(prefix="tapi-shared-fixtures-") as temp:
        root=Path(temp)
        for case in CASES:
            with asr.asr_stage("shared_fixture",case[0]):
                row=build_decode_fixture(case,root,binaries["ffmpeg"],binaries["espeak-ng"])
                fragments,row["ocr_frames"]=extract_ocr(row,root,binaries["tesseract"],tessdata_dir)
                if row["caption"]:
                    fragments.append(fusion.fragment(row["media_sha256"],"caption",row["caption"],
                        {"caption_sha256":row["caption_sha256"],"source":"authored_fixture_caption"}))
                row["fragments"]=fragments
                del row["frames"]
                prepared.append(row)
        if ocr.verify_tessdata(tessdata_dir)!=languages:
            raise fusion.FusionError("FUSION_LANGUAGE_DATA_CHANGED")
    if len({r["media_sha256"] for r in prepared})!=len(prepared):
        raise fusion.FusionError("FUSION_DUPLICATE_MEDIA_ASSET")
    with asr.asr_stage("vad"):
        get_vad_model.cache_clear()
        try:
            options=VadOptions(**vad.OPTIONS)
            get_vad_model()
            for row in prepared:
                row["vad"]=joint.detect_regions(row["pcm"],lambda pcm:get_speech_timestamps(pcm,options,sampling_rate=asr.SAMPLE_RATE))
            if asr._file_hash(asset)!=VAD_HASH:
                raise fusion.FusionError("FUSION_VAD_ASSET_CHANGED")
        finally:
            get_vad_model.cache_clear()
            gc.collect()
    with asr.asr_stage("model_load"):
        from faster_whisper import WhisperModel
        t=perf_counter()
        model=WhisperModel(str(model_dir),device="cpu",compute_type="int8",cpu_threads=4,num_workers=1,local_files_only=True)
        if not model.model.is_multilingual or model.feature_extractor.sampling_rate!=asr.SAMPLE_RATE:
            raise asr.ASRError("ASR_MULTILINGUAL_MODEL_REQUIRED")
        load_ms=round((perf_counter()-t)*1000,3)
    for row in prepared:
        with asr.asr_stage("inference",row["case_id"]):
            audio=joint.transcribe_regions(model,row.pop("pcm"),row["vad"]["intervals"])
            if audio["pcm_sha256"]!=row["decoded_pcm_sha256"]:
                raise fusion.FusionError("FUSION_PCM_HASH_MISMATCH")
            row["audio"]=audio
            for s in audio["segments"]:
                row["fragments"].append(fusion.fragment(row["media_sha256"],"audio",s["text"],
                    {"start_s":s["start_s"],"end_s":s["end_s"],"source_pcm_sha256":s["source_pcm_sha256"],
                     "chunk_pcm_sha256":s["chunk_pcm_sha256"],"timestamp_kind":audio["timestamp_kind"]}))
            row["asset_binding_verified"]=validate_asset_binding(row)
            row["arms"]={name:fusion.fuse(row["media_sha256"],row["fragments"],modalities)
                         for name,modalities in fusion.ARMS.items()}
    del model
    gc.collect()
    if asr.verify_checkpoint(model_dir,"medium")!=checkpoint:
        raise asr.ASRError("ASR_CHECKPOINT_CHANGED")
    scores=fusion.evaluate(prepared)
    integrity=all(r["source_pixels_and_pcm_verified"] and r["asset_binding_verified"] and r["temporal_passed"] for r in prepared)
    negatives=[r for r,c in zip(prepared,CASES) if not c[2]]
    negative_calls=sum(r["audio"]["asr_calls"] for r in negatives)
    gate=scores["engineering_gate_passed"] and integrity and negative_calls==0 and len(prepared)==len(CASES)
    return {"status":"SHARED_MULTIMODAL_FIXTURE_BENCHMARK_COMPLETED","policy_version":VERSION,
            "fusion_policy":fusion.VERSION,"checkpoint":checkpoint,"ocr_language_data_sha256":languages,
            "vad_asset_sha256":VAD_HASH,"auxiliary_hashes_match_operator_baseline":True,
            "auxiliary_hashes_independently_verified":False,
            "runtime_versions":{name:version(name) for name in ("faster-whisper","ctranslate2","onnxruntime","numpy","Pillow")},
            "binary_versions":{name:temporal._run(path,["--version"] if name!="ffmpeg" else ["-version"],output_limit=100000).decode("utf-8","replace").splitlines()[0] for name,path in binaries.items()},
            "execution_order":"mux_decode_ocr_then_vad_then_whisper_then_fusion","model_load_ms":load_ms,
            "cases":prepared,**scores,"engineering_gate_passed":bool(gate),
            "temporal_integrity_passed":integrity,"negative_asr_calls":negative_calls,
            "case_count":len(prepared),"synthetic_only":True,"vlm_evaluated":False,
            "semantic_scores_calibrated":False,"real_media_processed":0,
            "scientific_admissions":0,"rubric_assessments_written":0,
            "real_media_processing_allowed":False,
            "external_data_accessed":False,"database_mutated":False,"production_approved":False}
