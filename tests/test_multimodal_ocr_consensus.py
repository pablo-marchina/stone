import json
import hashlib

import pytest

from tapi_gate0 import multimodal_ocr_consensus as ocr
from tapi_gate0 import multimodal_ocr as base


def word(text,box=(10,10,40,20),conf=95):
    return {"text":text,"box_px":list(box),"confidence_raw":conf,
            "text_sha256":hashlib.sha256(text.encode()).hexdigest()}


def test_exact_token_and_spatial_agreement():
    a=word("Preço")
    b=word("PREÇO",(12,10,40,20))
    r=ocr.consensus_words([a],[b])
    assert len(r)==1 and r[0]["text"]=="Preço" and r[0]["supporting_word"]==b
    assert r[0]["spatial_iou"]==pytest.approx(38/42,abs=1e-6)
    assert not ocr.consensus_words([a],[word("Preco")])
    assert not ocr.consensus_words([a],[word("Preço",(90,90,40,20))])
    assert not ocr.consensus_words([a],[word("Preço",conf=59)])


def test_ambiguous_reciprocal_matches_abstain():
    a=word("vendas")
    assert not ocr.consensus_words([a],[a,a])
    assert not ocr.consensus_words([a,a],[a])
    assert not ocr.consensus_words([word(".")],[word(".")])
    assert len(ocr.consensus_words([a,word("vendas",(100,10,40,20))],
                                  [a,word("vendas",(100,10,40,20))]))==2


def test_partial_words_are_not_silently_reconstructed():
    rows=ocr.consensus_words([word("fluxo"),word("caixa",(60,10,40,20))],[word("fluxo")])
    r=ocr.score_row("fixture","fluxo caixa",rows)
    assert r["transcript"]=="fluxo" and r["wer"]==0.5


def test_suite_requires_zero_negatives_and_all_cases():
    fixtures=base.FIXTURES
    rows=[ocr.score_row(cid,ref,[word(w) for w in ref.split()]) for cid,ref,_,_ in fixtures]
    assert ocr.score_suite(rows,fixtures)["engineering_gate_passed"]
    assert not ocr.score_suite(rows[:-1],fixtures)["engineering_gate_passed"]
    rows[-1]=ocr.score_row("geometry","",[word("mão")])
    assert not ocr.score_suite(rows,fixtures)["engineering_gate_passed"]


def test_view_keeps_geometry_and_deterministic_hash(tmp_path):
    from PIL import Image
    a=tmp_path/"source.png"
    b=tmp_path/"view.png"
    base.generate_image(a,base.FIXTURES[1])
    r=ocr.prepare_view(a,b)
    assert r["inverted"]
    assert r==ocr.prepare_view(a,b)
    with Image.open(a) as x, Image.open(b) as y:
        assert x.size==y.size==(base.WIDTH,base.HEIGHT)


def test_challenge_has_single_word_and_negatives(tmp_path):
    assert len(ocr.CHALLENGE)==9
    assert sum(bool(r[1]) for r in ocr.CHALLENGE)==6
    assert any(r[1]=="Vendas" for r in ocr.CHALLENGE)
    for fixture in ocr.CHALLENGE:
        a=tmp_path/"a.png"
        b=tmp_path/"b.png"
        assert ocr.generate_challenge(a,fixture)==ocr.generate_challenge(b,fixture)


def test_cli_private_report_no_overwrite(tmp_path,monkeypatch,capsys):
    from scripts import a6_multimodal_readiness as cli
    monkeypatch.setattr(cli,"ROOT",tmp_path)
    monkeypatch.setattr(ocr,"run_ocr_consensus_benchmark",lambda _:{"cases":[],"engineering_gate_passed":True})
    assert cli.main(["--synthetic-ocr-consensus","--report-name","missing.json"])==2
    assert json.loads(capsys.readouterr().out)["code"]=="OCR_LOCAL_TESSDATA_REQUIRED"
    args=["--synthetic-ocr-consensus","--tessdata-dir",str(tmp_path),"--report-name","consensus.json"]
    assert cli.main(args)==0
    assert cli.main(args)==2


def test_local_consensus_when_installed():
    import os
    import shutil
    from pathlib import Path
    directory=os.environ.get("TAPI_OCR_TEST_TESSDATA")
    if not directory or not shutil.which("tesseract"):
        pytest.skip("explicit local tessdata and Tesseract required")
    r=ocr.run_ocr_consensus_benchmark(Path(directory))
    assert len(r["cases"])==15 and r["real_media_processed"]==0
    assert set(r["suites"])=={"baseline","challenge"}
    assert all(set(x)=={"primary","supporting","consensus"} for x in r["suites"].values())
    assert isinstance(r["engineering_gate_passed"],bool)
