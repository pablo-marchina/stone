"""Bounded pipeline coordinator tests with no IO, network or model execution."""
import pytest
from hashlib import sha256
from tapi_gate0 import asset_fixture_batch as batch

PIN='a'*64
ART=('artifact.'+sha256(('job.'+'1'*64+':'+'b'*64).encode()).hexdigest(),
     'artifact.'+sha256(('job.'+'2'*64+':'+'c'*64).encode()).hexdigest())
JOB_A='job.'+'1'*64
JOB_B='job.'+'2'*64

class RightsDenied(Exception):
    pass

class Spec:
    def __init__(self, jid, proc):
        self.job_id=jid;self.processor=proc;self.tenant_id='test_tenant'
        self.object_id='d'*64;self.purpose='research_analysis'
        self.method_version='fixture';self.configuration_sha256='e'*64

class Plan:
    mode='image_pair'
    fingerprint=PIN
    specs=(Spec(JOB_A,'ocr'),Spec(JOB_B,'vlm'))

class Decisions:
    tenant_id='test_tenant'
    object_id='d'*64
    purpose='research_analysis'
    scientific_evidence=False
    canonical_rubric=False
    evidence_fingerprint='e'*64

class Queue:
    def status(self, tenant, job_id):
        receipt = 'b'*64 if job_id == JOB_A else 'c'*64
        return {'tenant_id': tenant, 'job_id': job_id,
                'object_id': 'd'*64, 'state': 'completed',
                'reason': 'encrypted_payload', 'receipt_sha256': receipt}

class Fixture:
    def __init__(self, outcomes):
        self.plan=Plan()
        self.plan.mode='image_pair'
        self.plan.specs=(Spec(JOB_A,'ocr'),Spec(JOB_B,'vlm'))
        self.outcomes=list(outcomes)
        self.queue=Queue()
        self.calls=[]
    def step(self,worker,*,retry_stopped):
        self.calls.append((worker,retry_stopped))
        return self.outcomes.pop(0)

@pytest.fixture(autouse=True)
def patched(monkeypatch):
    monkeypatch.setattr(batch,'FixturePipeline',Fixture)
    monkeypatch.setattr(batch,'CandidateDecisions',Decisions)
    monkeypatch.setattr(batch,'AssetRightsDenied',RightsDenied)
    monkeypatch.setattr(batch,'AssetJobQueue',Queue)

def result(status,**kwargs):
    return dict(plan_sha256=PIN,synthetic_fixture=True,
                scientific_evidence=False,canonical_rubric=False,
                status=status,**kwargs)

def done(status='candidate_complete',**kwargs):
    return result(status,artifact_ids=ART,decisions=Decisions(),**kwargs)

def processed(job,processor):
    return result('processed',job_id=job,processor=processor,job_state='completed',
                  artifact_id=ART[0 if job==JOB_A else 1],model_calls=0)

def run(pipeline,*,ticks=3,**kwargs):
    return batch.run_explicit_fixture_batch(pipeline,'trusted_worker',
        expected_plan_sha256=kwargs.pop('expected_plan_sha256',PIN),max_ticks=ticks,**kwargs)

def test_full_sequence_returns_only_typed_candidate_with_all_rights_flags_false():
    p=Fixture([processed(JOB_A,'ocr'),processed(JOB_B,'vlm'),done()])
    receipt=run(p)
    assert receipt['status']=='CANDIDATE_ONLY'
    assert receipt['candidate_decisions'].tenant_id=='test_tenant'
    assert receipt['artifact_ids']==ART
    assert receipt['global_gates_released'] is False
    assert receipt['production_approved'] is False
    assert receipt['auto_retry_enabled'] is False
    assert receipt['candidate_evidence_sha256']=='e'*64
    assert p.calls==[('trusted_worker',False)]*3

def test_budget_exhaustion_is_not_canonical_or_auto_retry():
    p=Fixture([processed(JOB_A,'ocr'),processed(JOB_B,'vlm')])
    r=run(p,ticks=2)
    assert r['status']=='BUDGET_EXHAUSTED'
    assert r['candidate_decisions'] is None
    assert len(p.calls)==2

@pytest.mark.parametrize('halt',('busy','blocked','recovery_required'))
def test_halts_immediately_without_auto_retry(halt):
    p=Fixture([result(halt,job_id=JOB_A,processor='ocr'),done()])
    r=run(p)
    assert (r['status'],r['reason'])==('HALTED',halt)
    assert p.calls==[('trusted_worker',False)]

@pytest.mark.parametrize('bad',('0'*64,'',None))
def test_bad_pin_denied_before_step(bad):
    p=Fixture([done()])
    with pytest.raises(RightsDenied,match='PLAN_PIN_MISMATCH'):
        run(p,expected_plan_sha256=bad)
    assert p.calls==[]

@pytest.mark.parametrize('budget',(-1,0,4,True))
def test_invalid_tick_budget_denied(budget):
    p=Fixture([done()])
    with pytest.raises(RightsDenied,match='TICK_BUDGET'):
        run(p,ticks=budget)
    assert p.calls==[]

def test_unknown_step_state_denied():
    p=Fixture([result('nope')])
    with pytest.raises(RightsDenied,match='UNKNOWN_STEP_STATUS'):
        run(p)

