"""
Rung 3: run the proven SMART Backend Services client against Epic's sandbox.

The code is the SAME `SmartBackendClient` that passed end-to-end against the
SMART reference sandbox in Rung 2; only the registered client_id + base URL
differ. So this file is short on purpose.

PREREQUISITE (not code, Epic's vendor gate): register a Backend app on
fhir.epic.com, upload epic_keys/jwks.json, get a Non-Production Client ID, and
wait for Epic key activation (up to ~60 min). See EPIC_SANDBOX_SETUP.md.

Usage:
    python epic_demo.py --client-id <NON_PRODUCTION_CLIENT_ID>
"""

from __future__ import annotations

import argparse
import json

import smart_backend as sb

EPIC_R4_BASE = "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"
EPIC_TEST_PATIENT = "erXuFYUfucBZaryVksYEcMg3"  # Camila Lopez (Epic sandbox test patient)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True, help="Epic Non-Production Client ID")
    ap.add_argument("--base", default=EPIC_R4_BASE)
    ap.add_argument("--scope", default="system/Patient.read")
    ap.add_argument("--patient", default=EPIC_TEST_PATIENT)
    args = ap.parse_args()

    with open("epic_keys/private.pem") as f:
        priv = f.read()
    with open("epic_keys/public_jwk.json") as f:
        kid = json.load(f)["kid"]

    print(f"1. discover {args.base} ...")
    cfg = sb.discover(args.base)
    print(f"   token_endpoint={cfg.get('token_endpoint')}")

    print(f"2. token exchange (Epic, scope={args.scope}) ...")
    client = sb.SmartBackendClient(args.base, args.client_id, priv, kid, scope=args.scope)
    tok = client.access_token()
    print(f"   access_token={tok[:24]}... (len {len(tok)})")

    print(f"3. read Patient/{args.patient} ...")
    p = client.get(f"Patient/{args.patient}")
    nm = (p.get("name") or [{}])[0]
    who = " ".join((nm.get("given") or []) + [nm.get("family", "")]).strip()
    print(f"   -> {who or p.get('id')} (gender={p.get('gender')}, dob={p.get('birthDate')})")
    print("EPIC_BACKEND_OK")


if __name__ == "__main__":
    main()
