"""CAP-003 / IMP-064/065: grounded caption candidates, not validated labels."""
from hashlib import sha256
from collections import Counter
import re

from .discovery_rubric_benchmark import CASES, FIELDS, UNKNOWN, candidate

VERSION = "bd-caption-rubric-grounded.v1"
# Additional authored fixtures, not independent gold.
CHECK_CASES = (
    ("g01","tema_principal","vendas","Negocie para fechar mais vendas."),
    ("g02","tema_principal","finanças","Controle o fluxo de caixa e os custos fixos."),
    ("g03","tema_principal","marketing","Planeje a divulgação da marca e os anúncios."),
    ("g04","tema_principal",UNKNOWN,"Falaremos de vendas, marketing e finanças."),
    ("g05","tema_principal",UNKNOWN,"Confira as novidades da semana."),
    ("g06","tipo_cta","comentar","Comente sua dúvida abaixo."),
    ("g07","tipo_cta","DM","Mande uma mensagem pelo direct."),
    ("g08","tipo_cta","link na bio","Clique no link da bio para ler o material."),
    ("g09","tipo_cta",UNKNOWN,'O artigo cita "Siga nosso perfil" como exemplo.'),
    ("g10","tipo_cta",UNKNOWN,"Não salve este post."),
    ("g11","tipo_cta",UNKNOWN,"Comente e salve este post."),
    ("g12","tipo_cta",UNKNOWN,"O link na bio foi atualizado ontem."),
    ("g13","prova_social","positive_claim","Uma cliente afirmou: a oficina resolveu meu problema."),
    ("g14","prova_social","positive_claim","Mais de 200 clientes satisfeitos recomendaram o curso."),
    ("g15","prova_social",UNKNOWN,"Queremos ter 200 clientes satisfeitos."),
    ("g16","prova_social",UNKNOWN,"Saiba como pedir depoimentos aos clientes."),
    ("g17","prova_social",UNKNOWN,"Ainda não recebemos recomendações de clientes."),
    ("g18","oferta_ou_beneficio_explicito","positive_claim","Ganhe 15% de desconto na inscrição."),
    ("g19","oferta_ou_beneficio_explicito","positive_claim","Inscreva-se na oficina gratuita de vendas."),
    ("g20","oferta_ou_beneficio_explicito",UNKNOWN,"O desconto de 15% terminou ontem."),
    ("g21","oferta_ou_beneficio_explicito",UNKNOWN,"Em breve anunciaremos benefícios."),
    ("g22","oferta_ou_beneficio_explicito",UNKNOWN,"Não há desconto na inscrição."),
    ("g23","tom","informal","Oi, gente! Bora bater um papo?"),
    ("g24","tom","técnico","Calcule a margem dividindo o lucro pela receita."),
    ("g25","tom",UNKNOWN,"O material foi publicado nesta terça."),
    ("g26","tom",UNKNOWN,"A legenda mistura piadas e instruções técnicas."),
)
PATTERNS = {
    "tema_principal": {
        "vendas":r"\b(?:vendas?|negocia(?:ção|cao))\b",
        "finanças":r"\b(?:finan[çc]as|fluxo de caixa|custos fixos|caixa pessoal|capital de giro)\b",
        "marketing":r"\b(?:marketing|divulga[çc][ãa]o|an[úu]ncios?|publicidade)\b",
        "atendimento":r"\b(?:atendimento|reclama[çc][õo]es|suporte ao cliente|escuta ativa)\b",
        "gestão":r"\b(?:estoque|gest[ãa]o operacional|tarefas da equipe|processo semanal)\b",
        "motivação":r"\b(?:n[ãa]o desista|acredite no seu potencial|pequeno passo conta)\b",
        "ferramentas/maquininha":r"\b(?:maquininha|terminal de pagamento|aceitar cart[õo]es)\b",
        "história de empreendedor":r"\b(?:comecei vendendo|abri minha primeira loja)\b",
    },
    "tipo_cta": {
        "comentar":r"\b(?:comente|comentem|conte [^.!?\n]{0,80} nos coment[áa]rios)\b",
        "salvar":r"\b(?:salve|salvem)\b",
        "link na bio":r"\b(?:acesse|clique|confira|veja)\s+(?:o|no|pelo)?\s*link\s+(?:na|da)\s+bio\b",
        "DM":r"\b(?:envie|mande)\s+(?:uma\s+)?mensagem\s+(?:pelo|no|via)\s+(?:direct|dm)\b",
        "seguir":r"\b(?:siga|sigam)\b",
    },
    "prova_social":{"positive_claim":r"\b(?:um[ao]?\s+cliente\s+(?:afirmou|relatou|recomendou)\s*:\s*[^.!?\n]{8,160}|(?:mais de\s+)?\d[\d.]*\s+clientes satisfeitos\s+(?:recomendaram|aprovaram))\b"},
    "oferta_ou_beneficio_explicito":{"positive_claim":r"\b(?:ganhe\s+\d{1,3}\s*%\s+de desconto|inscreva-se\s+n[oa]\s+(?:curso|oficina)\s+gratuit[oa]|com este guia,\s*calcule\s+[^.!?\n]{8,150})\b"},
    "tom":{}, # Dominant tone requires more than an isolated lexical anchor.
}
QUOTED = r'["“”«»]|(?<!\w)\x27[^\x27\n]+\x27(?!\w)'
REPORTED = r"\b(?:relat[óo]rio|artigo|pesquisa|exemplo|frase|men[çc][ãa]o|menciona|cita|citou|hipot[ée]tic[oa])\b"
NEGATED = r"\b(?:n[ãa]o|nunca|sem|jamais)\b"
PAST_FUTURE = r"\b(?:terminou|expirou|encerrad[oa]|em breve|no futuro|ano passado|queremos|pretendemos|aprenda a coletar|saiba como pedir)\b"

