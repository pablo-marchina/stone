"""Fixed synthetic audience challenge; engineering evaluation, never a real gold set."""
from collections import Counter
from hashlib import sha256
from time import perf_counter

VERSION = "bd-audience-challenge.v1"
POS, NEG, UNC = "MODEL_POSITIVE_CANDIDATE", "MODEL_NEGATIVE_CANDIDATE", "MODEL_ABSTAIN"
LABELS = (POS, NEG, UNC)
# Frozen before observing any v2 output. Size/recipient ambiguity is deliberate.
CASES = (
    ("direct-01", POS, "Se você é MEI, aprenda a organizar o fluxo de caixa."),
    ("direct-02", POS, "Atenção, microempreendedores: emitam suas notas fiscais neste aplicativo."),
    ("direct-03", POS, "Sua pequena empresa precisa de capital de giro? Conheça estas opções."),
    ("direct-04", POS, "Curso gratuito para MEIs: inscreva-se e organize suas vendas."),
    ("direct-05", POS, "Olá, pequenos empreendedores! Confira como precificar seus produtos."),
    ("direct-06", POS, "Para donos de microempresas, preparamos um guia de contratação."),
    ("implicit-01", POS, "Você trabalha por conta própria e vende seus bolos na feira? Calcule o preço de cada encomenda."),
    ("implicit-02", POS, "Sua lojinha funciona na garagem de casa? Separe o dinheiro pessoal do caixa."),
    ("implicit-03", POS, "Começou a fazer unhas sozinha em casa? Aprenda a cobrar por atendimento."),
    ("implicit-04", POS, "Você vende marmitas por conta própria? Controle o custo dos ingredientes."),
    ("exclusion-01", NEG, "Não é para MEIs: evento exclusivo para grandes corporações."),
    ("exclusion-02", NEG, "Inscrições exclusivas para empresas com mais de mil funcionários; microempresas não são elegíveis."),
    ("exclusion-03", NEG, "Esta solução se destina somente a multinacionais, não a pequenos negócios."),
    ("consumer-01", NEG, "Compre dois produtos e ganhe desconto no supermercado."),
    ("consumer-02", NEG, "Reserve seu quarto e aproveite as férias em família."),
    ("consumer-03", NEG, "Clientes, paguem suas compras com Pix e participem do sorteio."),
    ("consumer-04", NEG, "Escolha seu batom favorito e ganhe frete grátis na sua compra pessoal."),
    ("consumer-05", NEG, "Receita de bolo para preparar com as crianças no domingo."),
    ("mention-01", UNC, "O número de MEIs cresceu no último ano."),
    ("mention-02", UNC, "Pesquisa aponta aumento das exportações de pequenas empresas."),
    ("mention-03", UNC, "O prefeito visitou uma microempresa ontem."),
    ("mention-04", UNC, "O relatório analisa o programa para MEIs lançado em 2020."),
    ("ambiguous-01", UNC, "Nossa equipe celebra mais uma conquista."),
    ("ambiguous-02", UNC, "Melhore a gestão da sua empresa com dados e tecnologia."),
    ("ambiguous-03", UNC, "Aprenda a organizar suas finanças."),
    ("ambiguous-04", UNC, "Você vende pelo WhatsApp? Organize os pedidos da sua loja e calcule sua margem."),
    ("ambiguous-05", UNC, "Não é só para MEIs: a iniciativa atende negócios de todos os portes."),
    ("ambiguous-06", UNC, "A frase 'Se você é MEI, aprenda a vender' foi usada como exemplo em uma pesquisa."),
    ("ambiguous-07", UNC, "Confira as novidades do nosso evento de empreendedorismo."),
    ("ambiguous-08", UNC, "Hoje celebramos quem transforma ideias em realidade."),
)

# Same classify_text API as E1; these are hypotheses, not known improvements.
HEADS = {
    "descriptive_pt": ("qual e o publico a quem esta legenda se dirige", (
        "microempreendedores ou pequenos negocios como destinatarios",
        "consumidores finais ou grandes empresas como destinatarios exclusivos",
        "publico incerto ou mera mencao sem direcionamento")),
    "descriptive_en": ("intended recipient of this social media caption", (
        "directed to micro or small business owners and self employed merchants",
        "directed to consumers or exclusively large enterprises instead",
        "unclear recipient or merely mentions small businesses")),
}
VARIANTS = ("v1", *HEADS, "semantic_consensus")


def semantic_candidates(extractor, text):
    outputs = {}
    for key, (head, labels) in HEADS.items():
        raw = extractor.classify_text(text, {head: list(labels)})
        label = raw.get(head) if isinstance(raw, dict) else None
        outputs[key] = LABELS[labels.index(label)] if isinstance(label, str) and label in labels else UNC
    values = tuple(outputs.values())
    outputs["semantic_consensus"] = values[0] if values[0] == values[1] else UNC
    return outputs


def score(rows):
    """Exact fixture agreement, false positives and coverage; no generalization."""
    if len(rows) != len(CASES) or {r["case_id"] for r in rows} != {c[0] for c in CASES}:
        raise ValueError("BD_AUDIENCE_BENCHMARK_PARTITION_MISMATCH")
    expected = {cid: label for cid, label, _ in CASES}
    metrics = {}
    for variant in VARIANTS:
        matrix = Counter()
        for row in rows:
            actual = row["predictions"][variant]
            if actual not in LABELS or row["expected"] != expected[row["case_id"]]:
                raise ValueError("BD_AUDIENCE_BENCHMARK_LABEL_MISMATCH")
            matrix[row["expected"], actual] += 1
        metrics[variant] = {
            "matrix": {a: {b: matrix[a, b] for b in LABELS} for a in LABELS},
            "exact_matches": sum(matrix[a, a] for a in LABELS),
            "positive_correct": matrix[POS, POS],
            "positive_on_negative": matrix[NEG, POS],
            "positive_on_uncertain": matrix[UNC, POS],
            "negative_on_positive": matrix[POS, NEG],
            "abstentions": sum(matrix[a, UNC] for a in LABELS),
        }
    return metrics


def run_challenge(extractor, v1_predict):
    rows = []
    for case_id, expected, text in CASES:
        started = perf_counter()
        predictions = {"v1": v1_predict(case_id, text), **semantic_candidates(extractor, text)}
        rows.append({"case_id": case_id, "expected": expected, "predictions": predictions,
                     "caption_sha256": sha256(text.encode("utf-8")).hexdigest(),
                     "duration_ms": round((perf_counter() - started) * 1000, 3)})
    return {"benchmark_version": VERSION, "synthetic_cases": len(rows),
            "expected_counts": dict(Counter(c[1] for c in CASES)),
            "metrics": score(rows), "cases": rows,
            "scientifically_validated": False, "independent_gold": False,
            "automatic_variant_selected": False, "scientific_admissions": 0}
