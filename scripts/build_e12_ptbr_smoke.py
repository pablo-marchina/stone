"""Build DEC-017 E1.2 Portuguese-BR synthetic smoke (NOT scientific gold)."""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path

from tapi_gate0.system_one_e1 import EvidenceBundle, ObservedText, E1_FIELDS
from tapi_gate0.system_one_e12 import E12Case, ReferenceLabel


# Artificial sentences are educational fixtures, not scraped social content.
# Categories here test the benchmark contract, not model accuracy.
EXAMPLES = [
    ("Como aumentar as vendas do seu pequeno comércio? Comente a sua maior dificuldade.",
     "vendas", "comentar", True, None, "informal"),
    ("O fluxo de caixa da padaria ficou negativo. Salve este passo a passo financeiro.",
     "finanças", "salvar", True, None, "técnico"),
    ("Marketing local para microempresas: aprenda a divulgar sua loja. Siga nosso perfil.",
     "marketing", "seguir", True, None, None),
    ("Atendimento humanizado no salão de bairro: responda os clientes com empatia.",
     "atendimento", None, True, None, None),
    ("Gestão de estoque para lojistas que trabalham sozinhos no pequeno negócio.",
     "gestão", None, True, None, "técnico"),
    ("Relatório anual reservado a investidores institucionais de uma holding global.",
     None, None, False, None, "técnico"),
    ("O céu está azul nesta tarde.", None, None, None, None, None),
    ("Marketing e vendas: qual a prioridade do negócio? Comente sua opinião.",
     None, "comentar", None, None, None),
    ("Planilha gratuita para microempreendedores: controle a maquininha. Link na bio.",
     "ferramentas/maquininha", "link na bio", True, True, None),
    ("Empreendedora conta como começou seu pequeno comércio no interior.",
     "história de empreendedor", None, True, None, None),
    ("Organize seu fluxo de caixa e suas vendas na mercearia. Envie uma DM.",
     None, "DM", True, None, None),
    ("NÃO siga este perfil: é um alerta de segurança, não uma chamada para ação.",
     None, None, None, None, None),
    ("Você consegue continuar empreendendo! Acredite no pequeno negócio.",
     "motivação", None, True, None, "inspiracional"),
    ("Planejamento de custos do comércio local: defina o orçamento mensal.",
     "finanças", None, True, None, "técnico"),
]


def make_cases() -> list[E12Case]:
    cases = []
    for index, (caption, topic, cta, target, offer, tone) in enumerate(EXAMPLES, 1):
        name = "ptbr_" + str(index).zfill(3)
        locator = "fixture:" + name + "#caption"
        observation = ObservedText(
            modality="caption", text=caption, locator=locator,
            sha256=sha256(caption.encode("utf-8")).hexdigest(),
        )
        bundle = EvidenceBundle(
            tenant_id="synthetic_ptbr", content_id=name,
            creator_id="criador_ficticio_" + str(index).zfill(3),
            source_kind="synthetic", observation=observation,
        )
        gold = {
            "tema_principal": topic,
            "tom": tone,
            "tipo_hook": None,  # text is never evidence of a video first-3-second hook
            "tem_cta": True if cta is not None else None,
            "tipo_cta": cta,
            "oferta_ou_beneficio_explicito": offer,
            "mpe_targeted": target,
        }
        labels = []
        for field in E1_FIELDS:
            value = gold[field]
            labels.append(ReferenceLabel(
                field_id=field,
                status="observed" if value is not None else "not_observable",
                value=value,
                evidence_locator=locator if value is not None else None,
                rationale=("synthetic author-provided textual target"
                           if value is not None else
                           "not decidable from this caption alone"),
            ))
        cases.append(E12Case(
            evidence=bundle, split="smoke", gold_kind="synthetic_fixture",
            synthetic_labels=labels,
        ))
    return cases


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic PT-BR E1.2 smoke cases")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    target = Path(args.output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    cases = make_cases()
    target.write_text(
        "".join(case.model_dump_json()+"\n" for case in cases), encoding="utf-8",
    )
    print("Wrote", len(cases), "synthetic Portuguese cases (NOT human or scientific gold).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
