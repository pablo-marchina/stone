#!/usr/bin/env python3
"""Reconstruct audited v5.2 CSV matrices from the original ZIP + versioned evidence overlays.

No network, credentials, platform activity or production state mutation.
Example:
  python scripts/sync_plano_v52_audit.py "/path/ORIGINAL.zip" --out-dir "/path/output"
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

SOURCE_SHA = "0dbb51bf18a75734fcb2121373590bfc1ba3ae5cd729aff9a4dcb537491aa04d"
MAIN_SHA = "79bb0173c90cbc993481bf1e959154adf796a5de"
CUT = "2026-11-05"
PREFIX = "tapi_plano_unico_v5_2/"
ROOT = Path(__file__).resolve().parents[1] / "planning/v5_2/audit_2026-11-05"
ROWS = {"MATRIZ_CAPACIDADES.csv": 23, "BACKLOG_UNICO_IMPORTAVEL.csv": 204,
        "MATRIZ_DECISOES.csv": 15, "MATRIZ_GATE_GLOBAL.csv": 7,
        "DEPENDENCIAS.csv": 543, "MATRIZ_ISO_23x9.csv": 207,
        "MATRIZ_CRITERIO_CAPACIDADE.csv": 414}
AUDIT = {
    "MATRIZ_CAPACIDADES.csv": ("MATRIZ_CAPACIDADES_EVIDENCIAS.csv", "feature_id", "operational_status"),
    "BACKLOG_UNICO_IMPORTAVEL.csv": ("BACKLOG_EVIDENCIAS_INCREMENTAIS.csv", "id", "status"),
    "MATRIZ_DECISOES.csv": ("MATRIZ_DECISOES_EVIDENCIAS.csv", "decision_id", None),
    "MATRIZ_GATE_GLOBAL.csv": ("MATRIZ_GATES_EVIDENCIAS.csv", "gate_id", "result_status"),
}
NEW_DEC = {
    "DEC-016": ("Populacao e elegibilidade cientifica por publicacao", "Conteudo dirigido a MPEs e independente de porte do produtor", "IMP-048;IMP-050;IMP-053;IMP-135;IMP-167;IMP-170"),
    "DEC-017": ("Experimento System One/GLiNER offline PT-BR", "GLiNER e texto sao laboratorio, nao rubrica audiovisual homologada", "IMP-026;IMP-060;IMP-064;IMP-065;IMP-069;IMP-136"),
    "DEC-018": ("Aprovacao ampla e dispensa de revisao independente declaradas pelo responsavel", "Dispensa da revisao humana altera criterio de aceite; NAO equivale a cumprir >=50 da proposta original. Instrumento institucional externo nao anexado.", "IMP-004;IMP-024;IMP-062;IMP-167;IMP-169"),
}

def parse(data):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    rows = list(reader)
    return rows, list(reader.fieldnames)

def dump(rows, cols):
    io_out = io.StringIO(newline="")
    writer = csv.DictWriter(io_out, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return io_out.getvalue().encode("utf-8-sig")

def checked_ids(rows, key, expected):
    ids = [x[key] for x in rows]
    assert len(ids) == expected and len(set(ids)) == expected, (key, len(ids), expected)
    return ids

def check_graph(deps, tasks):
    nodes = set(tasks)
    children = {x: [] for x in nodes}
    deg = {x: 0 for x in nodes}
    for e in deps:
        u, v = e["predecessor"], e["successor"]
        assert u in nodes and v in nodes and u != v, (u, v)
        children[u].append(v)
        deg[v] += 1
    stack = [x for x in nodes if deg[x] == 0]
    visited = 0
    while stack:
        u = stack.pop()
        visited += 1
        for v in children[u]:
            deg[v] -= 1
            if deg[v] == 0:
                stack.append(v)
    assert visited == len(nodes), "Cycle in dependency graph"

def main(archive, outdir):
    path = Path(archive)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SOURCE_SHA, "Original ZIP hash mismatch"
    with ZipFile(path) as z:
        content = {Path(n).name: z.read(n) for n in z.namelist() if n.startswith(PREFIX) and not n.endswith("/")}
    for file, expected in ROWS.items():
        assert len(parse(content[file])[0]) == expected, file
    result = dict(content)
    old_tasks, _ = parse(content["BACKLOG_UNICO_IMPORTAVEL.csv"])
    original_ids = checked_ids(old_tasks, "id", 204)
    original_deps = content["DEPENDENCIAS.csv"]
    check_graph(parse(original_deps)[0], original_ids)
    audited = {}
    for name, (overlay_name, key, status_field) in AUDIT.items():
        rows, cols = parse(content[name])
        overlay, _ = parse((ROOT / overlay_name).read_bytes())
        evidence = {r[key]: r for r in overlay}
        assert len(evidence) == len(overlay) and set(evidence) - set(x[key] for x in rows) <= ({"DEC-016", "DEC-017", "DEC-018"} if name == "MATRIZ_DECISOES.csv" else set())
        historical = {"status":"baseline_status_20261030","operational_status":"baseline_operational_status_20261030",
                      "result_status":"baseline_result_status_20261030"}
        extra = ["baseline_status_20261030" if not status_field else historical[status_field],
                 "audit_execution_status", "audit_evidence_pr", "audit_note", "audit_as_of", "audit_main_sha"]
        cols += [x for x in extra if x not in cols]
        for r in rows:
            old = r.get(status_field) if status_field else r.get("status")
            historical_field = extra[0]
            r[historical_field] = old
            ev = evidence.get(r[key])
            if ev:
                st = ev["audit_execution_status"]
                if status_field:
                    r[status_field] = ev.get("status") or st
                if name == "BACKLOG_UNICO_IMPORTAVEL.csv":
                    r["proof_state"] = ev.get("proof_state") or ("ALTERACAO_ACEITE_DECLARADA" if r[key]=="IMP-062" else "EVIDENCIA_INCREMENTAL_NAO_HOMOLOGADA")
                r.update(audit_execution_status=st,audit_evidence_pr=ev["evidence_pr_urls"],
                         audit_note=ev["audit_note"])
            else:
                r.update(audit_execution_status="NAO_COMPROVADO_NESTE_CORTE",audit_evidence_pr="",
                         audit_note="Estado de planejamento preservado; sem afirmacao de ausencia do codigo")
            if name == "BACKLOG_UNICO_IMPORTAVEL.csv" and r[key] in {"IMP-024","IMP-062","IMP-167","IMP-169"}:
                refs = [v for v in r["decision_ids"].split(";") if v]
                if "DEC-018" not in refs: refs.append("DEC-018")
                r["decision_ids"] = ";".join(refs)
            r.update(audit_as_of=CUT, audit_main_sha=MAIN_SHA)
        if name == "MATRIZ_DECISOES.csv":
            # Preserve DEC-001..015, then append only new IDs. Never overwrite the original criterion.
            original_cols = list(parse(content[name])[1])
            for dec_id, (issue, baseline, task_links) in NEW_DEC.items():
                e = evidence[dec_id]
                row = {c:"" for c in cols}
                row.update(decision_id=dec_id,issue=e["issue"],candidates=e["candidates"],
                           baseline=e["baseline"],comparison_protocol=e["comparison_protocol"],
                           linked_tasks=e["linked_tasks"],status=e["status"],
                           decision_evidence=e["decision_evidence"],decision_rule=e["decision_rule"],
                           baseline_status_20261030="NAO_EXISTIA_NA_V52",
                           audit_execution_status=e["audit_execution_status"],audit_evidence_pr=e["evidence_pr_urls"],
                           audit_note=e["audit_note"],audit_as_of=CUT,audit_main_sha=MAIN_SHA)
                rows.append(row)
        audited[name] = rows
        result[name] = dump(rows, cols)
    assert checked_ids(audited["BACKLOG_UNICO_IMPORTAVEL.csv"], "id", 204) == original_ids
    checked_ids(audited["MATRIZ_CAPACIDADES.csv"], "feature_id", 23)
    checked_ids(audited["MATRIZ_DECISOES.csv"], "decision_id", 18)
    checked_ids(audited["MATRIZ_GATE_GLOBAL.csv"], "gate_id", 7)
    assert result["DEPENDENCIAS.csv"] == original_deps
    assert all(a["dependencies"]==b["dependencies"] for a,b in zip(old_tasks,audited["BACKLOG_UNICO_IMPORTAVEL.csv"]))
    check_graph(parse(result["DEPENDENCIAS.csv"])[0], original_ids)
    decs = {x["decision_id"] for x in audited["MATRIZ_DECISOES.csv"]}
    taskids = set(original_ids)
    for r in audited["BACKLOG_UNICO_IMPORTAVEL.csv"]:
        assert all(d in decs for d in r["decision_ids"].split(";") if d)
    for r in audited["MATRIZ_DECISOES.csv"]:
        assert all(t in taskids for t in r["linked_tasks"].split(";") if t)
    # Fail if the rebuild diverges from the exact audited CSVs committed to Git.
    for changed_name in AUDIT:
        assert result[changed_name] == (ROOT / "synced" / changed_name).read_bytes(), ("REBUILD_DIFFERS_FROM_GIT", changed_name)
    assert parse(result["DEPENDENCIAS.csv"])[0] == parse((ROOT / "synced" / "DEPENDENCIAS.csv").read_bytes())[0]
    audit_meta = {"source_zip_sha256":SOURCE_SHA,"audited_main_sha":MAIN_SHA,"date":CUT,
                  "tasks":204,"capabilities":23,"decisions_old":15,"decisions_new":18,
                  "gates":7,"dependencies_preserved":543,
                  "no_reviewers_per_dec018":True,"original_50_reviews_not_fulfilled":True,
                  "full_release_approved":False,
                  "unchanged_csv_sha256":{name:hashlib.sha256(data).hexdigest()
                      for name,data in result.items() if name.endswith(".csv") and name not in AUDIT},
                  "changed_csv_sha256":{name:hashlib.sha256(result[name]).hexdigest() for name in AUDIT}}
    out = Path(outdir);out.mkdir(parents=True, exist_ok=True)
    for name,data in result.items():
        if name.endswith(".csv"): (out/name).write_bytes(data)
    (out/"MANIFESTO_AUDITORIA_2026-11-05.json").write_text(
        json.dumps(audit_meta, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    with ZipFile(out.parent/"TAPI_Stone_Matrizes_v5_2_Sincronizadas.zip","w",ZIP_DEFLATED,compresslevel=9) as z:
        for item in sorted(out.iterdir()): z.write(item, arcname="tapi_plano_unico_v5_2_atualizado/"+item.name)
    print(json.dumps(audit_meta,ensure_ascii=False))

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("source_zip")
    cli.add_argument("--out-dir",required=True)
    args=cli.parse_args()
    main(args.source_zip,args.out_dir)
