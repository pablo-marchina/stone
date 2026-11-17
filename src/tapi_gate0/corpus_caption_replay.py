"""A01.5: opt-in replay of saved caption reports, never inference or admission.

Pin bytes, reconstruct deterministic evidence, reaudit the entire original
population at startup, then check current rights and row binding at read time.
Saved model outputs are not independently attested.
"""
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .connectors import ConnectorError
from .discovery_audience_exploratory import evidence_tier, report_rows as audience_rows
from .discovery_batch import BatchManifest
from .discovery_caption_research import require_scoped_research, _idle, _rows
from .discovery_corpus_readiness import readiness_report
from .discovery_rubric_contrasts import report_rows as rubric_rows, revalidate_row
from .evidence_lab import ReportRef, read_pinned, ROOT

VERSION = "external-caption-replay-read.v1"
PREFIX = "TAPI_CAPTION_REPLAY_"
MODEL_REVISION = "e173bca1f0c4217d7a55b3b0c705d5ece8a0218d"
MODEL_WEIGHTS = "9efe0f88c99f2aa794452e9559dc60e98d60d9fa2bf1b60cf2710411b6da5b4e"


@dataclass(frozen=True)
class ReplayConfig:
    tenant: str
    viewer: str
    manifest: ReportRef
    audience: ReportRef
    topic_cta: ReportRef
    proof_offer: ReportRef


def config_from_env(env):
    keys = ("TENANT", "MANIFEST_NAME", "MANIFEST_SHA256", "AUDIENCE_NAME",
            "AUDIENCE_SHA256", "TOPIC_CTA_NAME", "TOPIC_CTA_SHA256",
            "PROOF_OFFER_NAME", "PROOF_OFFER_SHA256")
    v = {k: env.get(PREFIX+k, "") for k in keys}
    if not any(v.values()):
        return None
    if not all(v.values()) or not re.fullmatch(r"[0-9]{5,32}", env.get("TAPI_META_IG_ID", "")):
        raise ValueError("CAPTION_REPLAY_CONFIG_INCOMPLETE")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", v["TENANT"]):
        raise ValueError("CAPTION_REPLAY_TENANT_INVALID")
    return ReplayConfig(v["TENANT"], env["TAPI_META_IG_ID"],
        *(ReportRef(v[k+"_NAME"], v[k+"_SHA256"]) for k in
          ("MANIFEST","AUDIENCE","TOPIC_CTA","PROOF_OFFER")))


def _status(status):
    return {"schema_version": VERSION, "status": status,
            "canonical": False, "scientific_admission": False,
            "model_predictions_independently_verified": False,
            "model_predictions_reexecuted": False, "media_processing_allowed": False}


class CaptionReplay:
    def __init__(self, engine, config, root=ROOT):
        self.config = config
        refs = (config.manifest, config.audience, config.topic_cta, config.proof_offer)
        if len({r.name for r in refs}) != 4:
            raise ValueError("CAPTION_REPLAY_DISTINCT_REPORTS_REQUIRED")
        manifest, audience, topic, proof = (read_pinned(root, ref) for ref in refs)
        self.frame = BatchManifest.model_validate(manifest)
        fingerprint = self.frame.fingerprint()
        if (audience.get("model_revision") != MODEL_REVISION
                or audience.get("model_weights_sha256") != MODEL_WEIGHTS
                or audience.get("local_caption_scope_allowed") is not True
                or audience.get("local_caption_scope_policy") != "dec018-bd-caption-research.v1"
                or audience.get("external_data_accessed") is not False):
            raise ValueError("CAPTION_REPLAY_AUDIENCE_SCOPE_INVALID")
        saved = audience_rows(audience, fingerprint)
        parsed = []
        for report, ref, expected in (
            (topic, config.topic_cta, {"tema_principal","tipo_cta"}),
            (proof, config.proof_offer, {"prova_social","oferta_ou_beneficio_explicito"})):
            fields, records = rubric_rows(report, fingerprint, model_revision=MODEL_REVISION,
                model_weights_sha256=MODEL_WEIGHTS)
            if set(fields) != expected or set(records) != set(saved):
                raise ValueError("CAPTION_REPLAY_PARTITION_MISMATCH")
            parsed.append((fields, records, ref.digest))
        require_scoped_research(engine, config.tenant, self.frame, config.viewer)
        self._entries = {}
        def observe(source, post, metric):
            cid = post.content_id
            row = saved.get(cid)
            if cid in self._entries or not row or row["username"] != source.username:
                raise ValueError("CAPTION_REPLAY_PARTITION_MISMATCH")
            tier = evidence_tier(post.caption, row)
            fields = {}
            for keys, records, digest in parsed:
                values = revalidate_row(post.caption,cid,source.username,metric.snapshot_id,records[cid],keys)
                for k,v in values.items():
                    cell = next(f for f in records[cid]["fields"] if f["field"] == k)
                    fields[k] = {"state":"candidate" if v is not None else "abstained",
                        "value":v, "reason":cell["reason"], "report_sha256":digest,
                        "evidence_span_count":len(cell["evidence_spans"]),
                        "claim_only":k in ("prova_social","oferta_ou_beneficio_explicito")}
            self._entries[cid] = {"source_account_id":source.expected_ig_id,
                "caption_sha256":row["caption_sha256"],"snapshot_id":metric.snapshot_id,
                "audience_tier":tier,"audience_reason":row["grounding"]["reason"],
                "fields":fields,"caption_characters":len(post.caption)}
        ready = readiness_report(engine,config.tenant,self.frame,config.viewer,_record_observer=observe)
        if set(self._entries)!=set(saved) or len(saved)!=ready["first_blocking_stage"]["CAPTION_AVAILABLE_FOR_ASSESSMENT"]:
            raise ValueError("CAPTION_REPLAY_PARTITION_MISMATCH")
        require_scoped_research(engine, config.tenant, self.frame, config.viewer)
        self._provenance = {"manifest_sha256":fingerprint,"audience_report_sha256":config.audience.digest,
            "model_revision":MODEL_REVISION,"model_weights_sha256":MODEL_WEIGHTS,
            "reaudited_at":ready["as_of"],"population":len(saved)}

    def summary(self):
        return {**_status("ready"),**self._provenance,
            "audience_tiers":dict(Counter(x["audience_tier"] for x in self._entries.values())),
            "field_candidates":{k:sum(x["fields"][k]["state"]=="candidate" for x in self._entries.values())
                for k in ("tema_principal","tipo_cta","prova_social","oferta_ou_beneficio_explicito")}}

    def detail(self, db, tenant, row, post, snapshots, now):
        if tenant != self.config.tenant:
            return _status("disabled")
        entry = self._entries.get(post.content_id)
        if entry is None:
            return _status("outside_report_population")
        try:
            _idle(db,tenant)
            scopes = _rows(db,tenant,self.frame,self.config.viewer,now)
            if not scopes or any(action!="ALREADY_PROVISIONED" for _,action,_ in scopes):
                return _status("scope_blocked")
        except ConnectorError:
            return _status("scope_blocked")
        if (entry["source_account_id"] != row["source_account_id"] or not post.caption
                or sha256(post.caption.encode()).hexdigest()!=entry["caption_sha256"]
                or not snapshots or snapshots[0].snapshot_id!=entry["snapshot_id"]):
            return _status("stale_row")
        # Never return raw captions, offsets, private paths, viewer IDs or grant documents.
        return json.loads(json.dumps({**_status("ready"),**self._provenance,**entry,
            "caption_text_returned":False,"snapshot_and_caption_match":True}))
