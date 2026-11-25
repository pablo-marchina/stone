"""CAP-003 synthetic-only paired semantic rubric challenge; no real data access.

Caption claims are not proof of underlying events, and caption tone is not
audiovisual tone. Unknown is explicit; no candidate is a rubric assessment.
"""
from collections import Counter
from hashlib import sha256
from time import perf_counter

VERSION = "bd-caption-rubric-challenge.v1"
UNKNOWN = "ABSTAIN"
# Canonical labels, descriptive PT prompt labels, descriptive EN prompt labels.
FIELDS = {
    "tema_principal": (
        "tema predominante e inequivoco da legenda", "unambiguous dominant topic of the caption",
        (("vendas","vendas e conversao comercial","sales and commercial conversion"),
         ("finanças","financas fluxo de caixa e custos","finance cash flow and costs"),
         ("marketing","marketing divulgacao e publicidade","marketing promotion and advertising"),
         ("atendimento","atendimento e suporte ao cliente","customer service and support"),
         ("gestão","gestao operacional e organizacao","business operations and organization"),
         ("motivação","motivacao e perseveranca","motivation and perseverance"),
         ("ferramentas/maquininha","ferramentas de pagamento e maquininha","payment tools and card terminals"),
         ("história de empreendedor","historia de vida de empreendedor","entrepreneur personal story"))),
    "tipo_cta": (
        "acao explicita solicitada ao leitor na legenda", "explicit action requested from the caption reader",
        (("comentar","solicita comentar","asks to comment"),("salvar","solicita salvar a publicacao","asks to save the post"),
         ("link na bio","solicita acessar link na bio","asks to visit the bio link"),
         ("DM","solicita enviar mensagem direta","asks to send a direct message"),
         ("seguir","solicita seguir o perfil","asks to follow the account"))),
    "prova_social": (
        "alegacao explicita de prova social na legenda nao sua veracidade", "explicit social proof claim in caption not its truth",
        (("positive_claim","relata depoimento ou recomendacao de cliente ou numero de clientes satisfeitos",
          "states a customer testimonial endorsement or count of satisfied customers"),)),
    "oferta_ou_beneficio_explicito": (
        "oferta ou beneficio concreto explicitamente apresentado ao leitor", "concrete offer or benefit explicitly presented to reader",
        (("positive_claim","oferta ou beneficio concreto explicito","explicit concrete offer or benefit"),)),
    "tom": (
        "tom predominante inequivoco somente da legenda", "unambiguous dominant tone of the caption alone",
        (("informal","conversacional informal","casual conversational"),("técnico","tecnico instrucional preciso","technical precise instructional"),
         ("inspiracional","inspiracional encorajador","inspirational encouraging"),("humorístico","humoristico piada","humorous joke"))),
}
# Frozen authored fixtures, no real posts and no independent annotation.
CASES = (
    ("topic01","tema_principal","vendas","Treine a negociação para fechar mais vendas."),
    ("topic02","tema_principal","finanças","Separe o caixa pessoal do empresarial e calcule os custos fixos."),
    ("topic03","tema_principal","marketing","Planeje anúncios e campanhas de divulgação da marca."),
    ("topic04","tema_principal","atendimento","Responda reclamações dos clientes com escuta ativa e suporte."),
    ("topic05","tema_principal","gestão","Organize o estoque e as tarefas da equipe com um processo semanal."),
    ("topic06","tema_principal","motivação","Não desista do seu sonho. Cada pequeno passo conta."),
    ("topic07","tema_principal","ferramentas/maquininha","Veja como configurar a maquininha para aceitar cartões."),
    ("topic08","tema_principal","história de empreendedor","Comecei vendendo bolos na rua. Anos depois abri minha primeira loja."),
    ("topic09","tema_principal",UNKNOWN,"Hoje falamos de vendas, finanças e marketing, igualmente."),
    ("topic10","tema_principal",UNKNOWN,"Bom dia! Uma semana especial para todos."),
    ("cta01","tipo_cta","comentar","Conte sua experiência nos comentários."),
    ("cta02","tipo_cta","salvar","Salve este post para consultar depois."),
    ("cta03","tipo_cta","link na bio","Acesse o link na bio para conferir o guia."),
    ("cta04","tipo_cta","DM","Envie uma mensagem pelo direct para nossa equipe."),
    ("cta05","tipo_cta","seguir","Siga nosso perfil para mais dicas."),
    ("cta06","tipo_cta",UNKNOWN,"Salve este post e siga nosso perfil."),
    ("cta07","tipo_cta",UNKNOWN,"O relatório menciona o link na bio, sem solicitar cliques."),
    ("cta08","tipo_cta",UNKNOWN,"Não é necessário comentar."),
    ("cta09","tipo_cta",UNKNOWN,"A loja abriu na segunda-feira."),
    ("proof01","prova_social","positive_claim","Uma cliente afirmou: o atendimento resolveu meu problema."),
    ("proof02","prova_social","positive_claim","Mais de 500 clientes satisfeitos recomendaram nosso serviço."),
    ("proof03","prova_social",UNKNOWN,"Queremos conquistar clientes satisfeitos no futuro."),
    ("proof04","prova_social",UNKNOWN,"Aprenda a coletar depoimentos de clientes."),
    ("proof05","prova_social",UNKNOWN,"Ainda não temos avaliações de clientes."),
    ("offer01","oferta_ou_beneficio_explicito","positive_claim","Inscreva-se no curso gratuito de precificação."),
    ("offer02","oferta_ou_beneficio_explicito","positive_claim","Ganhe 20% de desconto na primeira compra."),
    ("offer03","oferta_ou_beneficio_explicito","positive_claim","Com este guia, calcule o custo de cada produto em cinco passos."),
    ("offer04","oferta_ou_beneficio_explicito",UNKNOWN,"Amanhã teremos novidades."),
    ("offer05","oferta_ou_beneficio_explicito",UNKNOWN,"O desconto do ano passado terminou."),
    ("offer06","oferta_ou_beneficio_explicito",UNKNOWN,"Não anunciamos nenhuma oferta neste post."),
    ("tone01","tom","informal","E aí, pessoal! Tudo certo por aí? Bora conversar."),
    ("tone02","tom","técnico","Divida os custos fixos pela margem de contribuição unitária para obter o ponto de equilíbrio."),
    ("tone03","tom","inspiracional","Acredite no seu potencial. Cada desafio superado aproxima você do sonho."),
    ("tone04","tom","humorístico","Meu estoque é tão organizado que até os produtos pedem férias."),
    ("tone05","tom",UNKNOWN,"Publicado em 17 de novembro."),
    ("tone06","tom",UNKNOWN,"Uma piada abre a legenda; depois seguem fórmulas e instruções técnicas."),
)


