"""CAP-023: ETag/version diff and human-reviewed structured edit previews.

A proposed change is NOT generated or authorized by an LLM. Data from an
untrusted model must pass the same deterministic schema and operator review.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .domain import Id
from .studio_e1 import DesignDocument, StudioError, StudioStore, TextLayerPatch


def studio_etag(doc: DesignDocument) -> str:
    """Strong ETag scoped to the exact version's canonical JSON."""
    digest = sha256(doc.model_dump_json().encode()).hexdigest()
    return f'"{digest}"'


def assert_etag(doc: DesignDocument, if_match: str | None, expected_version: int):
    if doc.version != expected_version:
        raise StudioError("STUDIO_VERSION_CONFLICT", 409)
    if if_match is not None and (if_match == '*' or if_match != studio_etag(doc)):
        raise StudioError("STUDIO_ETAG_MISMATCH", 412)


def _flatten(value, prefix=""):
    """Flat, bounded immutable JSON diff for an authenticated tenant."""
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _flatten(value[key], f"{prefix}/{key}")
    elif isinstance(value, list):
        # Lists use position because ordering is meaningful for pages/layers.
        for index, item in enumerate(value):
            yield from _flatten(item, f"{prefix}/{index}")
        yield f"{prefix}/length", len(value)
    else:
        yield prefix, value


def version_diff(store: StudioStore, tenant: str, document_id: str,
                 left: int, right: int) -> dict:
    if not 1 <= left <= 1_000_000 or not 1 <= right <= 1_000_000:
        raise StudioError("STUDIO_INVALID_VERSION", 422)
    before = store.get(tenant, document_id, left)
    after = store.get(tenant, document_id, right)
    a = dict(_flatten(before.model_dump(mode="json")))
    b = dict(_flatten(after.model_dump(mode="json")))
    changes = [{"path": path, "before": a.get(path), "after": b.get(path)}
               for path in sorted(a.keys() | b.keys()) if a.get(path) != b.get(path)]
    if len(changes) > 2000:
        raise StudioError("STUDIO_DIFF_TOO_LARGE", 413)
    return {"document_id": document_id, "from_version": left,
            "to_version": right, "changes": changes,
            "from_etag": studio_etag(before), "to_etag": studio_etag(after)}


class ProposedTextEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    page_id: Id
    layer_id: Id
    text: str = Field(min_length=1, max_length=2000)
    origin: Literal["operator", "untrusted_model"] = "operator"


class ApplyTextProposal(ProposedTextEdit):
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    operator_confirmed: Literal[True]


def _proposed_patch(doc: DesignDocument, proposal: ProposedTextEdit) -> tuple[dict, str]:
    from copy import deepcopy
    import json

    if doc.version != proposal.expected_version:
        raise StudioError("STUDIO_VERSION_CONFLICT", 409)
    new = deepcopy(doc.model_dump())
    found = False
    for page in new["pages"]:
        if page["id"] != proposal.page_id:
            continue
        for layer in page["layers"]:
            if layer["id"] == proposal.layer_id:
                if layer["kind"] != "text":
                    raise StudioError("STUDIO_PATCH_TEXT_LAYER_REQUIRED", 422)
                layer["text"] = proposal.text
                layer["origin"] = "operator_edit"
                found = True
    if not found:
        raise StudioError("STUDIO_LAYER_NOT_FOUND", 404)
    # A preview never grants editorial or rights approvals.
    new.update(version=doc.version+1, approval_status="draft",
               rights_status="pending_review", reference_status="unverified")
    checked = DesignDocument.model_validate(new)
    identity = {"document_id": doc.document_id, "tenant_id": doc.tenant_id,
                "base_etag": studio_etag(doc), "page_id": proposal.page_id,
                "layer_id": proposal.layer_id, "text": proposal.text,
                "origin": proposal.origin}
    digest = sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return checked.model_dump(mode="json"), digest


def preview_text_proposal(store: StudioStore, tenant: str, document_id: str,
                          proposal: ProposedTextEdit):
    doc = store.get(tenant, document_id)
    candidate, digest = _proposed_patch(doc, proposal)
    old = dict(_flatten(doc.model_dump(mode="json")))
    proposed = dict(_flatten(candidate))
    return {"base_version": doc.version, "preview_sha256": digest,
            "requires_operator_confirmation": True,
            "scientifically_validated": False, "production_approved": False,
            "changes": [{"path": k, "before": old.get(k), "after": proposed.get(k)}
                        for k in sorted(old.keys() | proposed.keys())
                        if old.get(k) != proposed.get(k)]}


def apply_text_proposal(store: StudioStore, tenant: str, actor: str, document_id: str,
                        proposal: ApplyTextProposal, if_match: str | None):
    current = store.get(tenant, document_id)
    assert_etag(current, if_match, proposal.expected_version)
    _, digest = _proposed_patch(current, proposal)
    if digest != proposal.preview_sha256:
        raise StudioError("STUDIO_PREVIEW_CHANGED", 409)
    return store.patch_text_layer(tenant, actor, document_id, TextLayerPatch(
        expected_version=proposal.expected_version, page_id=proposal.page_id,
        layer_id=proposal.layer_id, text=proposal.text))
