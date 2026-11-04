"""DEC-017 E1.1: real local GLiNER2.5-multi-Decide inference smoke.

This script does not fetch weights, access provider APIs, train, write to the
research corpus, or print any evidence text. Synthetic fixture only.
A PASS means compatibility of this installed checkpoint, NOT scientific quality.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import platform
from statistics import median
from time import perf_counter

from prepare_gliner25_local_checkpoint import (
    validate_local_checkpoint, _not_inside_project,
)
from tapi_gate0.system_one_e1 import (
    LocalGLiNERDecider, DeterministicTextDecider,
    to_rubric_assessment,
)
from tapi_gate0.system_one_benchmark import BenchmarkCase, evaluate_paired


def _rss_megabytes() -> float | None:
    try:
        import psutil
        return round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 2)
    except ImportError:
        return None


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    i = (len(ordered) - 1) * fraction
    lower = int(i)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (i - lower), 3)


def _load_synthetic(path: Path) -> list[BenchmarkCase]:
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise ValueError("SYNTHETIC_FIXTURE_REQUIRED_MAX_5MB")
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = BenchmarkCase.model_validate_json(line)
        if (case.evidence.source_kind != "synthetic" or case.gold_kind != "synthetic_fixture"
                or case.split != "smoke"):
            raise ValueError("E11_REQUIRES_SYNTHETIC_SMOKE_ONLY")
        cases.append(case)
    if not 2 <= len(cases) <= 100:
        raise ValueError("E11_SMOKE_REQUIRES_2_TO_100_CASES")
    if len({(x.evidence.tenant_id, x.evidence.content_id) for x in cases}) != len(cases):
        raise ValueError("DUPLICATE_SYNTHETIC_CASE")
    return cases


def _run_inference(
    *,
    model_dir: Path,
    cases: list[BenchmarkCase],
    repeats: int,
    warmup: int,
) -> dict:
    if os.getenv("TAPI_SYSTEM_ONE_ENABLED") != "1":
        raise PermissionError("SYSTEM_ONE_EXPERIMENT_DISABLED")
    _not_inside_project(model_dir)
    checkpoint = validate_local_checkpoint(model_dir)

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("TORCH_REQUIRED_FOR_REAL_GLINER_INFERENCE") from exc
    rss_before = _rss_megabytes()
    decider = LocalGLiNERDecider(model_dir)
    start = perf_counter()
    with torch.inference_mode():
        extractor = decider._load()  # one explicit, measured cold load
    load_ms = round((perf_counter() - start) * 1000, 3)
    rss_after_load = _rss_megabytes()

    # Test the documented classifying API itself, independently of TAPI policy.
    with torch.inference_mode():
        preflight = extractor.classify_text(
            "A loja vendeu mais produtos esta semana.",
            {"topic": ["vendas", "finanças", "marketing"]},
        )
    if (not isinstance(preflight, dict) or
            not isinstance(preflight.get("topic"), str) or
            preflight["topic"] not in ("vendas", "finanças", "marketing")):
        raise RuntimeError("REAL_GLINER_CLASSIFY_TEXT_OUTPUT_INCOMPATIBLE")

    total = 0
    latencies = []
    peak_rss = rss_after_load
    digests_by_case: dict[str, set[str]] = {}
    responses_without_answer = 0
    with torch.inference_mode():
        for _ in range(warmup):
            decider.evaluate(cases[0].evidence)
        for _ in range(repeats):
            for case in cases:
                started = perf_counter()
                answer = decider.evaluate(case.evidence)
                latencies.append((perf_counter() - started) * 1000)
                total += 1
                if answer.evidence_fingerprint != case.evidence.fingerprint():
                    raise RuntimeError("REAL_MODEL_EVIDENCE_FINGERPRINT_MISMATCH")
                assessment = to_rubric_assessment(case.evidence, answer)
                if len(type(assessment.values).model_fields) != 20:
                    raise RuntimeError("RUBRIC_20_FIELD_CONTRACT_VIOLATION")
                if assessment.values.hook_primeiros_3s is not None:
                    raise RuntimeError("UNOBSERVED_VIDEO_HOOK_ASSERTED")
                if answer.is_scientific_review is not False:
                    raise RuntimeError("MODEL_CANNOT_BE_HUMAN_SCIENTIFIC_REVIEW")
                predictions = [
                    (d.field_id, d.value, d.abstained) for d in answer.decisions
                ]
                if all(d.abstained for d in answer.decisions):
                    responses_without_answer += 1
                fingerprint = sha256(json.dumps(
                    predictions, ensure_ascii=False,
                    separators=(",", ":")
                ).encode("utf-8")).hexdigest()
                digests_by_case.setdefault(case.evidence.content_id, set()).add(fingerprint)
                reading = _rss_megabytes()
                if reading is not None:
                    peak_rss = max(peak_rss or 0, reading)

    with torch.inference_mode():
        paired = evaluate_paired(cases, {
            "baseline": DeterministicTextDecider(),
            "local_gliner": decider,
        })
    return {
        "schema_version": "tapi-gliner-e11-real-validation.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "CHECKPOINT_LOADED_REAL_INFERENCE_EXECUTED",
        "scientifically_validated": False,
        "model": {
            "repository": checkpoint["repository"],
            "revision": checkpoint["revision"],
            "architecture": checkpoint["architecture"],
            "extractor_class": type(extractor).__name__,
            "weights_sha256": checkpoint["files"]["model.safetensors"]["sha256"],
            "weights_bytes": checkpoint["files"]["model.safetensors"]["bytes"],
            "tensor_count": checkpoint["tensor_count"],
            "manifest_present": checkpoint["manifest_present"],
            "gliner2_version": _package_version("gliner2"),
            "torch_version": _package_version("torch"),
        },
        "execution": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cuda_available": bool(torch.cuda.is_available()),
            "n_synthetic_cases": len(cases),
            "warmup_calls": warmup,
            "measured_calls": total,
            "model_load_ms": load_ms,
            "inference_p50_ms": _percentile(latencies, .50),
            "inference_p95_ms": _percentile(latencies, .95),
            "rss_before_mb": rss_before,
            "rss_after_load_mb": rss_after_load,
            "peak_sampled_rss_mb": peak_rss,
            "n_consistency_disagreements": sum(len(s) > 1 for s in digests_by_case.values()),
            "n_all_abstained": responses_without_answer,
            "external_api_inference_calls": 0,
            "downloading_during_inference": False,
        },
        "paired_synthetic_smoke": paired,
        "limitations": [
            "Synthetic labels validate integration and metrics, not model quality.",
            "Checkpoint source revision is independently attested only if a matching manifest exists.",
            "RSS is unavailable when psutil is not installed; no GPU VRAM or energy estimate.",
            "The hook, temporal, visual and entrepreneurial-proof fields are not observed.",
            "MPE targeting predictions are candidates, never scientific reviews.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run GLiNER2.5 REAL checkpoint smoke OFFLINE")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--warmup", type=int, default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 10 or not 0 <= args.warmup <= 5:
        parser.error("repeats 1..10; warmup 0..5")
    model_dir = Path(args.model_dir).expanduser().resolve()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    if output_path == input_path:
        parser.error("input and output must differ")
    report = _run_inference(
        model_dir=model_dir,
        cases=_load_synthetic(input_path),
        repeats=args.repeats, warmup=args.warmup,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print("REAL LOCAL GLINER PASS — checkpoint loaded and inference executed")
    print("Checkpoint SHA256:", report["model"]["weights_sha256"])
    print("Measured inference calls:", report["execution"]["measured_calls"])
    print("Inference p50/p95 (ms):", report["execution"]["inference_p50_ms"],
          "/", report["execution"]["inference_p95_ms"])
    print("Synthetic fixture only; no scientific accuracy claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
