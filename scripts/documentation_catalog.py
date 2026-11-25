"""Read-only views of the Stone documentation and explicit planning links."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = Path("planning/base_atemporal")
MIRROR = Path("docs/base_atemporal/MANIFESTO_ESPELHO.json")
REGISTRIES = {
    "IMP": ("BACKLOG_UNICO_IMPORTAVEL.csv", "id"),
    "CAP": ("MATRIZ_CAPACIDADES.csv", "feature_id"),
    "U": ("MATRIZ_REQUISITOS.csv", "requirement_id"),
    "DEC": ("MATRIZ_DECISOES.csv", "decision_id"),
    "CT": ("CATALOGO_TESTES_CT.csv", "id"),
    "GATE": ("MATRIZ_GATE_GLOBAL.csv", "gate_id"),
    "F": ("MATRIZ_LACUNAS_F01_F18.csv", "finding_id"),
    "H": ("HIPOTESES_E_EXPERIMENTOS.csv", "id"),
    "SCHEMA": ("INVENTARIO_SCHEMAS_CANDIDATOS.csv", "schema_id"),
    "ISO": ("MATRIZ_ISO_23x9.csv", "matrix_id"),
    "CONFLICT": ("MATRIZ_CONFLITOS.csv", "id"),
    "DOMAIN": ("MATRIZ_DOMINIO.csv", "domain_group"),
    "CONTRACT": ("CATALOGO_CONTRATOS.csv", "operation"),
}


def rows(root, filename):
    with (root / PLAN / filename).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def tokens(value):
    return [part.strip() for part in value.split(";") if part.strip()]


def blob_sha(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def classification(path):
    if path.startswith("docs/base_atemporal/"):
        return "baseline_mirror_or_adoption"
    if path.startswith("docs/governance/STATE_") or path.startswith("docs/records/"):
        return "historical"
    if path.startswith("docs/governance/"):
        return "governance"
    if path.startswith("docs/guides/"):
        return "guide"
    if path.startswith("docs/architecture/"):
        return "architecture_view"
    if path in ("README.md", "AGENTS.md", "docs/README.md", "docs/REPOSITORY_WORKFLOW.md"):
        return "entrypoint"
    return "legacy_unreviewed"


def index(root):
    paths = [p for p in (root / "docs").rglob("*.md") if p.is_file()]
    paths += [root / name for name in ("README.md", "AGENTS.md") if (root / name).is_file()]
    result = []
    for path in sorted(paths):
        rel = path.relative_to(root).as_posix()
        title = next((line[2:].strip() for line in path.read_text(encoding="utf-8-sig").splitlines()
                      if line.startswith("# ")), path.stem)
        result.append({"path": rel, "title": title, "class_hint": classification(rel),
                       "git_blob_sha1": blob_sha(path)})
    return {"kind": "local_markdown_inventory_not_semantic_audit", "documents": result}


def graph(root):
    nodes, edges = {}, set()
    tables = {}

    def identity(kind, row):
        key = REGISTRIES[kind][1]
        # These two catalogs have no official row ID; namespace their natural keys.
        if kind in ("DOMAIN", "CONTRACT"):
            return kind + ":" + row[key] if row[key] else ""
        return row[key]
    for kind, (filename, key) in REGISTRIES.items():
        tables[kind] = rows(root, filename)
        for row in tables[kind]:
            ident = identity(kind, row)
            if not ident or ident in nodes:
                raise ValueError("empty or duplicate ID: " + ident)
            nodes[ident] = {"id": ident, "kind": kind, "source": (PLAN / filename).as_posix()}

    def link(source, target, relation, origin):
        if source not in nodes or target not in nodes:
            raise ValueError("unresolved explicit link: " + source + " -> " + target + " in " + origin)
        edges.add((source, target, relation, origin))

    def fields(kind, column, relation, reverse=False):
        filename, key = REGISTRIES[kind]
        for row in tables[kind]:
            for target in tokens(row[column]):
                ident = identity(kind, row)
                a, b = (target, ident) if reverse else (ident, target)
                link(a, b, relation, filename + ":" + column)

    for column, relation in (("capability_ids", "implements_capability"), ("criterion_ids", "addresses_requirement"),
                             ("decision_ids_vigentes", "governed_by"), ("gates", "subject_to_gate")):
        fields("IMP", column, relation)
    fields("CAP", "tasks", "implements_capability", True)
    fields("CAP", "requirement_ids", "addresses_requirement")
    fields("U", "task_ids", "addresses_requirement", True)
    fields("DEC", "linked_tasks", "governed_by", True)
    fields("CT", "criterion_id", "tests_requirement")
    fields("CT", "planned_task_ids", "planned_test_for")
    fields("GATE", "task_ids", "subject_to_gate", True)
    fields("F", "corrective_tasks", "corrective_task")
    fields("H", "task_ids", "experiment_task")
    fields("H", "capability_ids", "experiment_capability")
    fields("SCHEMA", "linked_to_capability", "candidate_for")
    fields("ISO", "capability_id", "measures_capability")
    fields("ISO", "test_links", "quality_test_link")
    fields("DOMAIN", "task_ids", "domain_task")
    fields("DOMAIN", "capability_ids", "domain_capability")
    fields("CONTRACT", "capability_id", "contract_for")
    fields("CONTRACT", "task_ids", "contract_task")
    # Candidate names not present in the schema inventory are not invented nodes.
    unresolved_candidates = []
    for row in tables["CONTRACT"]:
        name = row["proposed_contract"]
        ident = identity("CONTRACT", row)
        if name in nodes and nodes[name]["kind"] == "SCHEMA":
            link(ident, name, "candidate_schema", "CATALOGO_CONTRATOS.csv:proposed_contract")
        else:
            unresolved_candidates.append({"contract": ident, "candidate": name})
    for row in rows(root, "DEPENDENCIAS.csv"):
        link(row["predecessor"], row["successor"], "precedes", "DEPENDENCIAS.csv")
    for row in rows(root, "MATRIZ_CRITERIO_CAPACIDADE.csv"):
        link(row["criterion_id"], row["capability_id"], "matrix_relation",
             "MATRIZ_CRITERIO_CAPACIDADE.csv:" + row["relation"])
        for task in tokens(row["intersecting_tasks"]):
            link(row["criterion_id"], task, "matrix_intersection", "MATRIZ_CRITERIO_CAPACIDADE.csv")
    return {"kind": "planning_projection_not_acceptance",
            "candidate_names_not_in_inventory": sorted(unresolved_candidates, key=lambda x: x["contract"]),
            "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
            "edges": [{"source": a, "target": b, "relation": rel, "origin": origin}
                      for a, b, rel, origin in sorted(edges)]}


def check(root):
    subprocess.run([sys.executable, str(root / "docs/base_atemporal/ferramentas/validar_espelho.py")],
                   cwd=root, check=True, stdout=subprocess.DEVNULL)
    manifest = json.loads((root / MIRROR).read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if blob_sha(root / entry["path"]) != entry["git_blob_sha1"]:
            raise ValueError("mirror drift: " + entry["path"])
    g = graph(root)
    inv = index(root)
    entries = {item["path"] for item in inv["documents"]}
    expected = {"README.md", "AGENTS.md", "docs/README.md", "docs/governance/STANDARD.md",
                "docs/governance/TEMPLATES.md", "docs/architecture/README.md", "docs/guides/README.md"}
    if not expected <= entries:
        raise ValueError("missing entrypoint: " + ", ".join(sorted(expected - entries)))
    return {"status": "PASS_DOCUMENTATION_STRUCTURE", "mirror_blobs": len(manifest["files"]),
            "markdown_files": len(entries), "nodes": len(g["nodes"]), "edges_with_provenance": len(g["edges"]),
            "candidate_names_not_in_inventory": len(g["candidate_names_not_in_inventory"]),
            "software_tests": "NOT_RUN", "gates": "NOT_ASSESSED", "semantic_audit": "NOT_PERFORMED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "index", "graph"))
    args = parser.parse_args()
    try:
        result = {"check": check, "index": index, "graph": graph}[args.command](ROOT)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("FAIL_DOCUMENTATION: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
