import hashlib
import pytest
from tapi_gate0 import multimodal_vlm_single_scene as scene


def test_single_scene_schema_cannot_contradict_presence():
    assert scene.parse_scene('{"scene":"blank"}')=="blank"
    assert scene.derived("blank")=={"scene":"blank","text_present":"no"}
    assert scene.derived("text_card")["text_present"]=="yes"
    assert scene.derived("uncertain")["text_present"]=="uncertain"
    assert scene.parse_scene('{"scene":"blank","text_present":"yes"}') is None
    assert scene.parse_scene('{"scene":"other"}') is None
    assert scene.parse_scene("null") is None


def test_uniform_guard_and_nonuniform_blank_abstention():
    from PIL import Image
    for mode,color in (("L",250),("RGB",(10,50,90))):
        im=Image.new(mode,(960,540),color)
        r=scene.observe(im,lambda _:pytest.fail("uniform must not call model"))
        assert r["prediction"]==scene.derived("blank") and not r["inference_attempted"]
        assert r["response_sha256"] is None
    im=Image.new("RGB",(960,540),(250,250,250))
    im.putpixel((20,20),(249,250,250))
    assert not scene.exact_uniform(im)
    r=scene.observe(im,lambda _:'{"scene":"blank"}')
    assert r["prediction"]==scene.derived("uncertain") and r["model_scene"]=="blank"
    assert r["guard_reason"]=="NONUNIFORM_BLANK_CONFLICT"
    r=scene.observe(im,lambda _:'{"scene":"geometry"}')
    assert r["prediction"]==scene.derived("geometry") and r["inference_attempted"]
    assert scene.observe(im,lambda _:"bad")["prediction"] is None


def ideal_rows():
    rows=[]
    for suite,count in zip(scene.SUITES,(14,6,6)):
        for i in range(count):
            expected=scene.derived(("blank","geometry","text_card")[i%3])
            rows.append({"suite":suite,"case_id":f"{suite}_{i}",
                         "image_png_sha256":hashlib.sha256(f"{suite}_{i%3}".encode()).hexdigest(),
                         "expected":expected,"prediction":dict(expected)})
    return rows


def test_metrics_require_unique_images_and_all_splits():
    rows=ideal_rows()
    r=scene.metrics(rows)
    assert r["engineering_gate_passed"]
    assert r["suites"]["shared"]["unique_image_count"]==3
    assert r["suites"]["shared"]["position_count"]==14
    assert not scene.metrics(rows[:-1])["engineering_gate_passed"]
    rows[0]["prediction"]=scene.derived("text_card")
    with pytest.raises(scene.base.VLMError,match="DUPLICATE_CONFLICT"):
        scene.metrics(rows)


def test_extra_frames_distinguish_letters_from_geometry():
    frames=scene.extra_frames()
    assert len(frames)==6
    assert sum(scene.exact_uniform(f["image"]) for f in frames)==2
    assert len({hashlib.sha256(scene.base.encode_image(f["image"])).hexdigest() for f in frames})==6
    assert next(f for f in frames if f["case_id"]=="letters_ooo")["expected"]==scene.derived("text_card")
