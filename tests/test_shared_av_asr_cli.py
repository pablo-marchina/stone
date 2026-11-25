"""Integration of shared-AV failure diagnosis with the existing private CLI."""
from hashlib import sha256
import json

import pytest

from scripts import a02_asr_strict_diagnostic as cli
from test_shared_av_asr_diagnostic import make_report


@pytest.fixture
def sandbox(tmp_path,monkeypatch):
    report,_=make_report(monkeypatch,negative_speech=True)
    private=tmp_path/'artifacts'/'private'
    private.mkdir(parents=True)
    source=private/'shared.json'
    source.write_text(json.dumps(report),encoding='utf-8')
    digest=sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(cli,'ROOT',tmp_path)
    calls=[]
    monkeypatch.setattr(cli,'check_checkout',lambda root,head:calls.append(head))
    args=['--expected-head','f'*40,'--report-kind','shared_av',
          '--input-name','shared.json','--input-sha256',digest,
          '--output-name','new.json']
    return private,args,calls


def test_shared_fail_diagnostic_is_private_and_gates_remain_blocked(sandbox,capsys):
    folder,args,calls=sandbox
    assert cli.main(args)==0
    receipt=json.loads(capsys.readouterr().out)
    assert receipt['suite']=='shared_av'
    assert receipt['strict_thresholds_are_informational_only'] is True
    assert receipt['shared_gate_passed_in_report'] is False
    assert receipt['production_approved'] is False
    assert receipt['case_count']==7
    assert calls==['f'*40,'f'*40]
    output=json.loads((folder/'new.json').read_text())
    assert output['source_shared_engineering_gate_passed'] is False
    assert output['negative_transcript_words']==2
    assert receipt['output_sha256']==sha256((folder/'new.json').read_bytes()).hexdigest()


@pytest.mark.parametrize('change',[
    ('--input-sha256','0'*64),
    ('--input-name','../shared.json'),
    ('--output-name','../../shared.json'),
    ('--expected-head','bad'),
])
def test_private_input_guards_and_no_outputs(sandbox,change):
    folder,args,_=sandbox
    key,value=change
    args[args.index(key)+1]=value
    assert cli.main(args)==2
    assert not (folder/'new.json').exists()


def test_shared_format_not_silently_accepted_as_standard_asr(sandbox):
    folder,args,_=sandbox
    args.remove('--report-kind')
    args.remove('shared_av')
    assert cli.main(args)==2
    assert not (folder/'new.json').exists()


def test_output_immutability(sandbox):
    folder,args,_=sandbox
    (folder/'new.json').write_text('older evidence')
    assert cli.main(args)==2
    assert (folder/'new.json').read_text()=='older evidence'


def test_duplicate_json_key_in_source_is_rejected(sandbox):
    folder,args,_=sandbox
    source=folder/'shared.json'
    source.write_text('{"status":"fake","status":"fake"}')
    args[args.index('--input-sha256')+1]=sha256(source.read_bytes()).hexdigest()
    assert cli.main(args)==2
    assert not (folder/'new.json').exists()
