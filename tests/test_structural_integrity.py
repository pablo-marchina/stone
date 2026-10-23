import json
from pathlib import Path
import jsonschema
from tapi_gate0.policy import EXTERNAL_SOURCES

ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))

def test_rubric_exact_20_fields():
    schema=load('reference/rubric_candidate.schema.json')
    assert len(schema['properties'])==20
    assert len(schema['required'])==20
    jsonschema.Draft202012Validator.check_schema(schema)

def test_contracts_candidate_schemas_well_formed():
    data=load('reference/contract_candidates.json')
    assert len(data['schemas'])>=23
    for schema in data['schemas'].values(): jsonschema.Draft202012Validator.check_schema(schema)

def test_all_sources_operations_denied_by_config():
    perms=load('config/source_permissions.json')
    assert perms['external_operations_enabled'] is False
    assert len(perms['entries'])>=len(EXTERNAL_SOURCES)
    assert all(p['status']!='APPROVED' and p['approval_ref'] is None for p in perms['entries'])

def test_no_approved_budget_or_production_cloud():
    budget=load('config/budget_policy.json')
    assert budget['approved_total_budget'] == 0
    assert budget['monthly_ceiling'] == 0
    assert budget['per_operation_ceiling'] == 0
    assert budget['paid_cloud_enabled'] is False
    assert budget['paid_api_per_run_max']==0

def test_18_22_12_coverage_from_upstream():
    cov=load('config/traceability.json')
    assert len(cov['requirements'])==18
    assert len(cov['capabilities'])==22
    assert len(cov['decisions'])==12


def test_zero_financial_spend_and_scope_authority():
    dec=load('config/gate0_decisions.json')
    assert dec['expanded_scope']['decision'] == 'APROVADO_PELO_RESPONSAVEL_DO_PROJETO'
    assert dec['expanded_scope']['institutional_confirmation'] == 'NAO_COMPROVADA'
    assert dec['source_permissions']['status'] == 'PENDENTE'
    assert dec['budget']['approved_total_ceiling_brl'] == 0
    budget=load('config/budget_policy.json')
    assert budget['paid_ad_spend_max'] == 0
    assert budget['allowed_billed_services'] == []
    assert not list((ROOT/'.github/workflows').glob('*.yml'))
