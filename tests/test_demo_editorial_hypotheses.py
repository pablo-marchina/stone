from scripts.demo_editorial_hypotheses import hypotheses
from scripts.demo_editorial_contrast import contrast


def test_hypotheses_with_missing_values_and_full_coverage():
    rows = [dict(content_id=f'private.{i:02}', username='private.profile', likes=30-i,
                 comments=0, followers=100, format='reels' if i < 2 else 'imagem',
                 topic='marketing' if i == 0 else 'vendas' if i == 2 else None,
                 cta=None, age_band='14-29') for i in range(20)]
    packet = hypotheses(contrast(rows), 'a'*64)
    f, t = packet['hypotheses']
    assert f['value']=='reels' and f['missingness_bounds_pp']==[100,100]
    assert f['positive_under_all_missing_assignments']
    assert t['value']=='marketing' and t['difference_pp']==100
    assert t['missingness_bounds_pp']==[-44.444444,100]
    assert not t['positive_under_all_missing_assignments']
    assert t['top_count']==1 and t['top_observed']==1 and t['top_posts']==2
    assert packet['report_sha256']=='a'*64 and not packet['publication_allowed']
    assert not packet['joint_effect_estimated'] and 'private.' not in str(packet)


def test_no_comparable_values_no_hypothesis():
    rows=[dict(content_id='a',username='a',likes=1,comments=0,followers=10,format='reels')]
    assert hypotheses(contrast(rows),'b'*64)['hypotheses']==[]
