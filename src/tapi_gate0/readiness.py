"""Estado técnico observável: não converte pendência em aprovação."""
import json
import os
from pathlib import Path

CONFIG = Path(os.environ.get("TAPI_PROJECT_ROOT", Path.cwd())) / "config"

def status() -> dict:
    config = json.loads((CONFIG / "gate0_decisions.json").read_text(encoding="utf-8"))
    criteria = json.loads((CONFIG / "gate0_criteria.json").read_text(encoding="utf-8"))
    return {
        "project": "TAPI Stone",
        "stage": "Gate 0 — Engineering Readiness",
        "gate0a": config["gate0a"],
        "gate0b": config["gate0b"],
        "global_release": config["architecture_global_release"],
        "source_operations_enabled": False,
        "remote_repo_created": config["repo"].get("remote") == "REPO_GITHUB_EXISTENTE_ACESSIVEL",
        "expanded_scope_user_approved": True,
        "institutional_scope_confirmation": "UNVERIFIED",
        "financial_spend_ceiling_brl": 0,
        "source_use_grants": "PENDING",
        "cloud_selected": config["infrastructure"]["selected_provider"],
        "checks": criteria["gate0a"],
        "is_production_ready": False,
    }
