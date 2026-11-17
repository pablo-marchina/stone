"""IMP-063: OCR cross-view consensus, synthetic baseline and challenge.

Same engine and language weights: agreement is not independent confirmation.
Only generated images are accepted by the benchmark. No canonical evidence.
"""
from pathlib import Path
from time import perf_counter
import shutil
import tempfile
import unicodedata

from . import multimodal_ocr as base
from .multimodal_asr import _file_hash,word_errors,require_temp_capacity
from .multimodal_temporal import _run

VERSION="bd-ocr-consensus.v2"
MIN_CONFIDENCE=60.0
MIN_IOU=0.5
CHALLENGE=(
    ("inventory","Confira seu estoque",False,44),
    ("margin","Margem de contribuição",True,42),
    ("single_word","Vendas",False,40),
    ("delivery","Avise sobre a entrega",False,30),
    ("offer","Oferta de hoje",True,36),
    ("low_contrast","Planeje seu caixa",False,36),
    ("blank_gray","",False,40),
    ("geometry_lines","",False,40),
    ("geometry_circles","",True,40),
)


def normalized_token(text):
    return unicodedata.normalize("NFC",text).casefold().strip()


def box_iou(a,b):
    x,y,w,h=a
    X,Y,W,H=b
    overlap=max(0,min(x+w,X+W)-max(x,X))*max(0,min(y+h,Y+H)-max(y,Y))
    return overlap/(w*h+W*H-overlap)


def consensus_words(first,second):
    """Retain only unique reciprocal matches; never invent spelling/boxes."""
    left={i:[] for i in range(len(first))}
    right={j:[] for j in range(len(second))}
    for i,a in enumerate(first):
        token=normalized_token(a["text"])
        if a["confidence_raw"]<MIN_CONFIDENCE or not any(c.isalnum() for c in token):
            continue
        for j,b in enumerate(second):
            if b["confidence_raw"]<MIN_CONFIDENCE or token!=normalized_token(b["text"]):
                continue
            iou=box_iou(a["box_px"],b["box_px"])
            if iou>=MIN_IOU:
                left[i].append((j,iou))
                right[j].append(i)
    accepted=[]
    for i,a in enumerate(first):
        if len(left[i])!=1:
            continue
        j,iou=left[i][0]
        if right[j]!=[i]:
            continue
        accepted.append({**a,"supporting_word":second[j],"spatial_iou":round(iou,6),
                         "primary_index":i,"supporting_index":j,
                         "agreement_kind":"same_engine_cross_view_not_independent"})
    return accepted


def prepare_view(source,target):
    from PIL import Image,ImageOps,ImageStat
    with Image.open(source) as opened:
        if opened.size!=(base.WIDTH,base.HEIGHT):
            raise base.OCRError("OCR_VIEW_SIZE_INVALID")
        im=opened.convert("L")
    border=im.crop((0,0,im.width,16))
    inverted=ImageStat.Stat(border).median[0]<128
    if inverted:
        im=ImageOps.invert(im)
    im=ImageOps.autocontrast(im)
    im.save(target,format="PNG")
    return {"view_sha256":_file_hash(target),"inverted":inverted,
            "transform":"border_polarity_autocontrast_no_geometry_change"}


def supporting_tsv(binary,path,tessdata):
    return _run(binary,[str(path),"stdout","--tessdata-dir",str(tessdata),
                        "-l","por+eng","--oem","1","--psm","6",
                        "-c","tessedit_create_tsv=1","-c","tessedit_create_txt=0"],
                output_limit=1_000_000)


