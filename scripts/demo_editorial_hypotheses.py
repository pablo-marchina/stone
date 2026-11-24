"""Descriptive, aggregate-bound experiment suggestions; not a creative approval."""

PLAN = {
    'format': 'Compare este formato com outro mantendo tema, CTA e janela de medição constantes.',
    'topic': 'Compare este tema com outro mantendo formato, CTA e janela de medição constantes.',
    'cta': 'Compare este CTA com outro mantendo tema, formato e janela de medição constantes.',
}


def hypotheses(contrast, report_sha256):
    """Select largest positive observed contrast per actionable dimension.

    Bounds assign every unknown either to the candidate or another value.
    They are identification bounds, not confidence intervals. No automatic
    pairing of marginal signals, recommendation to publish, or causal claim.
    """
    out = []
    for field, plan in PLAN.items():
        f = contrast['fields'][field]
        a, b = f['top'], f['rest']
        positive = [r for r in f['comparisons'] if r['difference_percentage_points'] is not None
                    and r['difference_percentage_points'] > 0]
        if not positive or not a['posts'] or not b['posts']:
            continue
        r = sorted(positive, key=lambda r: (-r['difference_percentage_points'], r['value']))[0]
        x, y = r['top_count'], r['rest_count']
        low = 100 * (x/a['posts'] - (y+b['unknown'])/b['posts'])
        high = 100 * ((x+a['unknown'])/a['posts'] - y/b['posts'])
        out.append(dict(field=field, value=r['value'], top_count=x, rest_count=y,
                        top_observed=a['observed'], rest_observed=b['observed'],
                        top_posts=a['posts'], rest_posts=b['posts'], top_profiles=r['top_profiles'],
                        difference_pp=r['difference_percentage_points'],
                        missingness_bounds_pp=[round(low, 6), round(high, 6)],
                        positive_under_all_missing_assignments=low > 0,
                        experiment=plan))
    return dict(schema_version='tapi-demo-editorial-hypotheses.v1', report_sha256=report_sha256,
                hypotheses=out, joint_effect_estimated=False, causal_claims=False,
                scientifically_validated=False, publication_allowed=False)
