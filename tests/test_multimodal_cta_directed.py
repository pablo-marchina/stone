import pytest
from tapi_gate0 import multimodal_cta_directed as directed
from tapi_gate0 import multimodal_semantic_replay as replay
from tapi_gate0.discovery_rubric_grounded import UNKNOWN


@pytest.mark.parametrize("text,value",[
    ("Guarde este vídeo para consultar depois.","salvar"),
    ("Escreva sua experiência nos comentários.","comentar"),
    ("Siga nossa página.","seguir"),
    ("Chame a gente no privado.","DM"),
    ("Abra o endereço na bio para obter o guia.","link na bio"),
    ("Adicione esta publicação aos seus favoritos.","salvar"),
    ("A loja salvou os dados ontem.",UNKNOWN),
    ("Guarde o dinheiro da empresa.",UNKNOWN),
    ("Não guarde este vídeo.",UNKNOWN),
    ("Guarde este vídeo e escreva sua opinião nos comentários.",UNKNOWN),
    ("Se alguém pedisse para acompanhar o perfil?",UNKNOWN),
    ("Clique no link",UNKNOWN),
])
def test_directed_action_object(text,value):
    result=directed.directed_evidence(text)
    assert result["value"]==value
    if value!=UNKNOWN:
        import hashlib
        for s in result["spans"]:
            assert hashlib.sha256(text[s["start"]:s["end"]].encode()).hexdigest()==s["sha256"]


def test_hybrid_requires_same_fragment_and_preserves_conflicts():
    def p(text,model):
        return {"rule":replay.rule_evidence("tipo_cta",text),
                "directed":directed.directed_evidence(text),"model_consensus":model}
    a=p("Guarde este vídeo.","salvar")
    assert directed.directed_decision([a],hybrid=True)=="salvar"
    assert directed.directed_decision([a,p("Comente sua dúvida abaixo.","comentar")],hybrid=True) is None
    assert directed.directed_decision([a,p("Não salve este post.",UNKNOWN)],hybrid=False) is None
    a=p("Guarde este vídeo.",UNKNOWN)
    assert directed.directed_decision([a,p("O vídeo foi salvo.","salvar")],hybrid=True) is None


def test_complete_two_splits_no_automatic_promotion(monkeypatch):
    monkeypatch.setattr(replay,"candidate",lambda *_:UNKNOWN)
    r=directed.run_challenge(None)
    assert len(r["cases"])==48
    assert set(r["splits"])=={"observed_development","additional_authored"}
    assert not r["engineering_gate_passed"] and not r["automatic_variant_selected"]
    for split in r["splits"].values():
        assert split["directed_rule"]["strata"]["negative"]["wrong_nonabstained"]==0
        assert split["directed_hybrid"]["strata"]["all"]["correct_candidates"]==0