def generate_challenge(path,fixture):
    from PIL import Image,ImageDraw,ImageFont
    cid,text,inverted,size=fixture
    bg,fg=(20,240) if inverted else (250,15)
    if cid=="low_contrast":
        bg,fg=180,115
    if cid=="blank_gray":
        bg=140
    im=Image.new("L",(base.WIDTH,base.HEIGHT),bg)
    draw=ImageDraw.Draw(im)
    if text:
        draw.text((96,base.HEIGHT//2),text,font=ImageFont.load_default(size=size),fill=fg,anchor="lm")
    elif cid=="geometry_lines":
        for i in range(3):
            draw.rectangle((80+i*220,100+i*40,180+i*220,200+i*40),outline=fg,width=6)
        draw.line((100,400,800,400),fill=fg,width=8)
    elif cid=="geometry_circles":
        for i in range(3):
            draw.ellipse((100+i*220,160,230+i*220,290),outline=fg,width=8)
    im.save(path,format="PNG")
    return _file_hash(path)


def score_row(cid,reference,words):
    text=" ".join(w["text"] for w in words)
    return {"case_id":cid,"reference":reference,"transcript":text,"words":words,
            **word_errors(reference,text),**base.character_errors(reference,text)}


def score_suite(cases,fixtures):
    positives=[c for c in cases if c["reference_words"]>0]
    negatives=[c for c in cases if not c["reference_words"]]
    total=sum(c["reference_words"] for c in positives)
    errors=sum(c["word_errors"] for c in positives)
    chars=sum(c["reference_characters"] for c in positives)
    cer=sum(c["character_errors"] for c in positives)/chars if chars else None
    wer=errors/total if total else None
    inserted=sum(c["hypothesis_words"] for c in negatives)
    complete=len(cases)==len(fixtures) and {c["case_id"] for c in cases}=={f[0] for f in fixtures}
    passed=(complete and wer is not None and wer<=base.MAX_WER
            and all(c["wer"]<=base.MAX_CASE_WER for c in positives)
            and inserted==0 and all(not c["words"] for c in negatives))
    return {"reference_words":total,"word_errors":errors,"pooled_wer":wer,"pooled_cer":cer,
            "negative_inserted_words":inserted,"negative_detected_boxes":sum(len(c["words"]) for c in negatives),
            "engineering_gate_passed":bool(passed)}


def run_ocr_consensus_benchmark(tessdata_dir):
    from PIL import __version__ as pillow_version
    require_temp_capacity()
    before=base.verify_tessdata(tessdata_dir)
    binary=shutil.which("tesseract")
    if not binary:
        raise base.OCRError("OCR_LOCAL_BINARY_UNAVAILABLE")
    runtime=_run(binary,["--version"],output_limit=100000).decode("utf-8","replace").splitlines()[0]
    cases=[]
    suites={}
    with tempfile.TemporaryDirectory(prefix="tapi-ocr-consensus-") as temp:
        for suite,fixtures,generator in (("baseline",base.FIXTURES,base.generate_image),
                                        ("challenge",CHALLENGE,generate_challenge)):
            rows=[]
            for fixture in fixtures:
                cid,reference,_,_=fixture
                path=Path(temp)/(suite+"_"+cid+".png")
                view=Path(temp)/(suite+"_"+cid+"_view.png")
                digest=generator(path,fixture)
                provenance=prepare_view(path,view)
                start=perf_counter()
                first=base.parse_tsv(base.ocr_tsv(binary,path,tessdata_dir))
                second=base.parse_tsv(supporting_tsv(binary,view,tessdata_dir))
                accepted=consensus_words(first,second)
                elapsed=round((perf_counter()-start)*1000,3)
                if _file_hash(path)!=digest or _file_hash(view)!=provenance["view_sha256"]:
                    raise base.OCRError("OCR_FIXTURE_CHANGED")
                row={**score_row(cid,reference,accepted),"suite":suite,"image_sha256":digest,
                     "image_dimensions_px":[base.WIDTH,base.HEIGHT],"supporting_view":provenance,
                     "primary":score_row(cid,reference,first),"supporting":score_row(cid,reference,second),
                     "primary_word_count":len(first),"supporting_word_count":len(second),
                     "accepted_word_count":len(accepted),"discarded_primary_word_count":len(first)-len(accepted),
                     "complete_primary_sequence_retained":bool(first) and len(first)==len(accepted),
                     "complete_text_verified":False,
                     "inference_ms":elapsed,"observation_status":"candidate" if accepted else "abstained",
                     "abstention_reason":None if accepted else "NO_RECIPROCAL_CROSS_VIEW_AGREEMENT"}
                rows.append(row)
                cases.append(row)
            suites[suite]={key:score_suite([r if key=="consensus" else r[key] for r in rows],fixtures)
                           for key in ("primary","supporting","consensus")}
    if before!=base.verify_tessdata(tessdata_dir):
        raise base.OCRError("OCR_LANGUAGE_DATA_CHANGED")
    return {"status":"OCR_CONSENSUS_BENCHMARK_COMPLETED","policy_version":VERSION,
            "synthetic_only":True,"runtime_versions":{"tesseract":runtime,"pillow":pillow_version},
            "language_data_sha256":before,"language_data_independently_verified":False,
            "consensus_policy":{"min_raw_confidence":MIN_CONFIDENCE,"min_box_iou":MIN_IOU,
                                "exact_normalized_token":True,"reciprocal_unique_match":True},
            "gate_criteria":{"max_pooled_wer":base.MAX_WER,"max_case_wer":base.MAX_CASE_WER,
                             "negative_words":0,"both_suites_required":True},
            "suites":suites,"cases":cases,
            "engineering_gate_passed":all(s["consensus"]["engineering_gate_passed"] for s in suites.values()),
            "ocr_evaluated_on_synthetic":True,"ocr_validated_on_real_media":False,
            "independent_gold":False,"real_media_processed":0,"real_media_processing_allowed":False,
            "external_data_accessed":False,"database_mutated":False,"scientific_admissions":0,
            "rubric_assessments_written":0,"production_approved":False}
