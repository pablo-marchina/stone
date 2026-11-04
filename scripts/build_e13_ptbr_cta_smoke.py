"""DEC-017 E1.3: additional fabricated PT-BR CTA/negation cases.

No network, no real posts, no model calls. Labels are authors' synthetic
fixtures rather than human-reviewed ground truth.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path

from build_e12_ptbr_smoke import make_cases as e12_smoke
from tapi_gate0.system_one_e1 import E1_FIELDS, EvidenceBundle, ObservedText
from tapi_gate0.system_one_e12 import E12Case, ReferenceLabel

# text, observed positive CTA type (or None), observed CTA presence
CTA_CASES = (
    ("Não siga este perfil: é um alerta sobre golpes.", None, False),
    ("Siga nosso perfil para receber dicas de vendas.", "seguir", True),
    ("Não deixe de seguir nossa página de dicas de comércio.", "seguir", True),
    ("Nunca comente sua senha em páginas públicas.", None, False),
    ("Comente qual é a maior dificuldade no seu pequeno negócio.", "comentar", True),
    ("Não comente sua senha; salve estas dicas de segurança.", "salvar", True),
    ("O guia para sua lojinha está no link na bio.", "link na bio", True),
    ("Não clique no link na bio: é um aviso de segurança.", None, False),
    ("Envie uma DM para falar com a equipe da loja.", "DM", True),
    ("Comente e salve esta dica de atendimento ao cliente.", None, True),
    ("Você pode seguir a lista de tarefas da empresa.", None, False),
    ("A palavra comente é um verbo no imperativo.", None, False),
    ("Não esqueça de salvar este checklist financeiro.", "salvar", True),
    ("Para falar sobre vendas, mande uma DM.", "DM", True),
)


def make_cases() -> list[E12Case]:
    cases = e12_smoke()
    for index, (caption, cta_kind, is_positive) in enumerate(CTA_CASES, 1):
        content_id = "e13_" + str(index).zfill(3)
        locator = "fixture:" + content_id + "#caption"
        observation = ObservedText(
            modality="caption", text=caption, locator=locator,
            sha256=sha256(caption.encode("utf-8")).hexdigest(),
        )
        evidence = EvidenceBundle(
            tenant_id="synthetic_ptbr",
            content_id=content_id,
            creator_id="fictitious_e13_" + str(index).zfill(3),
            source_kind="synthetic", observation=observation,
        )
        labels = []
        for field in E1_FIELDS:
            if field == "tem_cta" and is_positive:
                value = True
            elif field == "tipo_cta" and cta_kind is not None:
                value = cta_kind
            else:
                value = None
            labels.append(ReferenceLabel(
                field_id=field,
                status="observed" if value is not None else "not_observable",
                value=value,
                evidence_locator=locator if value is not None else None,
                rationale=("synthetic positive textual action" if value is not None
                           else "no unambiguous positive text-only evidence"),
            ))
        cases.append(E12Case(evidence=evidence, split="smoke",
                             gold_kind="synthetic_fixture", synthetic_labels=labels))
    return cases


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="E1.3 synthetic CTA diagnostic input")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    target = Path(args.output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    cases = make_cases()
    target.write_text("".join(c.model_dump_json()+"\n" for c in cases),
                      encoding="utf-8")
    print("Created", len(cases), "fictional PT-BR E1.3 smoke items; not human gold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
