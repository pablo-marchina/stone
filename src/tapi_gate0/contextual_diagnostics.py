"""Safe, bounded diagnostics for local caption inference. Never expose input text."""
from __future__ import annotations

KNOWN_REASONS = frozenset({
    "LOCAL_CHECKPOINT_NOT_FOUND", "CHECKPOINT_REQUIRED_FILE_MISSING",
    "UNEXPECTED_GLINER_CHECKPOINT_ARCHITECTURE", "CHECKPOINT_WEIGHTS_TRUNCATED_OR_NOT_ORIGINAL",
    "SAFETENSORS_REQUIRED_FOR_CHECKPOINT_VALIDATION", "CHECKPOINT_HAS_TOO_FEW_TENSORS",
    "CHECKPOINT_VENDOR_PUBLISHED_SHA256_MISMATCH", "CHECKPOINT_MANIFEST_REPOSITORY_MISMATCH",
    "CHECKPOINT_MANIFEST_HASH_MISMATCH", "CHECKPOINT_DIR_MUST_BE_OUTSIDE_PROJECT",
    "LOCAL_SYSTEM_ONE_WEIGHTS_DIRECTORY_REQUIRED", "INSTALL_OPTIONAL_GLINER2_LOCAL_EXTRA",
    "INVALID_LOCAL_CLASSIFIER_OUTPUT", "REAL_GLINER_CLASSIFY_TEXT_OUTPUT_INCOMPATIBLE",
    "BD_CAPTION_INVALID", "BD_CONTEXTUAL_EVIDENCE_MISMATCH", "BD_CONTEXTUAL_FIELD_MISMATCH",
    "BD_CONTEXTUAL_DECISION_MISMATCH", "BD_CONTEXTUAL_PARTITION_MISMATCH",
    "BD_CONTEXTUAL_UNKNOWN_STATUS", "TEXT_EVIDENCE_SHA256_MISMATCH",
    "BD_CONTEXTUAL_SMOKE_ALL_ABSTAINED",
})
KNOWN_MODULES = frozenset({"torch", "gliner2", "safetensors", "transformers", "tokenizers", "sentencepiece",
                           "pydantic", "sqlalchemy", "tapi_gate0", "huggingface_hub", "numpy"})


def safe_failure(exc, stage):
    """Fixed reason/module allowlists; no exception message, paths, SQL or tracebacks."""
    kind = type(exc).__name__
    # Only fixed built-in / common dependency exception class names are exposed.
    if kind not in {"ValueError", "ValidationError", "RuntimeError", "OSError", "FileNotFoundError",
                    "PermissionError", "ModuleNotFoundError", "ImportError", "KeyError", "TypeError",
                    "AttributeError", "IndexError", "JSONDecodeError", "OperationalError",
                    "IntegrityError", "DatabaseError", "SafetensorError", "OutOfMemoryError"}:
        kind = "OtherError"
    result = {"failure_stage": stage, "error_type": kind}
    # Check only exact known codes or a fixed code followed by ': '. Never return suffix.
    if exc.args and isinstance(exc.args[0], str):
        reason = exc.args[0].partition(": ")[0]
        if reason in KNOWN_REASONS:
            result["reason_code"] = reason
    if isinstance(exc, ImportError):
        name = getattr(exc, "name", None)
        if isinstance(name, str) and name.split(".")[0] in KNOWN_MODULES:
            result["missing_module"] = name.split(".")[0]
    return result
