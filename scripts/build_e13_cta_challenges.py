"""DEC-017 E1.3: generate reproducible, solely artificial PT-BR CTA challenges."""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path

from tapi_gate0.system_one_e1 import E1_FIELDS, EvidenceBundle, ObservedText
from tapi_gate0.system_one_e12 import E12Case, ReferenceLabel
from build_e12_ptbr_smoke import make_cases as e12_smoke

# (text, positive CTA kind). None means insufficient evidence for video CTA;
# it NEVER means that a full video has no CTA.
CHALLENGES = (
    ("NÃO siga este perfil: é um alerta de segurança.", None),
    ("Não salve esta publicação.", None),
    ("Comente aqui qual é a maior dificuldade do seu comércio.", "comentar"),
    ("Não siga o perfil anterior, mas comente aqui sua dúvida.", "comentar"),
    ("Não comente nem siga o perfil suspeito.", None),
    ("Siga este perfil e salve estas dicas para depois.", "__multiple__"),
    ("Envie uma DM para receber o catálogo da loja.", "DM"),
    ("Use o link na bio para baixar o guia gratuito.", "link na bio"),
    ("Por favor, salve este post sobre gestão de estoque.", "salvar"),
    ("Não deixe de seguir nossa página.", "seguir"),
    ("A palavra 'siga' aparece no exemplo de gramática.", None),
    ("Se quiser, poderá seguir esses passos; não é uma instrução para seguir o perfil.", None),
    ("Comente agora: qual sua dúvida sobre a maquininha?", "comentar"),
    ("Não salve esta mensagem; siga o nosso perfil oficial.", "seguir"),
    # Additional edge cases retained from PR #27; no negative labels imply video-wide absence.
    ("Não clique no link na bio: é um aviso de segurança.", None),
    ("Você pode seguir a lista de tarefas da empresa.", None),
    ("A palavra comente é um verbo no imperativo.", None),
    ("Não esqueça de salvar este checklist financeiro.", "salvar"),
    ("Não comente sua senha; salve estas dicas de segurança.", "salvar"),
    ("O guia para sua lojinha está no link na bio.", "link na bio"),
)


def make_cases() -> list[E12Case]:
    cases = e12_smoke()
    for idx, (text, cta_type) in enumerate(CHALLENGES, 1):
        name = f"e13_{idx:03d}"
        locator = f"synthetic:{name}#caption"
        observation = ObservedText(
            modality="caption", text=text, locator=locator,
            sha256=sha256(text.encode("utf-8")).hexdigest(),
        )
        evidence = EvidenceBundle(
            tenant_id="synthetic_e13", content_id=name,
            creator_id=f"fictitious_creator_e13_{idx:03d}",
            source_kind="synthetic", observation=observation,
        )
        positive = cta_type is not None
        gold = {
            "tem_cta": True if positive else None,
            "tipo_cta": cta_type if cta_type not in (None, "__multiple__") else None,
        }
        labels = [
            ReferenceLabel(
                field_id=field,
                status="observed" if gold.get(field) is not None else "not_observable",
                value=gold.get(field),
                evidence_locator=locator if gold.get(field) is not None else None,
                rationale=("explicit artificial positive CTA in observed caption"
                           if gold.get(field) is not None else
                           "not determined by this caption or ambiguous CTA type"),
            )
            for field in E1_FIELDS
        ]
        cases.append(E12Case(
            evidence=evidence, split="smoke", gold_kind="synthetic_fixture",
            synthetic_labels=labels,
        ))
    return cases


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate E1.3 synthetic CTA diagnostic JSONL")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    target = Path(args.output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    cases = make_cases()
    target.write_text(
        "".join(case.model_dump_json()+"\n" for case in cases),
        encoding="utf-8",
    )
    print(f"E1.3 generated {len(cases)} synthetic PT-BR examples; NOT human gold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
