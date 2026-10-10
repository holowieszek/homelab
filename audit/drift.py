#!/usr/bin/env python3
"""Deterministic comparison of synthetic/reviewed desired and observed facts."""
import argparse
import json
from pathlib import Path

STATUSES = {"MATCH", "DRIFT", "REPO_ONLY", "RUNTIME_ONLY", "UNVERIFIED", "APPROVED_EXCEPTION"}


def compare(desired: dict, observed: dict, exceptions: dict | None = None) -> list[dict]:
    exceptions = exceptions or {}
    out = []
    for category, facts in desired.items():
        actual = observed.get(category)
        if actual is None:
            out.append({"category": category, "key": "*", "status": "REPO_ONLY"})
            continue
        if actual.get("collection_status") != "OK":
            out.append({"category": category, "key": "*", "status": "UNVERIFIED"})
            continue
        rows = actual.get("observed_facts", [])
        for key, expected in sorted(facts.items()):
            vals = [row.get(key) for row in rows if key in row]
            status = "MATCH" if expected in vals else ("DRIFT" if vals else "UNVERIFIED")
            out.append({"category": category, "key": key, "expected": expected, "status": status})
        for key in sorted({k for row in rows for k in row} - set(facts)):
            out.append({"category": category, "key": key, "status": "RUNTIME_ONLY"})
    for category in sorted(set(observed) - set(desired)):
        out.append({"category": category, "key": "*", "status": "RUNTIME_ONLY"})
    for row in out:
        exception = exceptions.get(row["category"] + "." + row["key"])
        if exception and row["status"] == "DRIFT":
            row["status"], row["exception"] = "APPROVED_EXCEPTION", exception
    return sorted(out, key=lambda x: (x["category"], x["key"]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("desired", type=Path)
    p.add_argument("observed", type=Path)
    p.add_argument("--exceptions", type=Path, help="Reviewed JSON map of category.key to rationale")
    a = p.parse_args()
    exceptions = json.loads(a.exceptions.read_text()) if a.exceptions else {}
    print(json.dumps(compare(json.loads(a.desired.read_text()), json.loads(a.observed.read_text()), exceptions), sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
