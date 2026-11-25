# DEC-008 / A02.7 / A11 — protected AV review ledger (23/11/2026)

## Functional increment

A protected audiovisual candidate review now uses the existing agent SQL ledger. The new internal `av_candidate_review` mode is deliberately excluded from `LocalGraphPlan` and the loopback API. It records technical plan, retrieve, evidence_verify and output_verify receipts; it does not perform scientific analysis, recommendation, CreativeSpec creation, publication or external tool invocation.

- The queue owns the SQLite BEGIN IMMEDIATE transaction. The protected fusion evaluator is reused inside that transaction, then the guarded projection and checkpoint CAS share the same connection.
- Each step reopens the selected encrypted derivatives through the existing rights and coverage checks, including on terminal replay. The plan binds the content, root object, four distinct canonical artifact IDs and research-only purpose. The ledger stores only hashes and technical state.
- Every previous node digest is reconstructed from the live candidate projection. Drift, scope mismatch, revoked rights or an invalid plan rolls back the step, including a newly reserved run. Partial coverage or all-abstained candidates result in ABSTAINED at evidence_verify. TRACE_RECORDED is technical only; all authority/science/production flags remain false.
- The existing public modes and historical plan schemas are unchanged. No new migration is required: existing mode column accommodates the private mode. No HTTP route exposes the new plan. No LangGraph saver parity, hard-kill recovery, PostgreSQL rights path or cross-database atomicity is established by this increment.

## Validation and regression coverage

Eight new portable tests in tests/test_dec008_protected_av_review.py exercise actual SQLite checkpoint tables and real protected projection with a test double for the protected source. Executed in an isolated Python 3.13.5 / SQLAlchemy 2.0.50 / Pydantic 2.13.5 environment: **8 passed in 0.33s**. Exact Git blobs verified:

- agent_graph_checkpoints.py: 164a9906795690df25c57b7ee63754bb9e37574e
- agent_graph_protected_av_dec008.py: 654bc7ab6b386efe7cfc47c5cc9e32ef970128de
- asset_system_one_guarded_handoff.py: cbe5b5922a112c4ad024a1fbd6d6aee1ee41e450
- test_dec008_protected_av_review.py: 5e1f2295127fba8bbbc0fc997cdbecd6ec866fc6

The isolated package supplied a minimal tenant-table module and explicit stand-ins for the protected storage and fusion imports; the test monkeypatches the source with a simulated guard and revocation. This is not execution of the full private checkout, actual signed-rights decryption or native media processing. Nine existing signed-rights integration cases now exercise the real adapter, including rollback, terminal revocation and digest-only records. Their execution on this HEAD is **NOT_RUN**.

A11 continues to require ten stages. A02.7 integrated remains 47 cases (unchanged number of expanded existing cases). A05/A07 increases from 407 to 417 (eight portable cases plus one additional registered ledger mode and one explicit rejection of the new mode by LocalGraphPlan). These are expected counts, not observed approvals.

## Remaining work

Validate the full protected integration in the actual checkout; establish native LangGraph and real process-death recovery for the appropriate scope, then close science, retrieval and operation-specific creative authorization. This increment does not grant operational rights or close DEC-008. G0–G6 / IMP-131 remain BLOCKED; no merge, deployment or external spending authorized.
