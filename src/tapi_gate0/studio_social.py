"""Candidate social art direction, not an empirically validated aesthetic."""
from .studio_e1 import Canvas, DesignDocument, DesignPage, TextLayer, TextStyle

DARK = '#102D22'
CREAM = '#F6F4EB'
LIME = '#C9F36B'


def social_document(spec, document_id, template):
    multi = template == 'social-carousel'
    if multi != (spec.platform_intent == 'instagram_carousel'):
        raise ValueError('STUDIO_SOCIAL_FORMAT_INVALID')

    def layer(id, x, y, w, h, text, size, color, *, bold=False, fill=None, pad=None):
        return TextLayer(id=id, x=x, y=y, w=w, h=h, text=text,
                         style=TextStyle(font_size=size, color=color, weight=700 if bold else 400,
                                         box_fill=fill, box_radius=28 if fill else None, padding=pad))

    def page(index, headline, body, cta):
        # Distinct role-specific compositions, constant between A/B variants.
        light = index == 2
        title_color = DARK if light else CREAM
        title_fill = CREAM if light else None
        return DesignPage(id=f'page.{index}', layers=[
            layer('series', 80, 70, 920, 62, 'GESTÃO NA PRÁTICA  /  GUIA', 32, LIME, bold=True),
            layer('section', 80, 158, 920, 85, f'0{index}  /  '+('ENTENDA' if index == 1 else 'APLIQUE' if light else 'REVISE'), 36, DARK, bold=True, fill=LIME, pad=18),
            layer('headline', 80, 280, 920, 350, headline, 104, title_color, bold=True, fill=title_fill, pad=24 if light else None),
            layer('step', 80, 660, 920, 48, 'UMA AÇÃO DE CADA VEZ', 32, LIME, bold=True),
            layer('body', 80, 730, 920, 285, body, 48, DARK, fill=CREAM, pad=28),
            layer('cta', 80, 1080, 920, 170, cta, 44, DARK, bold=True, fill=LIME, pad=24),
        ])

    pages = [page(1, spec.headline, spec.body if not multi else 'Uma mensagem clara começa com uma ação concreta.',
                  spec.cta if not multi else 'Deslize para aplicar →')]
    if multi:
        pages += [page(2, 'Coloque em\nprática', spec.body, 'Deslize para concluir →'),
                  page(3, 'Faça\nacontecer', 'Reserve um momento para revisar o que fez e ajustar a próxima ação.', spec.cta)]
    return DesignDocument(document_id=document_id, tenant_id=spec.tenant_id, spec_id=spec.spec_id,
                          version=1, canvas=Canvas(background=DARK), platform_intent=spec.platform_intent,
                          pages=pages, reference_content_ids=spec.reference_content_ids)
