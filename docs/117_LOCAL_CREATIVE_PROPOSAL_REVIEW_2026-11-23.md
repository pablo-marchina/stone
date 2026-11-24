# IMP-078 / IMP-174 — local editorial proposal review (2026-11-23)

## Scope implemented
The local opt-in diagnostic now produces five distinct deterministic educational proposals for a completed, actor-bound synthetic recommendation trace. Each contains an objective, headline, body, CTA, three-part script, caption, hypothesis, explicit uncertainty, synthetic segment, unbranded profile and exact SQL citation. These are authored templates, not model-generated or scientifically optimized creative content; the ranked reference is an example for inspection only and does not establish effectiveness of any template.

The preview replays the plan and ledger under the same SQLite lock used by acceptance, validates the SQL citation and independent B2 synthetic boundary, then rolls back its transaction. The editor explicitly chooses a proposal digest. Acceptance recomputes all inputs and rejects stale or altered digests, wrong actors, incomplete traces and reference changes. It creates the selected editable document, separate generated-proposal provenance event and outbox entry atomically. Provenance identifies the template, citation hash, plan and trace, proposal digest and initial document hash. It does not mark the brief as authored by the operator. Duplicate document IDs and concurrent selection cannot duplicate the document or event. Existing operator-authored draft flow is preserved via shared trace replay. Routes remain opt-in, loopback-only, authenticated admin/editor, and are absent in the production application.

## Executed validation
Using the supplied source archive and successive verified code changes (not a clean Git checkout), on the exact six changed code/test blobs below:
- 16 new proposal tests: all passed, covering five distinct proposals and selections, digest/plan/run/policy drift, extra fields, source drift, open trace, authentication, actor roles, remote access, rollback and concurrent duplication.
- Combined proposal, prior trace-draft/API and focal-packet contract suite: **77 passed in 16.51s**.
- Expanded A05/A07/DEC-008 focal stage: **451 passed in 66.80s**, zero failures/skips. The preceding batches overlap this total.
- Python 3.11 grammar preflight: 416 files, PASS. Zero-spend invariant: PASS.
- Restored the 32 documentary mirror blobs from the supplied original v6.1 ZIP and independently checked every Git blob against the pinned manifest: exact match. Matrix cardinalities (204 IMP, 543 dependencies, 23 CAP, 414 capacity-criterion rows, 28 contracts, 28 CT and other matrices) and DAG with unique sink IMP-131 verified. This is not software homologation.

Changed code/test Git blob hashes verified against remote:
- src/tapi_gate0/agent_trace_draft_handoff.py: dfe24be57f2011afe43865cdb7373788becbc661
- src/tapi_gate0/agent_graph_local_api.py: d8a87826a6c9c54a68dde6986a2a595103f4ed6e
- src/tapi_gate0/agent_creative_proposals_local.py: 6c406dbb0e1e1f4079a5b0816c92c92185c7da6a
- tests/test_agent_creative_proposals_local.py: 19c7771e505388a561989a333c072f73c313bd9c
- scripts/a11_focal_evidence_packet.py: 76d38054401f9b70784aace6d1f7652a3bd1d54b
- tests/test_a11_focal_evidence_packet.py: 25a921709581af80576454d422f8f28f49f712cc

## Boundaries
IMP-078 and IMP-174 receive partial technical evidence, not acceptance of five operational Stone creatives, brand authorization, scientific relevance, semantic matching or model-based creativity. CAP-007/023 remain subject to their original acceptance criteria. Other focal stages were not rerun for this increment. Native LangGraph, PostgreSQL recovery, Windows native inference, actual rights and scientific evaluation remain separate open fronts. No production or publication approval; no external model call, provider spending, merge or gate promotion. DEC-008 OPEN, G0–G6 / IMP-131 BLOCKED.
