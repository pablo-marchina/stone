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


@pytest.mark.parametrize("stratum,creator,context_sector,analytic_sector",[
    ("inclusive_microenterprise_support","sector_organization","cross_sector","other"),
    ("digital_marketing_education","educator_expert","services","services"),
    ("beauty_entrepreneurship_education","sector_brand","beauty","beauty"),
    ("foodservice_platform_education","sector_brand","food","food"),
    ("fashion_microenterprise_inclusion","sector_organization","commerce","commerce"),
    ("ecommerce_logistics","sector_brand","commerce","commerce"),
    ("artisan_market_access","sector_organization","commerce","commerce"),
    ("pet_retail_education","educator_expert","commerce","commerce"),
    ("retail_digital_training","sector_organization","commerce","commerce"),
])
def test_expanded_sampling_context(stratum,creator,context_sector,analytic_sector):
    from types import SimpleNamespace
    from tapi_gate0.discovery_caption_research import source_description
    source=SimpleNamespace(username="fixture",expected_ig_id="12345",sampling_stratum=stratum,
        source_evidence_reference="fixture-source-reference",audience_rationale_reference="fixture-rationale",
        audience_intent="mpe_targeted")
    context=source_description(source)
    assert context["creator_type_candidate"]==creator
    assert context["sector_context_candidate"]==context_sector
    assert context["business_size_class"]=="unknown"
    assert sampling_sector(stratum)==analytic_sector
