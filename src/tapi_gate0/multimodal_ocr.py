"""IMP-063: local OCR on generated images only; never canonical rubric evidence."""
import csv
import io
import math
from hashlib import sha256
from pathlib import Path
import shutil
import tempfile
from time import perf_counter

from .multimodal_temporal import _run
from .multimodal_asr import normalize_words,word_errors,_file_hash

VERSION="bd-ocr-fixture.v1"
WIDTH,HEIGHT=960,540
FIXTURES=(
    ("sales","Organize suas vendas",False,48),
    ("cash","Controle o fluxo de caixa",True,48),
    ("price","Preço e margem de contribuição",False,36),
    ("cta","Salve para revisar depois",True,34),
    ("blank","",False,48),
    ("geometry","",False,48),
)
MAX_WER=0.20
MAX_CASE_WER=0.40


class OCRError(ValueError):
    pass


def verify_tessdata(directory):
    root=Path(directory)
    if not root.is_absolute() or root.resolve()!=root.absolute() or not root.is_dir():
        raise OCRError("OCR_LOCAL_TESSDATA_REQUIRED")
    hashes={}
    for name in ("por","eng"):
        path=root/(name+".traineddata")
        if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=100_000_000:
            raise OCRError("OCR_LANGUAGE_DATA_REQUIRED")
        hashes[name]=_file_hash(path)
    return hashes


def generate_image(path,fixture):
    from PIL import Image,ImageDraw,ImageFont
    cid,text,inverted,size=fixture
    bg,fg=(20,240) if inverted else (250,15)
    im=Image.new("L",(WIDTH,HEIGHT),bg)
    draw=ImageDraw.Draw(im)
    if text:
        font=ImageFont.load_default(size=size)
        draw.text((64,HEIGHT//2),text,font=font,fill=fg,anchor="lm")
    elif cid=="geometry":
        draw.rectangle((80,90,250,210),fill=fg)
        draw.ellipse((420,160,600,340),outline=fg,width=8)
    im.save(path,format="PNG")
    return _file_hash(path)


def parse_tsv(raw):
    if len(raw)>1_000_000:
        raise OCRError("OCR_OUTPUT_TOO_LARGE")
    reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")),delimiter="\t")
    required={"level","left","top","width","height","conf","text"}
    if not required.issubset(reader.fieldnames or ()):
        raise OCRError("OCR_INVALID_TSV")
    words=[]
    for row in reader:
        if row["level"]!="5":
            continue
        text=row["text"].strip()
        if not text:
            continue
        try:
            x,y,w,h=(int(row[k]) for k in ("left","top","width","height"))
            confidence=float(row["conf"])
        except (ValueError,TypeError) as exc:
            raise OCRError("OCR_INVALID_WORD") from exc
        if (len(words)>=256 or len(text)>256 or not 0<=x<WIDTH or not 0<=y<HEIGHT
                or w<=0 or h<=0 or x+w>WIDTH or y+h>HEIGHT
                or not math.isfinite(confidence) or not 0<=confidence<=100):
            raise OCRError("OCR_INVALID_WORD")
        words.append({"text":text,"box_px":[x,y,w,h],"confidence_raw":confidence,
                      "text_sha256":sha256(text.encode("utf-8")).hexdigest()})
    return words


def character_errors(reference,hypothesis):
    ref,hyp=" ".join(normalize_words(reference))," ".join(normalize_words(hypothesis))
    previous=list(range(len(hyp)+1))
    for i,a in enumerate(ref,1):
        current=[i]
        for j,b in enumerate(hyp,1):
            current.append(min(previous[j]+1,current[-1]+1,previous[j-1]+(a!=b)))
        previous=current
    return {"reference_characters":len(ref),"character_errors":previous[-1],
            "cer":previous[-1]/len(ref) if ref else None}


def evaluate(cases):
    speech=[c for c in cases if c["reference_words"]>0]
    negative=[c for c in cases if not c["reference_words"]]
    total=sum(c["reference_words"] for c in speech)
    errors=sum(c["word_errors"] for c in speech)
    chars=sum(c["reference_characters"] for c in speech)
    char_errors=sum(c["character_errors"] for c in speech)
    pooled=errors/total if total else None
    inserted=sum(c["hypothesis_words"] for c in negative)
    complete=len(cases)==len(FIXTURES) and {c["case_id"] for c in cases}=={r[0] for r in FIXTURES}
    passed=complete and len(speech)==4 and len(negative)==2 and pooled is not None and pooled<=MAX_WER and all(c["wer"]<=MAX_CASE_WER for c in speech) and inserted==0 and all(not c["words"] for c in negative)
    return {"pooled_wer":pooled,"pooled_cer":char_errors/chars if chars else None,
            "reference_words":total,"word_errors":errors,"negative_inserted_words":inserted,
            "engineering_gate_passed":bool(passed),
            "gate_criteria":{"max_pooled_wer":MAX_WER,"max_case_wer":MAX_CASE_WER,"negative_words":0}}


def ocr_tsv(binary,path,tessdata_dir):
    # Named tsv config requires tessdata/configs/tsv, absent in minimal
    # language-only directories. Set renderer variables explicitly instead.
    return _run(binary,[str(path),"stdout","--tessdata-dir",str(tessdata_dir),
                        "-l","por+eng","--oem","1","--psm","11",
                        "-c","tessedit_create_tsv=1","-c","tessedit_create_txt=0"],
                output_limit=1_000_000)


def run_ocr_fixture_benchmark(tessdata_dir):
    from PIL import __version__ as pillow_version
    before=verify_tessdata(tessdata_dir)
    binary=shutil.which("tesseract")
    if not binary:
        raise OCRError("OCR_LOCAL_BINARY_UNAVAILABLE")
    runtime=_run(binary,["--version"],output_limit=100000).decode("utf-8","replace").splitlines()[0]
    cases=[]
    with tempfile.TemporaryDirectory(prefix="tapi-ocr-fixtures-") as temp:
        for fixture in FIXTURES:
            cid,reference,_,_=fixture
            path=Path(temp)/(cid+".png")
            digest=generate_image(path,fixture)
            start=perf_counter()
            words=parse_tsv(ocr_tsv(binary,path,tessdata_dir))
            elapsed=round((perf_counter()-start)*1000,3)
            if _file_hash(path)!=digest:
                raise OCRError("OCR_FIXTURE_CHANGED")
            text=" ".join(w["text"] for w in words)
            cases.append({"case_id":cid,"reference":reference,"transcript":text,
                          "image_sha256":digest,"image_dimensions_px":[WIDTH,HEIGHT],
                          "words":words,**word_errors(reference,text),**character_errors(reference,text),
                          "inference_ms":elapsed})
    if before!=verify_tessdata(tessdata_dir):
        raise OCRError("OCR_LANGUAGE_DATA_CHANGED")
    return {"status":"OCR_FIXTURE_BENCHMARK_COMPLETED","policy_version":VERSION,
            "synthetic_only":True,"renderer":"explicit_tsv_variables","runtime_versions":{"tesseract":runtime,"pillow":pillow_version},
            "language_data_sha256":before,"language_data_independently_verified":False,
            "cases":cases,**evaluate(cases),"ocr_evaluated_on_synthetic":True,
            "ocr_validated_on_real_media":False,"independent_gold":False,
            "real_media_processed":0,"real_media_processing_allowed":False,
            "external_data_accessed":False,"database_mutated":False,"scientific_admissions":0,
            "rubric_assessments_written":0,"production_approved":False}
