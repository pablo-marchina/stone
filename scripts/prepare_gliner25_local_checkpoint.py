"""Explicit public checkpoint acquisition for DEC-017 E1.1.

Only download open GLiNER model weights after a human CLI opt-in. This script
never accesses Instagram/YouTube data and never invokes paid inference APIs.
Store checkpoints OUTSIDE the repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil

REPO_ID = "fastino/GLiNER2.5-multi-Decide"
# Published by the source repository for the original model.safetensors.
# https://huggingface.co/fastino/GLiNER2.5-multi-Decide/blob/95f87c2984126e9a66db6bc3805847d09f00d415/model.safetensors
PUBLISHED_WEIGHTS_SHA256 = "9efe0f88c99f2aa794452e9559dc60e98d60d9fa2bf1b60cf2710411b6da5b4e"
ALLOW_PATTERNS = [
    "*.json", "*.safetensors", "*.model", "*.txt", "README.md", "LICENSE*",
]
REQUIRED_FILES = ("model.safetensors", "config.json", "tokenizer.json")
MANIFEST_NAME = "tapi_e11_checkpoint_manifest.json"


def _hash(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_local_checkpoint(directory: Path) -> dict:
    """Validate existence, source architecture, hashes and provenance, no network."""
    directory = directory.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("CHECKPOINT_DIRECTORY_REQUIRED")
    for name in REQUIRED_FILES:
        file = directory / name
        if not file.is_file() or file.is_symlink():
            raise ValueError("CHECKPOINT_REQUIRED_FILE_MISSING: " + name)
    cfg = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    if cfg.get("architecture") != "boundary" or cfg.get("model_name") != "microsoft/mdeberta-v3-base":
        raise ValueError("UNEXPECTED_GLINER_CHECKPOINT_ARCHITECTURE")
    weights = directory / "model.safetensors"
    if weights.stat().st_size < 800_000_000:
        raise ValueError("CHECKPOINT_WEIGHTS_TRUNCATED_OR_NOT_ORIGINAL")
    try:
        from safetensors import safe_open
    except ImportError as exc:
        raise RuntimeError("SAFETENSORS_REQUIRED_FOR_CHECKPOINT_VALIDATION") from exc
    with safe_open(str(weights), framework="pt", device="cpu") as handle:
        tensor_count = len(handle.keys())
    if tensor_count < 100:
        raise ValueError("CHECKPOINT_HAS_TOO_FEW_TENSORS")
    files = {}
    for name in REQUIRED_FILES:
        f = directory / name
        files[name] = {"sha256": _hash(f), "bytes": f.stat().st_size}
    if files["model.safetensors"]["sha256"] != PUBLISHED_WEIGHTS_SHA256:
        raise ValueError("CHECKPOINT_VENDOR_PUBLISHED_SHA256_MISMATCH")
    manifest_path = directory / MANIFEST_NAME
    recorded_revision = None
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded_revision = manifest.get("revision")
        if manifest.get("repository") != REPO_ID:
            raise ValueError("CHECKPOINT_MANIFEST_REPOSITORY_MISMATCH")
        for name, facts in files.items():
            claimed = manifest.get("files", {}).get(name, {})
            if claimed.get("sha256") != facts["sha256"] or claimed.get("bytes") != facts["bytes"]:
                raise ValueError("CHECKPOINT_MANIFEST_HASH_MISMATCH")
    return {
        "repository": REPO_ID, "revision": recorded_revision,
        "architecture": cfg["architecture"], "model_name": cfg["model_name"],
        "tensor_count": tensor_count, "files": files,
        "manifest_present": manifest_path.is_file(),
    }


def _not_inside_project(destination: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    if destination == project or destination.is_relative_to(project):
        raise ValueError("CHECKPOINT_DIR_MUST_BE_OUTSIDE_PROJECT")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Explicit public GLiNER checkpoint download")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--confirm-public-download", action="store_true",
                        help="Required to allow a free public download from Hugging Face")
    args = parser.parse_args(argv)
    if not args.confirm_public_download:
        parser.error("Download not authorized: pass --confirm-public-download explicitly")
    raw_destination = Path(args.model_dir).expanduser()
    if raw_destination.is_symlink():
        parser.error("Checkpoint target cannot be a symlink")
    destination = raw_destination.resolve()
    _not_inside_project(destination)
    if destination.is_symlink():
        parser.error("Checkpoint target cannot be a symlink")
    if shutil.disk_usage(destination.parent if destination.parent.exists() else Path.home()).free < 3_000_000_000:
        parser.error("At least 3 GB free disk is required")
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as exc:
        raise RuntimeError('Install the optional local dependency: python -m pip install -e ".[system_one_local]"') from exc

    info = HfApi().model_info(REPO_ID)
    revision = info.sha
    license_tag = getattr(getattr(info, "card_data", None), "license", None)
    if license_tag not in (None, "apache-2.0"):
        raise RuntimeError("MODEL_LICENSE_CHANGED_REVIEW_REQUIRED")
    if not revision or len(revision) != 40:
        raise RuntimeError("CHECKPOINT_IMMUTABLE_REVISION_REQUIRED")
    manifest_file = destination / MANIFEST_NAME
    if manifest_file.exists():
        existing = json.loads(manifest_file.read_text(encoding="utf-8"))
        if existing.get("revision") != revision:
            raise ValueError("CHECKPOINT_REVISION_CHANGED_USE_SEPARATE_DIRECTORY")
    snapshot_download(
        repo_id=REPO_ID, revision=revision,
        local_dir=str(destination), allow_patterns=ALLOW_PATTERNS,
    )
    validated = validate_local_checkpoint(destination)
    validated["revision"] = revision
    manifest = {"schema_version": "tapi-gliner-e11-checkpoint.v1",
                "repository": REPO_ID, "revision": revision,
                "license_declared_on_model_card": "Apache-2.0",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "files": validated["files"]}
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Checkpoint saved locally. Immutable revision:", revision)
    print("Weight SHA256:", validated["files"]["model.safetensors"]["sha256"])
    print("Files validated; model inference has NOT been run by this downloader.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
