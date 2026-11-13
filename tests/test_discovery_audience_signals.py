import hashlib
import pytest
from tapi_gate0.discovery_audience_signals import assess_caption, sampling_sector

@pytest.mark.parametrize('caption,status',[
 ('Se você é MEI, organize suas contas.', 'EXPLICIT_AUDIENCE_SIGNAL'),
 ('Dicas para pequenas empresas.', 'EXPLICIT_AUDIENCE_SIGNAL'),
 ('Atenção, microempreendedoras!', 'EXPLICIT_AUDIENCE_SIGNAL'),
 ('Proteja seu pequeno negócio.', 'EXPLICIT_AUDIENCE_SIGNAL'),
 ('O número de MEIs cresceu.', 'MENTION_ONLY_UNCERTAIN'),
 ('Empreender exige coragem.', 'NO_EXPLICIT_SIGNAL_ABSTAIN'),
 ('meioteca', 'NO_EXPLICIT_SIGNAL_ABSTAIN'),
 ('Não é para MEIs.', 'EXPLICIT_AUDIENCE_SIGNAL'),
])
def test_signals(caption,status):
    r=assess_caption(caption)
    assert r['signal_status']==status
    assert r['targeting_decision']=='not_assessed' and not r['scientific_admission'] and not r['human_review']
    assert r['caption_sha256']==hashlib.sha256(caption.encode()).hexdigest()
    assert all(0<=x['start']<x['end']<=len(caption) for x in r['evidence_spans'])
    assert 'caption' not in r

@pytest.mark.parametrize('caption',['', '  ',None,'a'*10001])
def test_invalid(caption):
    with pytest.raises(ValueError): assess_caption(caption)

def test_bounded_evidence():
    r=assess_caption('Para MEIs. '*30)
    assert len(r['evidence_spans'])==20 and r['evidence_truncated']

def test_sector():
    assert sampling_sector('ecommerce_education')=='commerce'
    assert sampling_sector('foodservice_association_regional')=='food'
    assert sampling_sector('unrecognized')=='other'
