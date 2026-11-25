"""Conservative caption-only candidate evidence; no scientific admission."""
from collections import Counter
from hashlib import sha256
import re
from time import perf_counter

from .discovery_audience_benchmark import CASES, LABELS, NEG, POS, UNC, semantic_candidates

VERSION = "bd-audience-grounded.v1"
AUDIENCE = r"(?:meis?|microempreendedor(?:es|a|as)?(?:\s+individua(?:l|is))?|microempresas?|pequen[oa]s?\s+(?:empreendedor(?:es|a|as)?|neg[óo]cios?|empresas?))"
OWNER = r"(?:(?:don[oa]s?|propriet[áa]ri[oa]s?|gestores)\s+de\s+)?"
DIRECT = re.compile(r"\b(?:se\s+voc[êe]\s+[ée]\s+(?:um[a]?\s+)?|(?:aten[çc][ãa]o|ol[áa]|ei)\s*[,!:]?\s*|(?:para|destinad[oa]s?\s+a|voltad[oa]s?\s+a)\s+(?:os\s+|as\s+)?" + OWNER + r"|seu\s+|sua\s+)" + AUDIENCE + r"\b|(?:^|[.!?\n]\s*)" + AUDIENCE + r"\s*[,!:]", re.I)
IMPLICIT = re.compile(r"\b(?:voc[êe]\s+[^.!?\n]{0,80}(?:por conta pr[óo]pria|como aut[ôo]nom[oa])|(?:seu|sua)\s+(?:lojinha|neg[óo]cio)\s+[^.!?\n]{0,45}(?:em casa|na garagem)|(?:voc[êe]\s+)?(?:come[çc]ou|trabalha|atende|vende|produz)\s+[^.!?\n]{0,60}(?:sozin[ha]?[oa]|sozinh[oa])\s+em casa)\b", re.I)
ACTION = re.compile(r"\b(?:aprend[ae]m?|organize[m]?|calcul[e]|controle[m]?|separe[m]?|conhe[çc]a[m]?|confira[m]?|inscreva[m]?-se|emit[ae]m?|precifiqu[e]|descubra[m]?|veja[m]?|participe[m]?|saiba[m]?|baixe[m]?|acesse[m]?|fa[çc]a[m]?|proteja[m]?|planeje[m]?|registre[m]?|guia|curso|oficina|consultoria|dicas|capital de giro)\b", re.I)
REPORTING = re.compile(r"\b(?:relat[óo]rio|pesquisa|estudo|levantamento|estat[íi]stica|not[íi]cia|frase|exemplo|cita[çc][ãa]o|citou|visitou|anunciou|informou|divulgou|disse|afirmou|n[úu]mero de)\b", re.I)
BROAD = re.compile(r"\b(?:todos os portes|qualquer porte|todo tipo de empresa|n[ãa]o (?:[ée]\s+)?(?:s[óo]|apenas|somente)\s+para|p[úu]blico em geral)\b", re.I)
EXCLUSION = re.compile(r"\bn[ãa]o\s+(?:[ée]\s+)?(?:para|a)\s+" + OWNER + AUDIENCE + r"\b|\b" + AUDIENCE + r"\s+n[ãa]o\s+(?:s[ãa]o|[ée]|podem|pode)\s+(?:eleg[íi]ve[li]s?|participar|atendid[oa]s?)\b|\b(?:exclusiv[oa]s?\s+para|somente\s+a)\s+(?:grandes corpora[çc][õo]es|multinacionais|grandes empresas)\b", re.I)
CONSUMER = re.compile(r"\b(?:f[ée]rias em fam[íi]lia|compra pessoal|com as crian[çc]as|clientes\s*,\s*paguem suas compras)\b", re.I)
QUOTED = re.compile(r"[\"“”«»]|(?<!\w)'[^'\n]+?'(?!\w)")
# A second set, distinct from the development challenge. Authored fixtures, not independent gold.
CHECK_CASES = (
    ("check-p01", POS, "MEI, descubra como emitir a nota fiscal da sua venda."),
    ("check-p02", POS, "Para proprietários de pequenas empresas: acesse o guia de gestão de estoque."),
    ("check-p03", POS, "Se você é microempreendedora, conheça as opções de crédito."),
    ("check-p04", POS, "Sua microempresa cresceu? Planeje os próximos investimentos."),
    ("check-p05", POS, "Você atende como autônoma? Organize a agenda dos seus clientes."),
    ("check-p06", POS, "Você costura por conta própria? Calcule a margem de cada peça."),
    ("check-n01", NEG, "Evento exclusivo para grandes empresas."),
    ("check-n02", NEG, "O treinamento não é para pequenos empreendedores."),
    ("check-n03", NEG, "Microempresas não podem participar desta licitação."),
    ("check-n04", NEG, "Aproveite suas férias em família e reserve uma suíte."),
    ("check-n05", NEG, "Compre agora seu tênis para uso pessoal."),
    ("check-n06", NEG, "Oferta de brinquedos para o presente dos seus filhos."),
    ("check-u01", UNC, "O estudo destacou o crescimento do crédito para pequenas empresas."),
    ("check-u02", UNC, "O evento é para todos os portes, inclusive MEIs."),
    ("check-u03", UNC, 'A manchete "MEI, descubra como vender" viralizou.'),
    ("check-u04", UNC, "Aumente a produtividade de sua equipe com este software."),
    ("check-u05", UNC, "Tem uma loja? Conheça nossas ferramentas de marketing."),
    ("check-u06", UNC, "O município anunciou uma oficina para microempreendedores."),
)


