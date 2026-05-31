"""
End-to-end Rung 1 demo: read FHIR R4 from a local HAPI sandbox, compute
retention scoring, print a follow-up-priority table.

Usage:
    python demo.py --base http://localhost:8080/fhir
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from connector import FhirConfig, FhirR4Connector
from retention_scoring import score_patients


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080/fhir", help="FHIR base URL")
    ap.add_argument("--recall-window-days", type=int, default=365)
    ap.add_argument("--top", type=int, default=20, help="how many rows to print")
    ap.add_argument("--tag", default=None, help="_tag filter (system|code) to scope reads on a shared server")
    ap.add_argument("--js", default=None, help="write scored items to a JS file (window.FHIR_FOLLOWUP) for the UI")
    args = ap.parse_args()

    cfg = FhirConfig(base_url=args.base, tag=args.tag)
    fhir = FhirR4Connector(cfg)

    print(f"Reading patients from {args.base} ...")
    patients = list(fhir.import_patients())
    print(f"  -> {len(patients)} patients")

    print("Reading encounters ...")
    encounters_by_patient: dict[str, list[dict]] = defaultdict(list)
    total_encs = 0
    for e in fhir.import_treatments():
        if e["patient_key"]:
            encounters_by_patient[e["patient_key"]].append(e)
            total_encs += 1
    print(f"  -> {total_encs} encounters across {len(encounters_by_patient)} patients")

    print("Scoring retention ...")
    items = score_patients(
        patients,
        encounters_by_patient,
        recall_window_days=args.recall_window_days,
    )

    needs = [i for i in items if i.bucket == "Needs call this week"]
    soft  = [i for i in items if i.bucket == "Soft touch"]
    none_ = len(items) - len(needs) - len(soft)
    print(f"  -> {len(needs)} need a call, {len(soft)} soft touch, {none_} no action")

    if args.js:
        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        payload = {
            "source": f"FHIR R4 via REST ({args.base})",
            "scoped_by_tag": args.tag,
            "generated_at": _dt.now(_tz.utc).isoformat(),
            "recall_window_days": args.recall_window_days,
            "counts": {"needs_call": len(needs), "soft_touch": len(soft), "no_action": none_},
            "items": [
                {
                    "patient_name": it.patient_name,
                    "patient_id": it.patient_id,
                    "bucket": it.bucket,
                    "days_since_last_encounter": it.days_since_last_encounter,
                    "personal_cadence_days": it.personal_cadence_days,
                    "score": it.score,
                    "explanation": it.explanation,
                }
                for it in items
            ],
        }
        with open(args.js, "w", encoding="utf-8") as f:
            f.write("window.FHIR_FOLLOWUP = " + _json.dumps(payload, indent=2) + ";\n")
        print(f"  -> wrote {args.js}")

    print("\nTop follow-up priorities:")
    header = f"{'PATIENT':<28} {'BUCKET':<22} {'DAYS':>6} {'SCORE':>6}  WHY"
    print(header)
    print("-" * len(header))
    for item in items[: args.top]:
        name = (item.patient_name or item.patient_id)[:27]
        days = item.days_since_last_encounter
        days_s = f"{days:>6}" if days is not None else "  None"
        print(f"{name:<28} {item.bucket:<22} {days_s} {item.score:>6.2f}  {item.explanation}")


if __name__ == "__main__":
    main()