def test_forged_receipt_cannot_claim_science():
    corrupted=processed(JOB_A,'ocr')
    corrupted['scientific_evidence']=True
    p=Fixture([corrupted])
    with pytest.raises(RightsDenied,match='STEP_RECEIPT_INVALID'):
        run(p)

def test_duplicate_processed_job_denied():
    p=Fixture([processed(JOB_A,'ocr'),processed(JOB_A,'ocr')])
    with pytest.raises(RightsDenied,match='PROCESSED_RECEIPT_INVALID'):
        run(p)

def test_forged_artifact_denied():
    p=Fixture([result('candidate_complete',artifact_ids=(ART[0],'foo'),decisions=Decisions())])
    with pytest.raises(RightsDenied,match='CANDIDATE_BINDING_INVALID'):
        run(p)

def test_candidate_with_wrong_tenant_is_denied():
    wrong=Decisions()
    wrong.tenant_id='other'
    p=Fixture([result('candidate_complete',artifact_ids=ART,decisions=wrong)])
    with pytest.raises(RightsDenied,match='CANDIDATE_BINDING_INVALID'):
        run(p)

def test_unexpected_terminal_for_nonpartial_pipeline_denied():
    p=Fixture([done('candidate_partial',quality_rejections=['ASR_WER'])])
    with pytest.raises(RightsDenied,match='UNEXPECTED_TERMINAL'):
        run(p)

def test_pipeline_plan_mutation_between_steps_denied():
    p=Fixture([processed(JOB_A,'ocr'),done()])
    original=p.step
    def changed(*args,**kwargs):
        receipt=original(*args,**kwargs)
        p.plan=Plan()
        return receipt
    p.step=changed
    with pytest.raises(RightsDenied,match='PLAN_CHANGED_DURING_STEP'):
        run(p)
    assert len(p.calls)==1

def test_worker_is_strictly_validated():
    p=Fixture([done()])
    with pytest.raises(RightsDenied,match='WORKER_INVALID'):
        batch.run_explicit_fixture_batch(p,'../../worker',expected_plan_sha256=PIN,max_ticks=1)
    assert p.calls==[]


def test_partial_quality_remains_experimental_and_reports_rejected_processor():
    p=Fixture([done('candidate_partial',quality_rejections={'ocr': {'quality': 'rejected'}})])
    p.plan.mode='shared_av_partial'
    r=run(p,ticks=1)
    assert r['status']=='CANDIDATE_ONLY'
    assert r['reason']=='candidate_partial'
    assert r['quality_rejected_processors']==('ocr',)
    assert r['canonical_rubric'] is False
    assert r['production_approved'] is False


def test_invalid_partial_quality_rejection_key_denied():
    p=Fixture([done('candidate_partial',quality_rejections={'unknown': {'a': True}})])
    p.plan.mode='shared_av_partial'
    with pytest.raises(RightsDenied,match='PARTIAL_QUALITY_INVALID'):
        run(p,ticks=1)


def test_candidate_fingerprint_is_required():
    bad=Decisions()
    bad.evidence_fingerprint='malformed'
    p=Fixture([result('candidate_complete',artifact_ids=ART,decisions=bad)])
    with pytest.raises(RightsDenied,match='CANDIDATE_BINDING_INVALID'):
        run(p,ticks=1)


def test_unauthorized_pipeline_class_is_refused_before_tick():
    p=object()
    with pytest.raises(RightsDenied,match='PIPELINE_REQUIRED'):
        run(p,ticks=1)


def test_rejected_cross_tenant_plan_is_refused():
    p=Fixture([done()])
    p.plan.specs=(Spec(JOB_A,'ocr'),Spec(JOB_B,'vlm'))
    p.plan.specs[1].tenant_id='other'
    with pytest.raises(RightsDenied,match='JOB_BINDING_INVALID'):
        run(p,ticks=1)


@pytest.mark.parametrize('halt', ('quota', 'rights_blocked', 'empty'))
def test_queue_denial_halts_without_automatic_retry(halt):
    p=Fixture([result(halt,job_id=JOB_A,processor='ocr'),done()])
    receipt=run(p)
    assert receipt['status']=='HALTED'
    assert receipt['reason']==halt
    assert receipt['auto_retry_enabled'] is False
    assert p.calls==[('trusted_worker',False)]


def test_swapped_plausible_artifact_ids_are_denied():
    p=Fixture([result('candidate_complete',artifact_ids=ART[::-1], decisions=Decisions())])
    with pytest.raises(RightsDenied,match='ARTIFACT_PROVENANCE_MISMATCH'):
        run(p,ticks=1)


def test_valid_shaped_artifact_from_foreign_job_denied():
    fake='artifact.'+'e'*64
    p=Fixture([result('candidate_complete',artifact_ids=(fake,ART[1]),decisions=Decisions())])
    with pytest.raises(RightsDenied,match='ARTIFACT_PROVENANCE_MISMATCH'):
        run(p,ticks=1)


@pytest.mark.parametrize('key,value',[
    ('reason','receipt_only'),
    ('state','running'),
    ('receipt_sha256',None),
    ('object_id','not-the-input'),
])
def test_nonpersisted_candidate_receipt_denied(key,value):
    p=Fixture([done()])
    original=p.queue.status
    def wrong(tenant,job_id):
        row=original(tenant,job_id)
        row[key]=value
        return row
    p.queue.status=wrong
    with pytest.raises(RightsDenied,match='PERSISTED_RECEIPT_INVALID'):
        run(p,ticks=1)
