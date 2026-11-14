"""Offline contextual audience candidate pilot using the existing System One model.

Default: policy readiness only. Synthetic smoke has no real data. Real execution
requires existing operation-specific policy to permit Instagram classification.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from sqlalchemy.exc import SQLAlchemyError
from tapi_gate0.connectors import ConnectorError
from tapi_gate0.discovery_audience_contextual import (
    POLICY, compare_candidate, paired_counts, require_caption_classification,
)
from tapi_gate0.discovery_audience_signals import assess_caption
from tapi_gate0.policy import decide, Operation
from tapi_gate0.discovery_caption_research import require_scoped_research, plan_research

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    "Se você é MEI, aprenda a organizar o fluxo de caixa.",
    "Não é para MEIs: evento exclusivo para grandes corporações.",
    "O número de MEIs cresceu no último ano.",
    "Você vende pelo WhatsApp? Organize os pedidos da sua loja e calcule sua margem.",
    "Nossa equipe celebra mais uma conquista.",
    "Compre dois produtos e ganhe desconto no supermercado.",
)


def evaluate_text(decider, *, tenant, cid, creator, caption, rights=None):
    from tapi_gate0.system_one_e1 import EvidenceBundle, ObservedText
    lexical = assess_caption(caption)
    evidence = EvidenceBundle(tenant_id=tenant, content_id=cid, creator_id=creator,
        source_kind="approved_local" if rights else "synthetic",
        rights_reference=rights, allowed_operations=["offline_classification"] if rights else [],
        observation=ObservedText(modality="caption", text=caption,
            locator="local-caption:" + cid, sha256=lexical["caption_sha256"]))
    answer = decider.evaluate(evidence, fields=("mpe_targeted",))
    return compare_candidate(evidence, answer, lexical)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--synthetic-smoke", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--report-name")
    parser.add_argument("--confirm-all-ingestion-stopped", action="store_true")
    args = parser.parse_args(argv)
    engine = None
    decision = decide("instagram_metadata", Operation.CLASSIFY.value)
    status = {"policy_version": POLICY, "classification_scope_allowed": decision.permitted,
              "classification_policy_code": decision.code, "external_data_accessed": False,
              "scientific_admissions": 0, "human_reviews": 0, "scientifically_validated": False}
    try:
        frame = None
        if args.manifest is not None and not args.synthetic_smoke:
            from tapi_gate0.discovery_batch import BatchManifest
            from tapi_gate0.discovery_local_db import validate_existing_database_url
            from tapi_gate0.sa_store import engine_for
            tenant, viewer = os.getenv("TAPI_TENANT_ID", ""), os.getenv("TAPI_META_IG_ID", "")
            if not tenant or not viewer:
                raise ValueError("MISSING_SCOPE")
            frame = BatchManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
            engine = engine_for(validate_existing_database_url(os.getenv("TAPI_DATABASE_URL", "")))
            plan = plan_research(engine, tenant, frame, viewer)
            status["local_caption_scope_sources"] = plan["scoped_sources"]
            status["local_caption_scope_allowed"] = bool(plan["sources"]) and all(r["action"] == "ALREADY_PROVISIONED" for r in plan["sources"])
        if not args.synthetic_smoke and not args.execute:
            print(json.dumps({"status": "CONTEXTUAL_READINESS", **status}))
            return 0
        if args.execute:
            if frame is None:
                require_caption_classification()
                raise ValueError("MANIFEST_REQUIRED")
            if not args.confirm_all_ingestion_stopped:
                raise ConnectorError("BD_CORPUS_ADMIN_STOP_REQUIRED", 403)
            status["local_caption_scope_policy"] = require_scoped_research(engine, tenant, frame, viewer)
        if os.getenv("TAPI_SYSTEM_ONE_ENABLED") != "1":
            raise ConnectorError("SYSTEM_ONE_EXPERIMENT_DISABLED", 403)
        path = args.model_dir or os.getenv("TAPI_SYSTEM_ONE_LOCAL_MODEL_DIR")
        if not path:
            raise ConnectorError("LOCAL_SYSTEM_ONE_WEIGHTS_DIRECTORY_REQUIRED", 422)
        path = Path(path).expanduser().resolve(strict=True)
        if not args.report_name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json", args.report_name):
            raise ConnectorError("BD_CONTEXTUAL_PRIVATE_REPORT_REQUIRED", 422)
        private = ROOT / "artifacts" / "private"
        if private.resolve() != private.absolute():
            raise ConnectorError("BD_CONTEXTUAL_PRIVATE_ROOT_REDIRECTED", 422)
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        output = private / args.report_name
        if output.exists() or output.is_symlink():
            raise ConnectorError("BD_CONTEXTUAL_REPORT_EXISTS", 409)
        # Existing pinned-checkpoint verification. No remote downloads.
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1")
        try:
            from scripts.prepare_gliner25_local_checkpoint import validate_local_checkpoint, _not_inside_project
        except ModuleNotFoundError:
            from prepare_gliner25_local_checkpoint import validate_local_checkpoint, _not_inside_project
        from tapi_gate0.system_one_e1 import LocalGLiNERDecider
        import torch
        _not_inside_project(path)
        checkpoint = validate_local_checkpoint(path)
        if not checkpoint["manifest_present"] or not re.fullmatch(r"[a-f0-9]{40}", checkpoint["revision"] or ""):
            raise ConnectorError("PINNED_CHECKPOINT_MANIFEST_REQUIRED", 422)
        decider = LocalGLiNERDecider(path)
        details = []
        with torch.inference_mode():
            if args.synthetic_smoke:
                for i, caption in enumerate(FIXTURES):
                    cid = "fixture." + str(i)
                    details.append({"content_id": cid, **evaluate_text(decider, tenant="synthetic",
                        cid=cid, creator="fixture", caption=caption)})
            else:
                from tapi_gate0.discovery_corpus_readiness import readiness_report
                from tapi_gate0.ingestion import stable_id
                def observe(source, cid, caption):
                    # Existing operation decision + active matched source scope, not a
                    # grant invented by the model or supplied by a report.
                    require_scoped_research(engine, tenant, frame, viewer)
                    creator = stable_id("creator", "instagram", source.expected_ig_id)
                    details.append({"content_id": cid, "username": source.username,
                        **evaluate_text(decider, tenant=tenant, cid=cid, creator=creator, caption=caption,
                                        rights="DEC-018:offline_bd_caption_candidate_classification:" + source.expected_ig_id)})
                ready = readiness_report(engine, tenant, frame, viewer, _caption_observer=observe)
                if len(details) != ready["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"]:
                    raise ValueError("BD_CONTEXTUAL_PARTITION_MISMATCH")
                require_scoped_research(engine, tenant, frame, viewer)
                status["manifest_sha256"] = frame.fingerprint()
        report = {"status": "CONTEXTUAL_SYNTHETIC_SMOKE" if args.synthetic_smoke else "CONTEXTUAL_CANDIDATES",
            **status, "synthetic_only": bool(args.synthetic_smoke), "assessed_captions": len(details),
            "paired_counts": paired_counts(details), "model_revision": checkpoint["revision"],
            "model_weights_sha256": checkpoint["files"]["model.safetensors"]["sha256"],
            "targeting_decisions": 0, "database_mutated": False}
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({**report, "private_evidence": details}, stream, ensure_ascii=False, indent=2)
        print(json.dumps({**report, "report_name": args.report_name}, ensure_ascii=False))
        return 0
    except ConnectorError as exc:
        code = exc.code
    except (OSError, ValueError, RuntimeError, SQLAlchemyError, KeyError, TypeError, ImportError):
        code = "BD_CONTEXTUAL_LOCAL_ERROR"
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({"status": "BLOCKED", "code": code, **status}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