def candidate(extractor, field, text, language):
    pt, en, labels = FIELDS[field]
    index = 1 if language == "pt" else 2
    head = pt if language == "pt" else en
    options = {label[index]: label[0] for label in labels}
    options["incerto ausente ou ambiguo" if language == "pt" else "unclear absent or ambiguous"] = UNKNOWN
    raw = extractor.classify_text(text, {head:list(options)})
    answer = raw.get(head) if isinstance(raw,dict) else None
    return options.get(answer, UNKNOWN) if isinstance(answer,str) else UNKNOWN


def score(rows):
    expected = {cid:(field,label) for cid,field,label,_ in CASES}
    if len(rows)!=len(expected) or {r["case_id"] for r in rows}!=set(expected):
        raise ValueError("BD_RUBRIC_BENCHMARK_PARTITION_MISMATCH")
    metrics = {}
    for field, (_,_,labels) in FIELDS.items():
        allowed = {label[0] for label in labels}|{UNKNOWN}
        subset = [r for r in rows if expected[r["case_id"]][0]==field]
        for r in subset:
            if (r["field"],r["expected"])!=expected[r["case_id"]] or any(r["predictions"][v] not in allowed for v in ("pt","en","consensus")):
                raise ValueError("BD_RUBRIC_BENCHMARK_LABEL_MISMATCH")
            p=r["predictions"]
            if p["consensus"]!=(p["pt"] if p["pt"]==p["en"] else UNKNOWN):
                raise ValueError("BD_RUBRIC_BENCHMARK_CONSENSUS_MISMATCH")
        variants={}
        for variant in ("pt","en","consensus"):
            matrix=Counter((r["expected"],r["predictions"][variant]) for r in subset)
            non_abstained=sum(n for (a,b),n in matrix.items() if b!=UNKNOWN)
            correct_candidates=sum(matrix[a,a] for a in allowed-{UNKNOWN})
            positive_expected=sum(n for (a,b),n in matrix.items() if a!=UNKNOWN)
            variants[variant]={"exact_matches":sum(matrix[a,a] for a in allowed),
                "candidates":non_abstained,"correct_candidates":correct_candidates,
                "candidate_precision":round(correct_candidates/non_abstained,6) if non_abstained else None,
                "candidate_recall":round(correct_candidates/positive_expected,6) if positive_expected else None,
                "candidates_on_unknown":sum(matrix[UNKNOWN,b] for b in allowed-{UNKNOWN}),
                "wrong_nonabstained":non_abstained-correct_candidates,
                "abstentions":sum(matrix[a,UNKNOWN] for a in allowed)}
        metrics[field]={"cases":len(subset),"expected_unknown":sum(r["expected"]==UNKNOWN for r in subset),
                        "variants":variants}
    return metrics


def run_rubric_challenge(extractor):
    rows=[]
    for cid,field,expected,text in CASES:
        started=perf_counter()
        pt=candidate(extractor,field,text,"pt")
        en=candidate(extractor,field,text,"en")
        rows.append({"case_id":cid,"field":field,"expected":expected,
                     "predictions":{"pt":pt,"en":en,"consensus":pt if pt==en else UNKNOWN},
                     "caption_sha256":sha256(text.encode("utf-8")).hexdigest(),
                     "duration_ms":round((perf_counter()-started)*1000,3)})
    return {"rubric_benchmark_version":VERSION,"synthetic_cases":len(rows),
            "fields":score(rows),"cases":rows,"independent_gold":False,
            "automatic_variant_selected":False,"real_caption_inference_allowed":False,
            "rubric_assessments_written":0,"scientific_admissions":0}
