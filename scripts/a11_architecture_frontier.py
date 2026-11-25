"""Read-only, evidence-neutral dependency frontier for the Base Atemporal v6.1.

This is a scheduling diagnostic, NOT an implementation inventory, gate result,
completion percentage, or authority to deploy. No network/database operations.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import heapq
import json
from pathlib import Path

PLAN = Path(__file__).resolve().parents[1] / "planning" / "base_atemporal"
FILES = ("BACKLOG_UNICO_IMPORTAVEL.csv", "DEPENDENCIAS.csv", "MATRIZ_CAPACIDADES.csv")
SCHEMA = "tapi-a11-architecture-frontier.v1"


class FrontierInvalid(ValueError):
    """Fail closed on inconsistent planning inputs, without exposing file data."""


def _read(path: Path, required: set[str]):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or not required <= set(reader.fieldnames):
                raise FrontierInvalid("FRONTIER_SCHEMA_INVALID")
            rows = list(reader)
            if not rows or any(None in row for row in rows):
                raise FrontierInvalid("FRONTIER_SCHEMA_INVALID")
            return rows
    except (OSError, UnicodeError, csv.Error):
        raise FrontierInvalid("FRONTIER_INPUT_UNREADABLE") from None


def analyze(plan_dir: Path) -> dict:
    """Rank task dependencies and workstream parallelism, never task completion."""
    root = Path(plan_dir)
    tasks = _read(root / FILES[0], {"id", "dependencies", "hours_estimate", "workstream", "capability_ids"})
    links = _read(root / FILES[1], {"predecessor", "successor", "type"})
    caps = _read(root / FILES[2], {"feature_id"})
    indexed = {r["id"]: r for r in tasks}
    cap_ids = {r["feature_id"] for r in caps}
    if (len(indexed) != len(tasks) or len(cap_ids) != len(caps)
            or "IMP-131" not in indexed
            or any(not k.startswith("IMP-") for k in indexed)
            or any(not k.startswith("CAP-") for k in cap_ids)):
        raise FrontierInvalid("FRONTIER_IDENTITIES_INVALID")
    hours = {}
    for key, row in indexed.items():
        try:
            parsed = int(row["hours_estimate"])
        except (ValueError, TypeError):
            raise FrontierInvalid("FRONTIER_ESTIMATE_INVALID") from None
        if parsed <= 0 or any(c not in cap_ids for c in row["capability_ids"].split(";") if c):
            raise FrontierInvalid("FRONTIER_ESTIMATE_OR_CAPABILITY_INVALID")
        hours[key] = parsed

    predecessors = {key: set() for key in indexed}
    successors = {key: set() for key in indexed}
    edges = set()
    for edge in links:
        before, after = edge["predecessor"], edge["successor"]
        if (edge["type"] != "bloqueante" or before not in indexed
                or after not in indexed or before == after or (before, after) in edges):
            raise FrontierInvalid("FRONTIER_DEPENDENCY_INVALID")
        edges.add((before, after))
        predecessors[after].add(before)
        successors[before].add(after)
    declared = {(parent, key) for key, row in indexed.items()
                for parent in row["dependencies"].split(";") if parent}
    if declared != edges:
        raise FrontierInvalid("FRONTIER_DEPENDENCY_DRIFT")
    if {key for key in indexed if not successors[key]} != {"IMP-131"}:
        raise FrontierInvalid("FRONTIER_RELEASE_SINK_INVALID")

    pending = {key: len(value) for key, value in predecessors.items()}
    ready = [key for key, count in pending.items() if count == 0]
    heapq.heapify(ready)
    order, level = [], {key: 0 for key in indexed}
    while ready:
        key = heapq.heappop(ready)
        order.append(key)
        for next_key in sorted(successors[key]):
            level[next_key] = max(level[next_key], level[key] + 1)
            pending[next_key] -= 1
            if pending[next_key] == 0:
                heapq.heappush(ready, next_key)
    if len(order) != len(indexed):
        raise FrontierInvalid("FRONTIER_DAG_CYCLE")

    longest, next_on_path, descendants = {}, {}, {}
    for key in reversed(order):
        children = successors[key]
        descendants[key] = set(children)
        for child in children:
            descendants[key].update(descendants[child])
        best = max(sorted(children), key=lambda x: (longest[x], x), default=None)
        next_on_path[key] = best
        longest[key] = hours[key] + (longest[best] if best else 0)
    roots = sorted(key for key in indexed if not predecessors[key])
    head = max(roots, key=lambda key: (longest[key], key))
    chain = []
    while head is not None:
        chain.append(head)
        head = next_on_path[head]

    lanes = {}
    for key in order:
        lane = indexed[key]["workstream"] or "sem_workstream"
        lanes.setdefault(lane, []).append(key)
    lane_summary = []
    for lane, ids in lanes.items():
        ranked = sorted(ids, key=lambda x: (-longest[x], -len(descendants[x]), x))
        lane_summary.append({"workstream": lane, "tasks": len(ids),
                             "representative_critical_tasks": ranked[:3]})
    lane_summary.sort(key=lambda x: (-len(x["representative_critical_tasks"]), -x["tasks"], x["workstream"]))

    digests = {name: sha256((root / name).read_bytes()).hexdigest() for name in FILES}
    return {"schema_version": SCHEMA, "status": "PLANNING_FRONTIER_ONLY",
            "completion_claimed": False, "gates_released": False,
            "production_approved": False, "scientific_admissions_claimed": 0,
            "task_count": len(indexed), "capability_count": len(cap_ids),
            "dependency_count": len(edges), "baseline_estimated_work_hours_sum": sum(hours.values()),
            "longest_dependency_chain_estimated_hours": longest[chain[0]],
            "longest_dependency_chain": chain, "initial_graph_roots": roots,
            "dag_layers": max(level.values()) + 1,
            "parallel_lanes": lane_summary, "source_sha256": digests,
            "interpretation": "historical estimates and dependencies only; no current task has been certified complete"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline v6.1 planning frontier; never an approval")
    parser.add_argument("--plan-dir", type=Path, default=PLAN)
    args = parser.parse_args(argv)
    try:
        report = analyze(args.plan_dir)
    except FrontierInvalid as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "production_approved": False}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
