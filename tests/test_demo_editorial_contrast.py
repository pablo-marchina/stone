from scripts.demo_editorial_contrast import contrast


def test_contrast_denominators_and_privacy():
    rows = [dict(content_id=f'private.{i}', username='secret.handle', likes=20-i,
                 comments=0, followers=100, format='reels' if i < 2 else 'imagem',
                 topic='vendas' if i == 0 else None, cta='private.free.text', age_band='14-29')
            for i in range(20)]
    r = contrast(rows)
    assert (r['top_posts'], r['rest_posts']) == (2, 18)
    f = r['fields']['format']
    reels = next(x for x in f['comparisons'] if x['value']=='reels')
    assert reels['top_observed_share'] == 1 and reels['rest_observed_share'] == 0
    assert reels['difference_percentage_points'] == 100
    topic = r['fields']['topic']
    assert topic['top']['unknown'] == 1 and topic['rest']['unknown'] == 18
    assert topic['comparisons'][0]['rest_observed_share'] is None
    assert topic['comparisons'][0]['difference_percentage_points'] is None
    assert r['fields']['cta']['comparisons'] == []
    assert 'private.' not in str(r) and 'secret.handle' not in str(r)
    assert r['causal_claims'] is False


def test_tie_break_and_missing_fields():
    r = contrast([dict(content_id=x, username='profile', likes=1, comments=0, followers=10,
                       format='imagem' if x=='a' else 'reels') for x in ('b','a')])
    f = r['fields']['format']
    assert f['top']['counts'] == {'imagem': 1}
    assert f['rest']['counts'] == {'reels': 1}
    assert r['fields']['age_band']['top']['unknown'] == 1
