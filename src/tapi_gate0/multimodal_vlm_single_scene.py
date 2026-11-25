"""IMP-063: separate single-scene visual candidate with exact pixel guard.

The v1 failure remains recorded. Only internally generated frame fixtures.
No inference from absent OCR, no real-media negative or canonical labels.
"""
from hashlib import sha256
import json
import time

from . import multimodal_vlm as base

VERSION="bd-vlm-single-scene.v2"
SCHEMA={"type":"object","properties":{"scene":{"type":"string","enum":["blank","text_card","geometry","uncertain"]}},
        "required":["scene"],"additionalProperties":False}
PROMPT=("Examine a imagem inteira. Escolha UMA categoria exclusiva: "
        "text_card se há palavras ou letras realmente escritas, inclusive se também houver figuras; "
        "geometry se há formas, desenhos ou linhas visíveis, mas nenhum texto escrito; "
        "blank somente se todo o fundo está vazio e uniforme, sem formas nem texto; "
        "uncertain se não conseguir distinguir. Não confunda círculos desenhados com letras O. "
        "Não imagine conteúdo ausente. Responda somente o objeto JSON com scene.")
SUITES=("shared","challenge","additional_authored")


def exact_uniform(image):
    # Extrema compare all pixels per channel, not just mean/variance or OCR.
    # Synthetic images are fully opaque L/RGB. Refuse other modes.
    if image.mode not in ("L","RGB") or image.size!=(960,540):
        raise base.VLMError("VLM_V2_IMAGE_INVALID")
    extrema=image.getextrema()
    bands=(extrema,) if image.mode=="L" else extrema
    return all(low==high for low,high in bands)


def parse_scene(raw):
    try:
        v=json.loads(raw)
    except (TypeError,ValueError):
        return None
    if not isinstance(v,dict) or set(v)!={"scene"} or v["scene"] not in SCHEMA["properties"]["scene"]["enum"]:
        return None
    return v["scene"]


def derived(scene):
    if scene is None:
        return None
    return {"scene":scene,"text_present":"yes" if scene=="text_card" else "uncertain" if scene=="uncertain" else "no"}


def observe(image,infer):
    raw=base.encode_image(image)
    if exact_uniform(image):
        return {"prediction":derived("blank"),"model_scene":None,"response_sha256":None,
                "inference_attempted":False,"guard_reason":"EXACT_UNIFORM_PIXELS","inference_ms":0.0}
    start=time.perf_counter()
    response=infer(raw)
    scene=parse_scene(response)
    # A nonuniform fixture cannot meet this benchmark's literal blank
    # definition. Abstain; do not infer geometry or text from nonuniformity.
    adjusted="uncertain" if scene=="blank" else scene
    return {"prediction":derived(adjusted),"model_scene":scene,
            "response_sha256":sha256(response.encode()).hexdigest(),
            "inference_attempted":True,"guard_reason":"NONUNIFORM_BLANK_CONFLICT" if scene=="blank" else None,
            "inference_ms":round((time.perf_counter()-start)*1000,3)}


def extra_frames():
    from PIL import Image,ImageDraw,ImageFont
    rows=[]
    specs=(("cream_blank","blank"),("navy_blank","blank"),("triangle_line","geometry"),
           ("gray_shapes","geometry"),("letters_ooo","text_card"),("dark_caption","text_card"))
    for cid,scene in specs:
        rgb=(245,235,205) if cid=="cream_blank" else (15,30,70) if cid in ("navy_blank","dark_caption") else (235,235,235)
        image=Image.new("RGB",(960,540),rgb)
        d=ImageDraw.Draw(image)
        if cid=="triangle_line":
            d.polygon(((100,390),(300,80),(500,390)),outline=(20,50,90),width=8)
            d.line((620,100,850,390),fill=(170,40,30),width=12)
        elif cid=="gray_shapes":
            d.rectangle((110,120,330,360),fill=(70,70,70))
            d.ellipse((520,130,770,380),outline=(50,50,50),width=12)
        elif scene=="text_card":
            text="OOO" if cid=="letters_ooo" else "Revise suas metas"
            d.text((100,270),text,font=ImageFont.load_default(size=52),fill=(15,15,15) if cid=="letters_ooo" else (245,245,245),anchor="lm")
        rows.append({"case_id":cid,"suite":"additional_authored","image":image,"media_sha256":None,
                     "timestamp_s":None,"expected":derived(scene),"ocr_positive_candidate":None})
    return rows


