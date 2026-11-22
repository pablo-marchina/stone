"""Shared AV FAIL diagnostic on authored-shape reports, without model/media.

The real per-asset validator is replaced with an explicit fixture validator;
production always calls the real shared.validate_asset_binding.
"""
from copy import deepcopy
from hashlib import sha256

import pytest
from tapi_gate0 import multimodal_shared_fixture as shared
from tapi_gate0 import multimodal_fusion as fusion
from tapi_gate0 import multimodal_asr as asr
from tapi_gate0 import shared_av_asr_diagnostic as diag


def make_report(monkeypatch, *, negative_speech=False, blank_positive=False):
    checked = []
    def validate(row):
        checked.append(row['case_id'])
        return row['asset_binding_verified']
    monkeypatch.setattr(shared, 'validate_asset_binding', validate)
    rows=[]
    for idx,case in enumerate(shared.CASES):
        cid,caption,reference,screen,late,geometry,topic,cta,has_text=case
        force_neg = negative_speech and cid == 'negative'
        hyp = ('Salve agora' if force_neg else
               '' if blank_positive and cid == 'audio_only' else reference)
        has_asr = bool(reference or force_neg)
        full_hash = sha256(f'{cid}:pcm'.encode()).hexdigest()
        audio_sha = sha256(f'{cid}:chunk'.encode()).hexdigest()
        media_sha = sha256(f'{cid}:asset'.encode()).hexdigest()
        chunks = ([{'start_sample':0,'end_sample':16000,'pcm_sha256':audio_sha,
                    'transcript':hyp}] if has_asr else [])
        segments = ([{'text':hyp,'region_start_sample':0,'region_end_sample':16000,
                     'start_s':0.1,'end_s':0.9,'text_sha256':sha256(hyp.encode()).hexdigest(),
                     'source_pcm_sha256':full_hash,'chunk_pcm_sha256':audio_sha}]
                    if has_asr and hyp else [])
        intervals = ([{'start':0,'end':16000}] if has_asr else [])
        fragments=[]
        if caption:
            fragments.append(fusion.fragment(media_sha,'caption',caption,
                              {'caption_sha256':fusion.digest(caption),
                               'source':'authored_fixture_caption'}))
        if hyp:
            fragments.append(fusion.fragment(media_sha,'audio',hyp,
                              {'start_s':0.1,'end_s':0.9,
                               'source_pcm_sha256':full_hash,
                               'chunk_pcm_sha256':audio_sha,
                               'timestamp_kind':'model_estimate_mapped_to_decoded_pcm_not_original_pts'}))
        row = {'case_id':cid,'caption':caption,'caption_sha256':fusion.digest(caption),
               'expected':{'tema_principal':topic,'tipo_cta':cta,'texto_na_tela':has_text},
               'duration_s':shared.DURATION, 'source_pixels_and_pcm_verified':True,
               'temporal_passed':True,'asset_binding_verified':True,
               'media_sha256':media_sha,'decoded_pcm_sha256':full_hash,
               'vad':{'intervals':intervals,'pcm_sha256':full_hash},
               'audio':{'chunks':chunks,'segments':segments,'asr_calls':len(chunks),
                        'inference_attempted':has_asr, 'pcm_sha256':full_hash,
                        'duration_s':shared.DURATION,'timestamp_kind':'model_estimate_mapped_to_decoded_pcm_not_original_pts',
                        'transcript':hyp},
               'fragments':fragments}
        row['arms']={key:fusion.fuse(media_sha,fragments,mods) for key,mods in fusion.ARMS.items()}
        rows.append(row)
    scores=fusion.evaluate(rows)
    negative_calls=sum(r['audio']['asr_calls'] for r,c in zip(rows,shared.CASES) if not c[2])
    return {
        'status':'SHARED_MULTIMODAL_FIXTURE_BENCHMARK_COMPLETED',
        'policy_version':shared.VERSION,'fusion_policy':fusion.VERSION,
        'synthetic_only':True,'temporal_integrity_passed':True,
        'ocr_language_data_sha256':shared.BEST_HASHES,
        'vad_asset_sha256':shared.VAD_HASH,
        'auxiliary_hashes_match_operator_baseline':True,
        'auxiliary_hashes_independently_verified':False,
        'vlm_evaluated':False,'semantic_scores_calibrated':False,
        'real_media_processing_allowed':False,'external_data_accessed':False,
        'database_mutated':False,'production_approved':False,
        'real_media_processed':0,'scientific_admissions':0,'rubric_assessments_written':0,
        'checkpoint':{'model_id':asr.MEDIUM_MODEL_ID,'model_revision':asr.MEDIUM_REVISION,
                      'weights_sha256':asr.MEDIUM_SHA256,'weights_digest_verified':True},
        'case_count':len(rows),'cases':rows,'negative_asr_calls':negative_calls,
        **scores, 'engineering_gate_passed':bool(scores['engineering_gate_passed'] and negative_calls == 0)
    }, checked


