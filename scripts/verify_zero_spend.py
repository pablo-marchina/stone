"""Verificação local de invariantes financeiras; não consulta sistemas de cobrança externos."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))
def run():
    d=load("config/gate0_decisions.json")
    b=load("config/budget_policy.json")
    p=load("config/source_permissions.json")
    assert d["budget"]["approved_total_ceiling_brl"] == 0
    assert d["budget"]["approved_per_operation_ceiling_brl"] == 0
    assert d["expanded_scope"]["decision"] == "APROVADO_PELO_RESPONSAVEL_DO_PROJETO"
    assert d["expanded_scope"]["data_access_grants"] == "PENDENTES"
    assert d["repo"]["remote"] == "REPO_GITHUB_EXISTENTE_ACESSIVEL"
    for key in ("approved_total_budget","monthly_ceiling","per_operation_ceiling","paid_api_per_run_max","paid_api_monthly_max","paid_storage_max","paid_ad_spend_max","paid_video_generation_max","github_actions_billed_minutes_max"):
        assert b[key] == 0, key
    assert b["allowed_billed_services"] == []
    assert b["paid_cloud_enabled"] is False
    assert b["automatic_cloud_provisioning"] is False
    assert p["external_operations_enabled"] is False
    assert all(x["status"] == "PENDING" and x["approval_ref"] is None for x in p["entries"])
    assert not list((ROOT/".github/workflows").glob("*.yml"))
    assert not list((ROOT/".github/workflows").glob("*.yaml"))
    print("PASS — invariantes locais de gasto zero e bloqueio externo")
if __name__ == "__main__":
    run()
