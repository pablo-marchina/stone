# IMP-074 / DEC-008 / A11 — real process termination recovery (23/11/2026)

## Scope
The direct SQL orchestration baseline now has six mandatory process-death tests: the three existing modes (analisar, recomendar, gerar_criativo) crossed with termination immediately before or after the second checkpoint's SQL commit. A real child process is killed by its parent after reaching a bounded marker. After reopening the SQLite file, the test requires rollback of an uncommitted event or preservation of a committed event, exact final receipt parity with an uninterrupted run, sequential nonduplicated events, terminal replay and all existing negative authority flags. Only the test harness injects a pause into the child; production code is unchanged.

Traceability: IMP-027, IMP-074/CAP-005/U05, DEC-008; partial recovery evidence for G1/G2, not acceptance of CT-05/CT-07. No native LangGraph saver, external tool, operational corpus, rights, model, paid API or production effect.

## Executed local evidence
Base PR #79 SHA c7e519db1ccb9d645de74a7a55d060c84aff8137: source ZIP SHA-256 87886738a917cba6a0f37a1a39dfe192a2b3914c307534decc677b21e3329d1c; ZIP comment equals base SHA; CRC clean; relevant modified source blobs verified after CRLF normalization. Six Python focal stages independently passed (A02.7 integrated 47; A05/A07 417; A06 35; ASR diagnostics 91; fixture batch 40; CDP 13), total 643; Node 19; zero-spend PASS. The earlier 133-test battery overlaps these stages and is not added to the total. Fifteen planning matrix files match the original v6.1 overlay after line-ending normalization. The archive omitted repository docs, so this was not the full 32-blob Git mirror validator.

New local files tested: six process-kill tests passed in 5.73s; combined new process recovery and A11 contract tests **39 passed in 6.33s**. Python 3.11 grammar preflight checked 412 files, PASS; zero spend PASS; Chromium visual parity **7/7**. The A11 stage target is now 423 (previously 417 plus six). The 423-case stage was not executed as one stage on this increment. No official signed/pinned A11 packet: source archive has no .git metadata and omits docs and some root files. Independent checks are not an official A11 receipt or full regression.

Local tested Git blob hashes:
- tests/test_dec008_process_recovery.py: 42f2fb277faaa1bd8a7a11b4f3b18af7603804cc
- scripts/a11_focal_evidence_packet.py: 02f8d86c20e1e0334fbff9ba71944e1b54dab61f
- tests/test_a11_focal_evidence_packet.py: 3a5fc34b7187df64265ea2829fde28dd3b7d2d1a

## Remaining
Native LangGraph dependency/saver is absent from the local Linux environment, so native process recovery remains NOT_RUN. Windows Job Objects and native model assets are still host-dependent. Preserve synthetic/technical status, run native and consolidated full regression only on the selected final candidate, evaluate scientific and Studio authorization boundaries, and close remaining architectural capabilities against the original acceptance criteria. DEC-008 OPEN; G0–G6 and IMP-131 BLOCKED. No merge, deployment, external spend or new authority.
