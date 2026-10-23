"""Verificador estático, não aprova Gate 0 automaticamente."""
from pathlib import Path
import json, csv, hashlib, sys
ROOT=Path(__file__).resolve().parents[1]
fail=[]

def load(name): return json.loads((ROOT/name).read_text(encoding='utf-8'))

def test(name, condition):
    if not condition: fail.append(name)
    print(('PASS' if condition else 'FAIL')+' '+name)

d=load('config/gate0_decisions.json')
p=load('config/source_permissions.json')
b=load('config/budget_policy.json')
t=load('config/traceability.json')
s=load('reference/rubric_candidate.schema.json')
c=load('reference/contract_candidates.json')
test('repositório privado configurado',d['repo']['choice']=='NOVO' and d['repo']['visibility']=='PRIVADO' and d['repo']['remote']=='REPO_GITHUB_EXISTENTE_ACESSIVEL' and d['repo']['name']=='stone')
test('infraestrutura não escolhida',d['infrastructure']['selected_provider'] is None)
test('teto obrigatório R$0',b['approved_total_budget']==0 and b['monthly_ceiling']==0 and b['per_operation_ceiling']==0 and b['paid_cloud_enabled'] is False and b['paid_api_per_run_max']==0)
test('todas operações externas sem grant',not p['external_operations_enabled'] and all(x['status']=='PENDING' and x['approval_ref'] is None for x in p['entries']))
test('escopo aprovado pelo usuário; autoridade institucional pendente',d['expanded_scope']['decision']=='APROVADO_PELO_RESPONSAVEL_DO_PROJETO' and d['approval_authority']['status']=='ESCOPO_USUARIO_APROVADO_STONE_INTELI_NAO_CONFIRMADA')
test('20 campos candidato',len(s['properties'])==20 and len(s['required'])==20)
test('>=23 candidatos de contrato',len(c['schemas'])>=23)
test('18 critérios, 22 capacidades, 12 decisões',len(t['requirements'])==18 and len(t['capabilities'])==22 and len(t['decisions'])==12)
test('entrega única',d['single_final_delivery'] is True)
test('Gate 0B bloqueado',d['gate0b'].startswith('BLOQUEADO'))
with (ROOT/'reference/CAPABILITIES_GATE0.csv').open(encoding='utf-8') as file:
    caps=list(csv.DictReader(file))
test('22 capacidades não implementadas',len(caps)==22 and all(row['is_implemented']=='false' for row in caps))
print('STATUS=ESTRUTURA_LOCAL_VERIFICADA' if not fail else f'ERROS={len(fail)}')
sys.exit(bool(fail))
