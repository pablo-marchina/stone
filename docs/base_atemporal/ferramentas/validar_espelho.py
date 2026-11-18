"""Verifica o espelho v6.1 localmente. Sem rede, modelos, DB ou alterações."""
import csv, hashlib, json
from pathlib import Path
from collections import Counter, defaultdict
ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "docs/base_atemporal"
PLAN = ROOT / "planning/base_atemporal"
m = json.loads((DOC / "MANIFESTO_ESPELHO.json").read_text(encoding="utf-8"))
def require(ok, msg):
    if not ok:
        raise SystemExit("FAIL: " + msg)
require(len(m["files"]) == 32 and len({e["path"] for e in m["files"]}) == 32, "manifesto")
for e in m["files"]:
    p = ROOT / e["path"]
    require(p.is_file(), e["path"] + " ausente")
    b = p.read_bytes()
    require(hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest() == e["git_blob_sha1"], e["path"] + " diverge")
def rows(name):
    with (PLAN / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
expected = {"BACKLOG_UNICO_IMPORTAVEL.csv":204,"DEPENDENCIAS.csv":543,"MATRIZ_CAPACIDADES.csv":23,
 "MATRIZ_REQUISITOS.csv":18,"MATRIZ_DECISOES.csv":18,"MATRIZ_GATE_GLOBAL.csv":7,
 "MATRIZ_ISO_23x9.csv":207,"MATRIZ_CRITERIO_CAPACIDADE.csv":414,"MATRIZ_DOMINIO.csv":16,
 "CATALOGO_CONTRATOS.csv":28,"CATALOGO_TESTES_CT.csv":28,"INVENTARIO_SCHEMAS_CANDIDATOS.csv":29,
 "MATRIZ_LACUNAS_F01_F18.csv":18}
for f,n in expected.items():
    require(len(rows(f))==n, f + " contagem")
tasks=rows("BACKLOG_UNICO_IMPORTAVEL.csv"); ids={x["id"] for x in tasks}
require(ids=={f"IMP-{i:03d}" for i in range(1,205)}, "IDs")
edges={(x["predecessor"],x["successor"]) for x in rows("DEPENDENCIAS.csv")}
require(len(edges)==543 and all(u in ids and v in ids and u!=v for u,v in edges), "arestas")
children=defaultdict(list); indeg=Counter()
for u,v in edges:
    children[u].append(v); indeg[v]+=1
require({u for u in ids if not children[u]}=={"IMP-131"},"sink")
stack=[u for u in ids if not indeg[u]]; seen=0
while stack:
    u=stack.pop(); seen+=1
    for v in children[u]:
        indeg[v]-=1
        if not indeg[v]: stack.append(v)
require(seen==204,"DAG")
require("DEC-018" in next(x for x in tasks if x["id"]=="IMP-062")["decision_ids_vigentes"],"DEC-018")
print(json.dumps({"status":"PASS_ESPELHO_DOCUMENTAL","exact_blobs":32,"matrix_rows":expected,"dag":"acyclic","unique_sink":"IMP-131","software_tests":"not_run","gates":"not_assessed"},ensure_ascii=False,indent=2))
