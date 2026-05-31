"""
US Core conformance pre-check demo (Rung 1, Session 2).

Reads raw FHIR resources from the server (scoped by --tag) and runs the
`us_core_check` pre-check, printing a conformance report.

NOTE: this is the in-pipeline pre-check, NOT the authoritative HL7
validator_cli / ONC Inferno validation. See us_core_check.py header.

Usage:
    python validate_demo.py --base https://hapi.fhir.org/baseR4 --tag "http://arfa-demo.test/run|aol-demo"
"""

from __future__ import annotations

import argparse
from collections import Counter

import us_core_check
from connector import FhirConfig, FhirR4Connector


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080/fhir")
    ap.add_argument("--tag", default=None, help="_tag filter (system|code) to scope reads")
    ap.add_argument("--show-issues", type=int, default=20)
    args = ap.parse_args()

    fhir = FhirR4Connector(FhirConfig(base_url=args.base, tag=args.tag))

    results = []
    for rt in ("Patient", "Encounter", "Immunization"):
        for res in fhir.read_raw(rt):
            results.append(us_core_check.validate(res))

    total = Counter(r.resource_type for r in results)
    conformant = Counter(r.resource_type for r in results if r.ok)

    print("US Core 6.1.0 conformance PRE-CHECK (not the authoritative validator):")
    if not results:
        print("  (no resources found for this tag)")
        return
    for rt in sorted(total):
        print(f"  {rt:<14} {conformant[rt]}/{total[rt]} pass")

    all_issues = [(r, i) for r in results for i in r.issues]
    errors = [x for x in all_issues if x[1].severity == "error"]
    warnings = [x for x in all_issues if x[1].severity == "warning"]
    print(f"\n  {len(errors)} errors, {len(warnings)} warnings across {len(results)} resources")
    for r, i in all_issues[: args.show_issues]:
        print(f"  [{i.severity:<7}] {r.resource_type}/{r.resource_id} {i.path}: {i.message}")
    if not all_issues:
        print("  no conformance issues found in the pre-check")


if __name__ == "__main__":
    main()