def _hash(text):
    return sha256(text.encode("utf-8")).hexdigest()

def rule_evidence(field, text):
    if field not in FIELDS or not isinstance(text,str) or not text.strip() or len(text)>10000:
        raise ValueError("BD_RUBRIC_GROUNDED_INPUT_INVALID")
    result={"rule_value":UNKNOWN,"reason":"NO_UNAMBIGUOUS_ANCHOR",
            "caption_sha256":_hash(text),"evidence_spans":[]}
    if not PATTERNS[field]:
        return {**result,"reason":"DOMINANCE_NOT_ESTABLISHED"}
    guards=[QUOTED,REPORTED]
    if field!="tema_principal":
        guards.extend((NEGATED,PAST_FUTURE))
    if any(re.search(pattern,text,re.I) for pattern in guards):
        return {**result,"reason":"CONTEXT_GUARD"}
    found={label:list(re.finditer(pattern,text,re.I)) for label,pattern in PATTERNS[field].items()}
    labels=[label for label,matches in found.items() if matches]
    if len(labels)!=1:
        return {**result,"reason":"MULTIPLE_ANCHORS" if labels else result["reason"]}
    label=labels[0]
    return {**result,"rule_value":label,"reason":"UNIQUE_LEXICAL_ANCHOR",
            "evidence_spans":[{"start":m.start(),"end":m.end(),"sha256":_hash(m.group())}
                              for m in found[label]]}

def grounded_field(extractor,field,text):
    rule=rule_evidence(field,text)
    pt=candidate(extractor,field,text,"pt")
    en=candidate(extractor,field,text,"en")
    consensus=pt if pt==en else UNKNOWN
    hybrid=consensus if consensus==rule["rule_value"] else UNKNOWN
    return {**rule,"field":field,"policy_version":VERSION,
            "predictions":{"pt":pt,"en":en,"consensus":consensus,"rule":rule["rule_value"],"hybrid":hybrid},
            "candidate_value":hybrid,"candidate_kind":"caption_only_not_validated",
            "human_review":False,"scientific_admission":False}

def _metrics(rows,variant):
    matrix=Counter((r["expected"],r["predictions"][variant]) for r in rows)
    return {"cases":len(rows),
            "expected_candidates":sum(n for (a,b),n in matrix.items() if a!=UNKNOWN),
            "correct_candidates":sum(n for (a,b),n in matrix.items() if a==b!=UNKNOWN),
            "wrong_nonabstained":sum(n for (a,b),n in matrix.items() if a!=b and b!=UNKNOWN),
            "candidates_on_unknown":sum(n for (a,b),n in matrix.items() if a==UNKNOWN and b!=UNKNOWN),
            "abstentions":sum(n for (a,b),n in matrix.items() if b==UNKNOWN),
            "exact_matches":sum(n for (a,b),n in matrix.items() if a==b)}

def run_grounded_rubric_challenge(extractor):
    rows,splits=[],{}
    for split,cases in (("development",CASES),("additional_authored",CHECK_CASES)):
        group=[{**grounded_field(extractor,field,text),"case_id":cid,"expected":expected,"split":split}
               for cid,field,expected,text in cases]
        splits[split]={field:{v:_metrics([r for r in group if r["field"]==field],v)
                             for v in ("pt","en","consensus","rule","hybrid")} for field in FIELDS}
        rows.extend(group)
    # Engineering proposal, frozen before local model run, not a scientific gate.
    gates={field:all(m["expected_candidates"]>=2 and m["wrong_nonabstained"]==0 and
                     2*m["correct_candidates"]>=m["expected_candidates"]
                     for m in (s[field]["hybrid"] for s in splits.values())) for field in FIELDS}
    return {"rubric_benchmark_version":VERSION,"synthetic_cases":len(rows),"splits":splits,
            "field_engineering_gate":gates,
            "gate_criteria":"each split: >=2 expected candidates; zero wrong candidates; >=50% correct",
            "independent_gold":False,"scientifically_validated":False,"automatic_variant_selected":False,
            "real_caption_inference_allowed":False,"rubric_assessments_written":0,"scientific_admissions":0,"cases":rows}
