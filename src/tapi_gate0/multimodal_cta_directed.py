"""IMP-064: experimental directed-request grounding after CTA v1 failure.

Development examples are the already observed v1 challenge; new authored
challenge is separate, not independent gold. No media or canonical writes.
"""
import re
from hashlib import sha256
from . import multimodal_fusion as fusion
from . import multimodal_semantic_replay as replay
from . import multimodal_cta_challenge as original
from .discovery_rubric_grounded import rule_evidence,UNKNOWN

VERSION="bd-cta-directed-request.v2"
# Require an action and a publication/channel object in the SAME fragment.
# No concatenation across modalities or ASR segments. Conservative syntax,
# not a general-purpose speech-act parser.
BOUNDARY=r"(?:^|[.!?;]\s*|\be\s+)"
OBJECT=r"(?:est[ea]|ess[ea]|[oa])\s+(?:post|v[ií]deo|conte[úu]do|publica[çc][ãa]o|material|guia|lista(?: de tarefas)?|dica|carrossel)"
PATTERNS={
    "salvar":rf"(?:salve|salvem|guarde|guardem)\s+{OBJECT}\b|(?:adicione|coloque)\s+{OBJECT}\s+(?:aos|nos)\s+(?:seus\s+)?favoritos\b",
    "comentar":r"(?:comente|comentem)\s+[^.!?;\n]{2,100}|(?:deixe|deixem|escreva|escrevam)\s+(?:a\s+)?(?:sua\s+)?(?:opini[ãa]o|d[úu]vida|resposta|experi[êe]ncia)\s+(?:na se[çc][ãa]o de|nos)\s+coment[áa]rios\b",
    "seguir":r"(?:siga|sigam)\s+(?:(?:est[ea]|ess[ea]|noss[oa]|[oa])\s+)?(?:perfil|canal|p[áa]gina)\b|(?:passe a|comece a|continue a)\s+acompanhar\s+(?:est[ea]|ess[ea]|noss[oa]|[oa])\s+(?:perfil|canal|p[áa]gina)\b",
    "DM":r"(?:envie|mande)\s+(?:uma\s+)?mensagem\s+(?:pelo|no|via)\s+(?:direct|dm|privado)\b|(?:chame|procure)\s+(?:a gente|nos|nossa equipe)\s+(?:no|pelo)\s+(?:privado|direct|dm)\b",
    "link na bio":r"(?:acesse|clique|confira|veja|abra|toque)\s+(?:(?:o|no|pelo)\s+)?(?:link|endere[çc]o)\s+(?:na|da)\s+bio\b",
}
HYPOTHETICAL=r"\b(?:se\s+(?:algu[ée]m|voc[êe]|eu|n[óo]s)|pedisse|pediriam|hipot[ée]tic[oa]|imagine que|suponha que)\b"
BIO_ANTECEDENT=r"\b(?:link|endere[çc]o)\s+(?:na|da)\s+bio\s*;\s*(?:toque|clique)\s+nele\b"

NEW_CASES=(
    ("h01","explicit","salvar",(("caption","Salve esse carrossel para usar no planejamento."),)),
    ("h02","explicit","comentar",(("audio","Comente sua experiência com fornecedores."),)),
    ("h03","explicit","seguir",(("ocr","Siga nossa página."),)),
    ("h04","explicit","DM",(("caption","Mande mensagem pelo direct para saber os detalhes."),)),
    ("h05","explicit","link na bio",(("audio","Clique no link da bio para baixar o guia."),)),
    ("h06","explicit","salvar",(("ocr","Salve esta dica."),("caption","Salve esta dica para consultar depois."))),
    ("h07","paraphrase","salvar",(("audio","Guarde essa publicação para sua próxima consulta."),)),
    ("h08","paraphrase","comentar",(("ocr","Escreva sua experiência nos comentários."),)),
    ("h09","paraphrase","seguir",(("caption","Comece a acompanhar nosso canal de negócios."),)),
    ("h10","paraphrase","DM",(("audio","Procure nossa equipe no privado para conversar."),)),
    ("h11","paraphrase","link na bio",(("ocr","Abra o endereço na bio para obter o checklist."),)),
    ("h12","paraphrase","salvar",(("caption","Coloque este guia nos favoritos."),)),
    ("h13","negative",None,(("audio","Guarde o dinheiro da empresa numa conta separada."),)),
    ("h14","negative",None,(("caption","Os seguidores acompanham as novidades diariamente."),)),
    ("h15","negative",None,(("ocr","A opinião nos comentários foi positiva."),)),
    ("h16","negative",None,(("audio","A equipe respondeu pelo direct ontem."),)),
    ("h17","negative",None,(("caption","O link na bio recebeu muitas visitas."),)),
    ("h18","negative",None,(("audio","Se você guardasse esta publicação, seria apenas uma hipótese."),)),
    ("h19","negative",None,(("caption","Nunca guarde este vídeo desatualizado."),)),
    ("h20","negative",None,(("ocr",'"Siga nosso perfil" era a frase usada na campanha.'),)),
    ("h21","negative",None,(("caption","Guarde este conteúdo."),("audio","Procure nossa equipe no privado."))),
    ("h22","negative",None,(("audio","Guarde essa dica e escreva sua opinião nos comentários."),)),
    ("h23","negative",None,(("caption","Mande uma mensagem"),("ocr","pelo direct."))),
    ("h24","negative",None,(("caption","Acompanhar o fluxo de caixa ajuda a evitar problemas."),)),
)
# Both v1 and v2 must keep unknowns as unknown. v1 remains untouched.
VARIANTS=(*replay.VARIANTS,"directed_rule","directed_hybrid")