def _score(group):
    result={}
    for field in ("scene","text_present"):
        labels=sorted({r["expected"][field] for r in group})
        per_class={}
        for label in labels:
            expected=[r for r in group if r["expected"][field]==label]
            correct=sum(r["prediction"] is not None and r["prediction"][field]==label for r in expected)
            per_class[label]={"expected":len(expected),"correct":correct,"recall":correct/len(expected)}
        wrong=sum(r["prediction"] is not None and r["prediction"][field] not in ("uncertain",r["expected"][field]) for r in group)
        invalid=sum(r["prediction"] is None for r in group)
        result[field]={"per_class":per_class,"wrong_nonabstained":wrong,"invalid":invalid,
                       "abstentions":sum(r["prediction"] is not None and r["prediction"][field]=="uncertain" for r in group),
                       "engineering_gate_passed":bool(per_class) and wrong==0 and invalid==0 and all(m["recall"]>=0.75 for m in per_class.values())}
    return result


def metrics(rows):
    suites={}
    complete=len(rows)==26 and len({r["case_id"] for r in rows})==26
    for suite,expected_count in zip(SUITES,(14,6,6)):
        group=[r for r in rows if r["suite"]==suite]
        unique={}
        for r in group:
            h=r["image_png_sha256"]
            if h in unique and any(unique[h][k]!=r[k] for k in ("expected","prediction")):
                raise base.VLMError("VLM_V2_DUPLICATE_CONFLICT")
            unique[h]=r
        complete=complete and len(group)==expected_count and set(r["expected"]["scene"] for r in group)=={"blank","geometry","text_card"}
        suites[suite]={"positions":_score(group),"unique_images":_score(list(unique.values())),
                       "position_count":len(group),"unique_image_count":len(unique)}
    gate=complete and all(m["engineering_gate_passed"] for s in suites.values()
                            for scope in ("positions","unique_images") for m in s[scope].values())
    return {"suites":suites,"engineering_gate_passed":bool(gate),
            "gate_criteria":{"each_class_min_recall":0.75,"wrong_nonabstained":0,"invalid":0,
                             "all_26_positions_required":True,"both_position_and_unique_metrics_required":True}}


def benchmark(report,model_dir,executable):
    capacity=base.plan(model_dir)
    if not capacity["run_memory_ready"] or not capacity["run_disk_ready"]:
        raise base.VLMError("VLM_RESOURCE_PREFLIGHT_BLOCKED")
    checkpoint=base.verify_checkpoint(model_dir)
    runtime=base.verify_runtime(executable)
    frames=base.make_frames(report)+extra_frames()
    rows=[]
    cache={}
    start=time.perf_counter()
    with base.local_server(executable,model_dir,schema=SCHEMA,prompt=PROMPT) as infer:
        load_ms=round((time.perf_counter()-start)*1000,3)
        for frame in frames:
            image=frame.pop("image")
            digest=sha256(base.encode_image(image)).hexdigest()
            reused=digest in cache
            if not reused:
                cache[digest]=observe(image,infer)
            obs=cache[digest]
            rows.append({**frame,**obs,"image_png_sha256":digest,
                         "inference_ms":0 if reused else obs["inference_ms"],
                         "reused_identical_image_result":reused})
    if base.verify_checkpoint(model_dir)!=checkpoint or base.verify_runtime(executable)!=runtime:
        raise base.VLMError("VLM_RUNTIME_OR_MODEL_CHANGED")
    return {"status":"VLM_SINGLE_SCENE_BENCHMARK_COMPLETED","policy_version":VERSION,
            "model_id":base.MODEL_ID,"model_revision":base.MODEL_REVISION,"checkpoint":checkpoint,"runtime":runtime,
            "capacity_preflight":capacity,"model_load_ms":load_ms,"prompt_sha256":sha256(PROMPT.encode()).hexdigest(),
            "unique_images":len(cache),"unique_model_calls":sum(v["inference_attempted"] for v in cache.values()),
            "uniform_guard_unique_images":sum(v["guard_reason"]=="EXACT_UNIFORM_PIXELS" for v in cache.values()),
            "cases":rows,**metrics(rows),"synthetic_only":True,"vlm_evaluated":True,
            "source_report_consistency_revalidated":True,"shared_pixels_hash_matched":True,"source_container_redecoded":False,
            "network_scope":"authenticated_local_loopback_only","derived_text_presence_not_independent":True,
            "independent_gold":False,"real_media_processed":0,"real_media_processing_allowed":False,
            "external_data_accessed":False,"database_mutated":False,"scientific_admissions":0,
            "rubric_assessments_written":0,"production_approved":False}