def _span(match, rule):
    return {"start": match.start(), "end": match.end(), "rule": rule,
            "sha256": sha256(match.group().encode("utf-8")).hexdigest()}


def grounded_rule(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 10000:
        raise ValueError("BD_CAPTION_INVALID")
    result = {"policy_version": VERSION, "caption_sha256": sha256(text.encode("utf-8")).hexdigest(),
              "rule_status": UNC, "evidence_spans": [], "reason": "NO_SUFFICIENT_AUDIENCE_ANCHOR"}
    for pattern, reason in ((QUOTED, "QUOTED_CONTEXT"), (REPORTING, "REPORTING_CONTEXT"), (BROAD, "BROAD_AUDIENCE")):
        if pattern.search(text):
            return {**result, "reason": reason}
    excluded = EXCLUSION.search(text)
    if excluded:
        return {**result, "rule_status": NEG, "reason": "EXPLICIT_EXCLUSION",
                "evidence_spans": [_span(excluded, "exclusion")]}
    anchors = [(m, label) for pattern, label in ((DIRECT, "explicit_address"), (IMPLICIT, "microactivity_address"))
               for m in pattern.finditer(text)]
    actions = list(ACTION.finditer(text))
    for anchor, label in anchors:
        # Reject a nearby negative statement even if its phrasing is not covered by EXCLUSION.
        if re.search(r"\bn[ãa]o\b", text[max(0, anchor.start()-35):min(len(text), anchor.end()+35)], re.I):
            continue
        nearby = [a for a in actions if max(anchor.start()-a.end(), a.start()-anchor.end(), 0) <= 120]
        if nearby:
            action = min(nearby, key=lambda a: abs(a.start()-anchor.start()))
            return {**result, "rule_status": POS, "reason": "ADDRESSEE_AND_ACTION_OBSERVED",
                    "evidence_spans": [_span(anchor, label), _span(action, "action")]}
    consumer = CONSUMER.search(text)
    if consumer and not anchors:
        return {**result, "rule_status": NEG, "reason": "CONSUMER_CONTEXT",
                "evidence_spans": [_span(consumer, "consumer")]}
    return result


def grounded_candidate(text, consensus):
    if consensus not in LABELS:
        raise ValueError("BD_AUDIENCE_GROUNDED_UNKNOWN_LABEL")
    rule = grounded_rule(text)
    agreed = consensus == rule["rule_status"] and consensus != UNC
    return {**rule, "status": consensus if agreed else UNC, "semantic_consensus": consensus,
            "human_review": False, "scientific_admission": False,
            "targeting_decision": "not_assessed"}


def _metrics(rows, variants):
    metrics = {}
    for variant in variants:
        matrix = Counter((r["expected"], r["predictions"][variant]) for r in rows)
        if any(a not in LABELS or b not in LABELS for a, b in matrix):
            raise ValueError("BD_AUDIENCE_GROUNDED_UNKNOWN_LABEL")
        metrics[variant] = {"matrix": {a: {b: matrix[a, b] for b in LABELS} for a in LABELS},
                            "exact_matches": sum(matrix[a, a] for a in LABELS),
                            "positive_correct": matrix[POS, POS], "positive_on_negative": matrix[NEG, POS],
                            "positive_on_uncertain": matrix[UNC, POS], "negative_on_positive": matrix[POS, NEG],
                            "abstentions": sum(matrix[a, UNC] for a in LABELS)}
    return metrics


def run_grounded_challenge(extractor, v1_predict):
    rows = []
    summaries = {}
    variants = ("v1", "descriptive_pt", "descriptive_en", "semantic_consensus", "grounded_rule", "grounded_hybrid")
    for split, cases in (("development", CASES), ("additional_synthetic", CHECK_CASES)):
        subset = []
        for cid, expected, text in cases:
            start = perf_counter()
            predictions = {"v1": v1_predict(cid, text), **semantic_candidates(extractor, text)}
            result = grounded_candidate(text, predictions["semantic_consensus"])
            predictions.update(grounded_rule=result["rule_status"], grounded_hybrid=result["status"])
            subset.append({"case_id": cid, "split": split, "expected": expected,
                           "predictions": predictions, "grounding": result,
                           "duration_ms": round((perf_counter()-start)*1000, 3)})
        summaries[split] = {"cases": len(subset), "metrics": _metrics(subset, variants)}
        rows.extend(subset)
    checks = [summaries[s]["metrics"]["grounded_hybrid"] for s in summaries]
    passed = all(m["positive_on_negative"] == m["positive_on_uncertain"] == 0 for m in checks) and checks[0]["positive_correct"] >= 5 and checks[1]["positive_correct"] >= 3
    return {"benchmark_version": VERSION, "synthetic_cases": len(rows), "splits": summaries,
            "engineering_gate_passed": passed, "engineering_gate_criteria": "zero_positive_on_negative_or_uncertain_each_split; >=5/10_development; >=3/6_additional",
            "scientifically_validated": False, "independent_gold": False, "scientific_admissions": 0,
            "cases": rows}
