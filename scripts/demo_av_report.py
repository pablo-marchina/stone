"""Read a successful local authored-observation test report, never live inference.

Only the fixed nine authored fixtures are displayable; no external media,
source IDs, or rights credentials are projected. This is not a signed proof.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from hashlib import sha256

CASES = {
    'agreement': ('Organize suas vendas.', 'Organize suas vendas'),
    'conflict': ('Calcule os custos fixos.', 'Organize suas vendas'),
    'complementary': ('Salve este conteúdo.', 'Organize suas vendas'),
    'cta_conflict': ('Comente sua dúvida.', 'Salve este post'),
    'context_veto': ('Não salve este post.', 'Salve este post'),
    'split_request': ('Salve', 'este post'),
    'unrecognized_audio': ('Palavras sem classificação.', 'Organize suas vendas'),
    'audio_insufficient': (None, 'Organize suas vendas'),
    'audio_no_signal': (None, 'Organize suas vendas'),
}
FIELDS = ('tema_principal', 'tipo_cta', 'tem_cta', 'texto_na_tela')
PROCESSORS = ('asr_vad', 'ocr', 'temporal', 'vlm')
SCHEMA = 'stone-demo-authored-av-evidence.v1'


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value) is not None


def validate(report):
    if (type(report) is not dict or set(report) != {'schema_version','test_report_sha256','cases','native_inference','scientifically_validated','production_approved'}
            or report['schema_version'] != SCHEMA or not _sha(report['test_report_sha256'])
            or any(report[k] is not False for k in ('native_inference','scientifically_validated','production_approved'))):
        raise ValueError('DEMO_AV_REPORT_INVALID')
    rows = report['cases']
    if type(rows) is not list or len(rows) != len(CASES):
        raise ValueError('DEMO_AV_REPORT_INVALID')
    seen = set()
    for row in rows:
        case = row['case']
        if (set(row) != {'case','authored_audio','authored_screen','coverage','fields','source_fingerprint','ledger_status','ledger_revision','chain_sha256','revocation_denied','native_inference'}
                or case not in CASES or case in seen or (row['authored_audio'],row['authored_screen']) != CASES[case]
                or row['revocation_denied'] is not True or row['native_inference'] is not False
                or not _sha(row['source_fingerprint']) or not _sha(row['chain_sha256'])
                or (row['ledger_status'],row['ledger_revision']) != (('ABSTAINED',3) if case=='audio_insufficient' else ('TRACE_RECORDED',4))):
            raise ValueError('DEMO_AV_REPORT_INVALID')
        seen.add(case)
        expected = {p: 'observed' for p in PROCESSORS}
        if CASES[case][0] is None: expected['asr_vad'] = 'abstained'
        if row['coverage'] != expected or [f['field_id'] for f in row['fields']] != list(FIELDS):
            raise ValueError('DEMO_AV_REPORT_INVALID')
        for f in row['fields']:
            allowed = (None,'vendas','salvar',True)
            if (set(f) != {'field_id','state','value','suppressed_by_guard','support_count','veto_count','provenance_sha256','baseline_value','reason'}
                    or f['state'] not in ('candidate','abstained') or (f['state']=='abstained') != (f['value'] is None)
                    or f['value'] not in allowed or f['baseline_value'] not in allowed
                    or type(f['suppressed_by_guard']) is not bool or not _sha(f['provenance_sha256'])
                    or not all(type(f[k]) is int and 0<=f[k]<=100 for k in ('support_count','veto_count'))
                    or not isinstance(f['reason'],str) or not re.fullmatch(r'[A-Z0-9_]{1,100}', f['reason'])):
                raise ValueError('DEMO_AV_REPORT_INVALID')
            if f['suppressed_by_guard'] and (f['baseline_value'] is None or f['value'] is not None):
                raise ValueError('DEMO_AV_REPORT_INVALID')
    return report


def read_report(path):
    try:
        if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 100_000:
            raise ValueError()
        return validate(json.loads(path.read_bytes()))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError('DEMO_AV_REPORT_INVALID') from None


def from_junit(path):
    raw = path.read_bytes()
    if len(raw)>1_000_000 or b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
        raise ValueError('DEMO_AV_JUNIT_INVALID')
    root = ET.fromstring(raw)
    rows = []
    tests = root.findall('.//testcase')
    if len(tests)!=len(CASES): raise ValueError('DEMO_AV_JUNIT_INVALID')
    for test in tests:
        if not test.attrib.get('name','').startswith('test_shared_av_ablation_policy_and_rights[') or any(test.find(tag) is not None for tag in ('failure','error','skipped')):
            raise ValueError('DEMO_AV_JUNIT_INVALID')
        values = test.findall('./properties/property[@name="demo_av_case"]')
        if len(values)!=1: raise ValueError('DEMO_AV_JUNIT_INVALID')
        rows.append(json.loads(values[0].attrib['value']))
    return validate(dict(schema_version=SCHEMA,test_report_sha256=sha256(raw).hexdigest(),cases=rows,
                         native_inference=False,scientifically_validated=False,production_approved=False))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('junit',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    report=from_junit(args.junit)
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,separators=(',',':')); f.write('\n')