def directed_evidence(text):
    old=rule_evidence("tipo_cta",text)
    result={"value":UNKNOWN,"reason":"NO_DIRECTED_REQUEST","spans":[]}
    if old["reason"] in ("CONTEXT_GUARD","MULTIPLE_ANCHORS") or re.search(HYPOTHETICAL,text,re.I):
        return {**result,"reason":"CONTEXT_VETO"}
    matches={}
    for label,pattern in PATTERNS.items():
        hits=list(re.finditer(BOUNDARY+"("+pattern+")",text,re.I))
        if hits:
            matches[label]=[(m.start(1),m.end(1)) for m in hits]
    hits=list(re.finditer(BIO_ANTECEDENT,text,re.I))
    if hits:
        matches.setdefault("link na bio",[]).extend((m.start(),m.end()) for m in hits)
    if len(matches)!=1:
        return {**result,"reason":"MULTIPLE_REQUESTS" if matches else result["reason"]}
    label,spans=next(iter(matches.items()))
    if old["rule_value"] not in (UNKNOWN,label):
        return {**result,"reason":"CONTEXT_VETO"}
    return {"value":label,"reason":"DIRECTED_ACTION_AND_OBJECT",
            "spans":[{"start":a,"end":b,"sha256":sha256(text[a:b].encode()).hexdigest()} for a,b in spans]}


def directed_decision(preds,*,hybrid):
    if any(p["directed"]["reason"] in ("CONTEXT_VETO","MULTIPLE_REQUESTS") for p in preds):
        return None
    labels={p["directed"]["value"] for p in preds}-{UNKNOWN}
    lexical={p["rule"]["rule_value"] for p in preds}-{UNKNOWN}
    if len(labels)!=1 or (lexical and lexical!=labels):
        return None
    label=next(iter(labels))
    if hybrid:
        models={p["model_consensus"] for p in preds}-{UNKNOWN}
        if models!={label} or not any(p["directed"]["value"]==label and p["model_consensus"]==label for p in preds):
            return None
    return label


def score(rows,cases):
    if [(r["case_id"],r["stratum"],r["expected"]) for r in rows]!=[(c[0],c[1],c[2]) for c in cases]:
        raise ValueError("CTA_DIRECTED_PARTITION_INVALID")
    result={}
    for v in VARIANTS:
        groups={}
        for s in (*original.STRATA,"all"):
            group=[r for r in rows if s=="all" or r["stratum"]==s]
            expected=sum(r["expected"] is not None for r in group)
            correct=sum(r["expected"] is not None and r["values"][v]==r["expected"] for r in group)
            wrong=sum(r["values"][v] is not None and r["values"][v]!=r["expected"] for r in group)
            groups[s]={"cases":len(group),"expected_candidates":expected,"correct_candidates":correct,
                       "wrong_nonabstained":wrong,"abstentions":sum(r["values"][v] is None for r in group),
                       "candidate_recall":correct/expected if expected else None,
                       "candidate_precision":correct/(correct+wrong) if correct+wrong else None}
        result[v]={"strata":groups,"engineering_gate_passed":groups["all"]["wrong_nonabstained"]==0 and
            all(groups[s]["candidate_recall"]>=original.MIN_RECALL for s in ("explicit","paraphrase"))}
    return result


def run_challenge(extractor):
    rows=[]
    splits={}
    for split,cases in (("observed_development",original.CASES),("additional_authored",NEW_CASES)):
        group=[]
        for cid,stratum,expected,parts in cases:
            asset=sha256(("directed-surrogate:"+cid).encode()).hexdigest()
            fragments=[fusion.fragment(asset,m,t,{"source":"authored_text_surrogate","index":i}) for i,(m,t) in enumerate(parts)]
            preds=[{**replay.fragment_predictions(extractor,f,"tipo_cta"),"directed":directed_evidence(f["text"])} for f in fragments]
            values={v:replay.select_field(preds,fusion.MODALITIES,v)["value"] for v in replay.VARIANTS}
            values.update(directed_rule=directed_decision(preds,hybrid=False),directed_hybrid=directed_decision(preds,hybrid=True))
            group.append({"case_id":cid,"split":split,"stratum":stratum,"expected":expected,
                          "fragments":fragments,"fragment_predictions":preds,"values":values})
        splits[split]=score(group,cases)
        rows.extend(group)
    return {"status":"CTA_DIRECTED_CHALLENGE_COMPLETED","policy_version":VERSION,
            "cases":rows,"splits":splits,"engineering_gate_passed":all(s["directed_hybrid"]["engineering_gate_passed"] for s in splits.values()),
            "gate_criteria":{"min_recall_each_positive_stratum":original.MIN_RECALL,"wrong_nonabstained":0,"both_splits_required":True},
            "reference_kind":"authored_text_surrogates_not_extracted_media","automatic_variant_selected":False,
            "synthetic_only":True,"independent_gold":False,"real_media_processed":0,"real_media_processing_allowed":False,
            "external_data_accessed":False,"database_mutated":False,"scientific_admissions":0,
            "rubric_assessments_written":0,"production_approved":False}
