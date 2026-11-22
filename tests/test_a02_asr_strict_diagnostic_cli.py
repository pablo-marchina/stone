from hashlib import sha256
import json
import os
from pathlib import Path
import pytest

from scripts import a02_asr_strict_diagnostic as cli
from test_asr_strict_diagnostic import report_for, change_case


@pytest.fixture
def setup(tmp_path, monkeypatch):
    folder = tmp_path / 'artifacts' / 'private'
    folder.mkdir(parents=True)
    source = folder / 'input.json'
    report = report_for()
    change_case(report, 'cta', '')
    source.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    digest = sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(cli,'ROOT',tmp_path)
    checks = []
    monkeypatch.setattr(cli,'check_checkout', lambda root, head:checks.append(head))
    args = ['--expected-head', 'a'*40, '--input-name', 'input.json',
            '--input-sha256', digest, '--output-name', 'new.json']
    return folder,args,checks


def test_failed_benchmark_is_diagnosed_without_release(setup,capsys):
    folder,args,checks=setup
    assert cli.main(args)==0
    summary=json.loads(capsys.readouterr().out)
    assert summary['strict_failure_case_count']==1
    assert summary['engineering_gate_passed_in_report'] is False
    assert summary['production_approved'] is False
    assert summary['global_gates_released'] is False
    output=json.loads((folder/'new.json').read_text())
    assert output['strict_failure_cases']==['cta']
    assert output['strict_thresholds_unchanged'] is True
    assert checks==['a'*40,'a'*40]
    assert summary['output_sha256']==sha256((folder/'new.json').read_bytes()).hexdigest()
    if os.name=='posix':
        assert (folder/'new.json').stat().st_mode&0o077==0


def test_failed_sha_never_creates_output_or_leaks_words(setup,capsys):
    folder,args,checks=setup
    args[args.index('--input-sha256')+1]='0'*64
    assert cli.main(args)==2
    assert not (folder/'new.json').exists()
    assert 'Salve' not in capsys.readouterr().out


def test_existing_output_never_overwritten(setup):
    folder,args,checks=setup
    (folder/'new.json').write_text('existing')
    assert cli.main(args)==2
    assert (folder/'new.json').read_text()=='existing'


@pytest.mark.parametrize('option,value', [
    ('--input-name', '../secret.json'),
    ('--output-name','../../secret.json'),
    ('--expected-head','invalid'),
])
def test_path_escape_and_invalid_head_fail_closed(setup,option,value):
    folder,args,checks=setup
    args[args.index(option)+1]=value
    assert cli.main(args)==2
    assert not (folder/'new.json').exists()


def test_partial_and_duplicate_json_keys_rejected(setup):
    folder,args,checks=setup
    source=folder/'input.json'
    source.write_text('{"status":"PASS","status":"PASS"}')
    args[args.index('--input-sha256')+1]=sha256(source.read_bytes()).hexdigest()
    assert cli.main(args)==2
    assert not (folder/'new.json').exists()


def test_stale_checkout_blocks_analysis(setup,monkeypatch):
    folder,args,checks=setup
    def fail(*a):raise RuntimeError('unexpected sensitive checkout')
    monkeypatch.setattr(cli,'check_checkout',fail)
    assert cli.main(args)==2
    assert not (folder/'new.json').exists()


def test_source_symlink_is_rejected(setup, monkeypatch):
    folder,args,checks=setup
    orig=folder/'input.json'
    destination=folder/'source.json'
    orig.rename(destination)
    try:
        orig.symlink_to(destination)
    except (OSError, NotImplementedError):
        # Windows may deny user-created symlinks. Still exercise the
        # explicit rejection path, never silently skip this guard.
        actual_is_symlink = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink",
                            lambda candidate: (candidate == orig
                                               or actual_is_symlink(candidate)))
    assert cli.main(args)==2
    assert not (folder/'new.json').exists()


def test_private_directory_symlink_is_rejected_without_external_access(setup, monkeypatch):
    folder,args,_=setup
    actual_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink",
                        lambda candidate: (candidate == folder
                                           or actual_is_symlink(candidate)))
    assert cli.main(args)==2
    assert not (folder/'new.json').exists()


def test_output_symlink_is_rejected_before_creating_diagnostic(setup, monkeypatch):
    folder,args,_=setup
    output = folder/'new.json'
    actual_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink",
                        lambda candidate: (candidate == output
                                           or actual_is_symlink(candidate)))
    assert cli.main(args)==2
    assert not output.exists()
