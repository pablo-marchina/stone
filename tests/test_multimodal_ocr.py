import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tapi_gate0 import multimodal_ocr as ocr
from tapi_gate0.multimodal_asr import word_errors


HEADER=b"level\tleft\ttop\twidth\theight\tconf\ttext\n"


def test_tsv_locators_and_hash():
    rows=ocr.parse_tsv(HEADER+"5\t12\t20\t50\t32\t96.1\tPreço\n".encode())
    assert rows==[{"text":"Preço","box_px":[12,20,50,32],"confidence_raw":96.1,
                   "text_sha256":hashlib.sha256("Preço".encode()).hexdigest()}]


@pytest.mark.parametrize("row",[b"5\t960\t20\t1\t1\t90\ttext\n",b"5\t1\t1\t0\t1\t90\ttext\n",
                                 b"5\t1\t1\t1\t1\tnan\ttext\n",b"5\t1\t1\t1\t1\t-1\ttext\n"])
def test_invalid_boxes_fail_closed(row):
    with pytest.raises(ocr.OCRError,match="INVALID_WORD"):
        ocr.parse_tsv(HEADER+row)


def test_cer_preserves_accents():
    assert ocr.character_errors("PREÇO!","preço")["cer"]==0
    assert ocr.character_errors("preço","preco")["cer"]==0.2
    assert ocr.character_errors("","abc")["cer"] is None


def test_gate_requires_all_cases_and_no_hallucinated_boxes():
    rows=[{"case_id":cid,"words":[],**word_errors(text,text),**ocr.character_errors(text,text)}
          for cid,text,_,_ in ocr.FIXTURES]
    assert ocr.evaluate(rows)["engineering_gate_passed"]
    assert not ocr.evaluate(rows[:-1])["engineering_gate_passed"]
    rows[-1]["words"]=[{"text":"."}]
    assert not ocr.evaluate(rows)["engineering_gate_passed"]


def test_language_data_required(tmp_path):
    (tmp_path/"eng.traineddata").write_bytes(b"english")
    with pytest.raises(ocr.OCRError,match="LANGUAGE_DATA_REQUIRED"):
        ocr.verify_tessdata(tmp_path)
    (tmp_path/"por.traineddata").write_bytes(b"portuguese")
    assert set(ocr.verify_tessdata(tmp_path))=={"por","eng"}


def test_generated_fixture_is_repeatable(tmp_path):
    first=ocr.generate_image(tmp_path/"a.png",ocr.FIXTURES[0])
    second=ocr.generate_image(tmp_path/"b.png",ocr.FIXTURES[0])
    assert first==second
    assert first!=ocr.generate_image(tmp_path/"c.png",ocr.FIXTURES[-1])


def test_cli_no_media_no_overwrite(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    assert cli.main(["--synthetic-ocr","--report-name","ocr.json"])==2
    assert json.loads(capsys.readouterr().out)["code"]=="OCR_LOCAL_TESSDATA_REQUIRED"
    def fake(directory):
        return {"cases":[],"engineering_gate_passed":True}
    monkeypatch.setattr(ocr,"run_ocr_fixture_benchmark",fake)
    args=["--synthetic-ocr","--tessdata-dir",str(tmp_path),"--report-name","ocr.json"]
    assert cli.main(args)==0
    assert cli.main(args)==2


def test_local_ocr_integration_when_installed():
    import os
    directory=os.environ.get("TAPI_OCR_TEST_TESSDATA")
    if not directory or not shutil.which("tesseract"):
        pytest.skip("explicit TAPI_OCR_TEST_TESSDATA and local Tesseract required")
    report=ocr.run_ocr_fixture_benchmark(Path(directory))
    assert len(report["cases"])==6 and report["real_media_processed"]==0
    # Quality failures are measured and recorded by CLI, not hidden as test failures.
    assert isinstance(report["engineering_gate_passed"],bool)