def test_all_seven_shared_cases_diagnosed_without_media_or_gold(monkeypatch):
    report,checks=make_report(monkeypatch)
    before=deepcopy(report)
    d=diag.diagnose_shared_av_asr(report)
    assert report == before
    assert len(d['cases'])==7
    assert checks == [x[0] for x in shared.CASES]
    assert d['negative_transcript_words']==0
    assert d['reference_asr_thresholds_informational_only']['max_case_wer']==.5
    assert d['production_approved'] is False
    assert d['source_bytes_independently_verified'] is False
    assert d['checkpoint_independently_attested'] is False


def test_failed_shared_report_is_diagnosable_not_promoted(monkeypatch):
    report,_=make_report(monkeypatch, blank_positive=True)
    assert report['engineering_gate_passed'] in (True,False)
    d=diag.diagnose_shared_av_asr(report)
    target=next(r for r in d['cases'] if r['case_id']=='audio_only')
    assert target['wer']==1
    assert target['counts']['deletion']==target['reference_words']
    assert 'INFORMATIONAL_CASE_WER_EXCEEDED' in d['failure_and_observation_reasons']
    assert d['global_gates_released'] is False


def test_negative_asr_calls_exposed_without_gate_override(monkeypatch):
    report,_=make_report(monkeypatch, negative_speech=True)
    assert report['negative_asr_calls']==1
    assert report['engineering_gate_passed'] is False
    d=diag.diagnose_shared_av_asr(report)
    assert 'NEGATIVE_ASR_CALLS' in d['failure_and_observation_reasons']
    assert 'NEGATIVE_TRANSCRIPT_WORDS' in d['failure_and_observation_reasons']
    assert d['negative_transcript_words']==2
    assert d['source_shared_engineering_gate_passed'] is False


@pytest.mark.parametrize('corrupt', [
    lambda r:r.update(policy_version='OTHER'),
    lambda r:r.update(independent_gold=True),
    lambda r:r.update(external_data_accessed=True),
    lambda r:r.update(engineering_gate_passed=not r['engineering_gate_passed']),
    lambda r:r['cases'][0].update(case_id='OTHER'),
    lambda r:r['cases'][0].update(caption='tampered caption'),
    lambda r:r['cases'][1]['audio'].update(transcript='changed'),
    lambda r:r['cases'][1]['audio'].update(asr_calls=9),
    lambda r:r['cases'][1]['audio']['chunks'][0].update(transcript='changed'),
    lambda r:r['cases'][1]['vad'].update(pcm_sha256='changed'),
    lambda r:r['cases'][1].update(arms={}),
    lambda r:r['cases'][1]['audio']['segments'][0].update(text_sha256='0'*64),
    lambda r:r['cases'][1].update(fragments=[]),
    lambda r:r.update(negative_asr_calls=2),
    lambda r:r['checkpoint'].update(weights_sha256='f'*64),
    lambda r:r['cases'].reverse(),
])
def test_tampered_report_fail_closed(monkeypatch,corrupt):
    report,_=make_report(monkeypatch)
    corrupt(report)
    with pytest.raises(diag.SharedAVDiagnosticDenied,match='A02_SHARED_AV_REPORT_INVALID'):
        diag.diagnose_shared_av_asr(report)


def test_source_validator_failure_fails_closed(monkeypatch):
    report,_=make_report(monkeypatch)
    monkeypatch.setattr(shared,'validate_asset_binding',lambda row:False)
    with pytest.raises(diag.SharedAVDiagnosticDenied):
        diag.diagnose_shared_av_asr(report)
