import os
from pathlib import Path
from hashlib import sha256
import subprocess
import sys

import pytest
from tapi_gate0 import asset_ocr_fixture as a

HEADER=b"level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
PAGE=b"1\t1\t0\t0\t0\t0\t0\t0\t960\t540\t-1\t\n"


def _tsv(words):
    return HEADER+PAGE+b"".join(f"5\t1\t1\t1\t1\t{i}\t{20*i}\t10\t10\t20\t90.5\t{word}\n".encode() for i,word in enumerate(words,1))


def tessdata():
    root=os.getenv("TAPI_OCR_TEST_TESSDATA")
    if not root:
        pytest.skip("explicit TAPI_OCR_TEST_TESSDATA required")
    return Path(root)


@pytest.mark.parametrize("case",["sales","cta","blank"])
def test_real_tesseract_fixture(case):
    data,words=a.fixture(case)
    config,code=a.plan(case,tessdata())
    r=subprocess.run([sys.executable,"-I","-S","-c",code],input=data,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,check=True,
        env={k:os.environ[k] for k in ("SystemRoot","WINDIR") if k in os.environ})
    result=a.result_from_tsv(case,r.stdout)
    if words:
        assert result.state=="observed" and tuple(w.text for w in result.words)==words
        assert result.frame.frame_sha256==sha256(data).hexdigest()
        assert all(w.box_px[2]>0 and 0<=w.confidence_raw<=100 for w in result.words)
    else:
        assert result.state=="abstained" and result.reason=="no_observable_signal"
    assert set(config["language_sha256"])=={"por","eng"}


@pytest.mark.parametrize("case",["sales","cta","blank"])
def test_typed_parser(case):
    data,words=a.fixture(case)
    result=a.result_from_tsv(case,_tsv(words))
    if words:
        assert tuple(w.text for w in result.words)==words
        assert result.frame.frame_sha256==sha256(data).hexdigest()
    else:
        assert result.state=="abstained"


@pytest.mark.parametrize("raw",[b"",HEADER,HEADER+PAGE.replace(b"960",b"999"),
    HEADER+PAGE+b"truncated\n",_tsv(["invented"]),
    HEADER+PAGE+b"5\t1\t1\t1\t1\t1\t0\t0\t10\t20\t95\t\n",
    b"x"*(a.MAX_TSV+1)])
def test_blank_rejects_malformed_or_hallucinated(raw):
    with pytest.raises(ValueError):
        a.result_from_tsv("blank",raw)


@pytest.mark.parametrize("raw",[_tsv(["Organize","suas","vendas"]).replace(b"\t20\t10\t10\t20\t",b"\t959\t10\t10\t20\t"),
    _tsv(["Organize","suas","vendas"]).replace(b"90.5",b"nan"),
    _tsv(["Organize","suas","vendas"]).replace(b"\t2\t40",b"\t1\t40"),
    _tsv(["Organize","vendas","suas"])])
def test_positive_rejects_invalid_geometry_confidence_duplicate_or_order(raw):
    with pytest.raises(ValueError):
        a.result_from_tsv("sales",raw)


def test_configuration_binds_case_and_language_and_runtime(monkeypatch):
    monkeypatch.setattr(a,"_runtime",lambda d:("C:/trusted/tesseract.exe","a"*64,{"por":"b"*64,"eng":"c"*64}))
    p,_=a.plan("sales","C:/trusted/tessdata")
    assert p["configuration_sha256"]!=a.plan("cta","C:/trusted/tessdata")[0]["configuration_sha256"]
    monkeypatch.setattr(a,"_runtime",lambda d:("C:/trusted/tesseract.exe","a"*64,{"por":"d"*64,"eng":"c"*64}))
    q,_=a.plan("sales","C:/trusted/tessdata")
    assert p["configuration_sha256"]!=q["configuration_sha256"]
    monkeypatch.setattr(a,"_runtime",lambda d:("C:/trusted/tesseract.exe","e"*64,{"por":"d"*64,"eng":"c"*64}))
    assert q["configuration_sha256"]!=a.plan("sales","C:/trusted/tessdata")[0]["configuration_sha256"]


def test_unknown_fixture():
    with pytest.raises(ValueError,match="UNKNOWN"):
        a.fixture("other")


@pytest.mark.parametrize("bound",[0,True,131073])
def test_variable_output_bounds_before_job(bound):
    with pytest.raises(a.windows.JobError,match="FIXTURE_BOUNDS"):
        a.windows._run_bounded_fixture("",b"x",lambda:pytest.fail("check called"),limits=a.LIMITS,max_output=bound)
