"""IMP-064: authored CTA stress test on observed-text surrogates.

No media extraction, actual ASR corruption, independent gold or automatic
promotion. All examples and targets fixed in code before model execution.
"""
from hashlib import sha256
from . import multimodal_fusion as fusion
from . import multimodal_semantic_replay as replay

VERSION="bd-multimodal-cta-challenge.v1"
# case_id, stratum, expected unique CTA (None means abstain), modality/text.
CASES=(
    ("e01","explicit","salvar",(("audio","Salve este material para consultar amanhã."),)),
    ("e02","explicit","comentar",(("caption","Comente qual ferramenta você usa na loja."),)),
    ("e03","explicit","seguir",(("ocr","Siga nosso canal de dicas."),)),
    ("e04","explicit","DM",(("audio","Envie uma mensagem pelo direct para conversar."),)),
    ("e05","explicit","link na bio",(("caption","Acesse o link da bio para obter o guia."),)),
    ("e06","explicit","salvar",(("caption","Salve a lista de tarefas."),("audio","Salve a lista de tarefas para sua próxima reunião."))),
    ("p01","paraphrase","salvar",(("audio","Guarde este vídeo para consultar quando precisar."),)),
    ("p02","paraphrase","comentar",(("caption","Deixe sua opinião na seção de comentários."),)),
    ("p03","paraphrase","seguir",(("ocr","Passe a acompanhar este perfil para receber as próximas dicas."),)),
    ("p04","paraphrase","DM",(("audio","Chame a gente no privado para tirar suas dúvidas."),)),
    ("p05","paraphrase","link na bio",(("caption","O material está no endereço da bio; toque nele para abrir."),)),
    ("p06","paraphrase","salvar",(("ocr","Adicione esta publicação aos seus favoritos."),)),
    ("n01","negative",None,(("audio","A loja salvou os dados de vendas ontem."),)),
    ("n02","negative",None,(("caption","O número de seguidores cresceu durante o mês."),)),
    ("n03","negative",None,(("ocr","Comentários dos clientes ajudam a avaliar o serviço."),)),
    ("n04","negative",None,(("audio","Recebemos uma mensagem pelo direct na semana passada."),)),
    ("n05","negative",None,(("caption","O endereço da bio mudou ontem."),)),
    ("n06","negative",None,(("audio","Não guarde este vídeo; ele contém informações desatualizadas."),)),
    ("n07","negative",None,(("caption",'O artigo analisa a frase "Guarde esta publicação".'),)),
    ("n08","negative",None,(("audio","Se alguém pedisse para acompanhar o perfil, o que aconteceria?"),)),
    ("n09","negative",None,(("caption","Salve a lista."),("ocr","Comente sua dúvida abaixo."))),
    ("n10","negative",None,(("audio","Guarde o vídeo e deixe sua opinião nos comentários."),)),
    ("n11","negative",None,(("caption","Clique no link"),("audio","na bio."))),
    ("n12","negative",None,(("audio","Organize as despesas da sua empresa."),)),
)
STRATA=("explicit","paraphrase","negative")
MIN_RECALL=0.75


def score(rows):
    if [(r["case_id"],r["stratum"],r["expected"]) for r in rows]!=[(c[0],c[1],c[2]) for c in CASES]:
        raise ValueError("CTA_CHALLENGE_PARTITION_MISMATCH")
    result={}
    for variant in replay.VARIANTS:
        groups={}
        for stratum in (*STRATA,"all"):
            group=[r for r in rows if stratum=="all" or r["stratum"]==stratum]
            expected=sum(r["expected"] is not None for r in group)
            correct=sum(r["expected"] is not None and r["values"][variant]==r["expected"] for r in group)
            wrong=sum(r["values"][variant] is not None and r["values"][variant]!=r["expected"] for r in group)
            groups[stratum]={"cases":len(group),"expected_candidates":expected,
                "correct_candidates":correct,"wrong_nonabstained":wrong,
                "abstentions":sum(r["values"][variant] is None for r in group),
                "candidate_precision":correct/(correct+wrong) if correct+wrong else None,
                "candidate_recall":correct/expected if expected else None}
        passed=groups["all"]["wrong_nonabstained"]==0 and all(
            groups[s]["candidate_recall"]>=MIN_RECALL for s in ("explicit","paraphrase"))
        result[variant]={"strata":groups,"engineering_gate_passed":passed}
    return result


def run_challenge(extractor):
    rows=[]
    for cid,stratum,expected,parts in CASES:
        asset=sha256(("authored-text-surrogate:"+cid).encode()).hexdigest()
        fragments=[fusion.fragment(asset,modality,text,{"source":"authored_text_surrogate","index":i})
                   for i,(modality,text) in enumerate(parts)]
        predictions=[replay.fragment_predictions(extractor,f,"tipo_cta") for f in fragments]
        decisions={v:replay.select_field(predictions,fusion.MODALITIES,v) for v in replay.VARIANTS}
        rows.append({"case_id":cid,"stratum":stratum,"expected":expected,"fragments":fragments,
                     "fragment_predictions":predictions,"decisions":decisions,
                     "values":{v:d["value"] for v,d in decisions.items()}})
    variants=score(rows)
    return {"status":"MULTIMODAL_CTA_CHALLENGE_COMPLETED","policy_version":VERSION,
            "cases":rows,"variants":variants,
            "engineering_gate_passed":variants["grounded_hybrid"]["engineering_gate_passed"],
            "gate_criteria":{"min_recall_each_positive_stratum":MIN_RECALL,"wrong_nonabstained":0,"all_cases_required":True},
            "reference_kind":"authored_text_surrogates_not_extracted_media",
            "model_only_is_exploratory":True,"automatic_variant_selected":False,
            "synthetic_only":True,"independent_gold":False,"source_bytes_redecoded":False,
            "real_media_processed":0,"real_media_processing_allowed":False,"external_data_accessed":False,
            "database_mutated":False,"scientific_admissions":0,"rubric_assessments_written":0,"production_approved":False}
