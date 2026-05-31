"""
Rung 2 live demo: full SMART Backend Services handshake against the SMART
Bulk Data reference sandbox (bulk-data.smarthealthit.org).

Flow (no human, no browser):
  1. generate an RSA keypair
  2. discover .well-known/smart-configuration -> token + registration endpoints
  3. dynamically register our JWKS -> client_id
  4. sign a JWT client assertion, exchange it for an access_token
  5. call the FHIR API with the Bearer token

This is the same SmartBackendClient that will point at Epic's backend sandbox
in Rung 3, only the registered client_id + base URL change.

Usage:
    python smart_demo.py
"""

from __future__ import annotations

import argparse
import json

import requests

import smart_backend as sb

DEFAULT_BASE = "https://bulk-data.smarthealthit.org/fhir"


def register(reg_endpoint: str, jwks: dict) -> str:
    """Register our public JWKS with the sandbox; returns a client_id.
    The SMART Bulk Data server accepts a form POST with the stringified JWKS."""
    r = requests.post(reg_endpoint, data={"jwks": json.dumps(jwks)}, timeout=30)
    print(f"  register -> HTTP {r.status_code}: {r.text[:160]}")
    r.raise_for_status()
    ct = r.headers.get("content-type", "")
    if ct.startswith("application/json"):
        body = r.json()
        return body.get("client_id") or body.get("clientId") or str(body)
    return r.text.strip().strip('"')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--scope", default="system/Patient.rs")
    args = ap.parse_args()

    print("1. keypair ...")
    kp = sb.gen_keypair()
    print(f"   kid={kp['kid']}")

    print(f"2. discover {args.base} ...")
    cfg = sb.discover(args.base)
    token_ep = cfg["token_endpoint"]
    reg_ep = cfg.get("registration_endpoint")
    print(f"   token_endpoint={token_ep}")
    print(f"   registration_endpoint={reg_ep}")
    if not reg_ep:
        print("   no dynamic registration; this server needs manual client registration.")
        return

    print("3. register JWKS ...")
    client_id = register(reg_ep, kp["jwks"])
    print(f"   client_id={str(client_id)[:48]}...")

    print(f"4. token exchange (scope={args.scope}) ...")
    client = sb.SmartBackendClient(
        args.base, client_id, kp["private_pem"], kp["kid"],
        scope=args.scope, token_endpoint=token_ep,
    )
    tok = client.access_token()
    print(f"   access_token={tok[:28]}... (len {len(tok)})")

    # bulk-data.smarthealthit.org is a Bulk Data server: its protected, scoped
    # operation is system-level $export, not interactive Patient search (that
    # 404s here). The token's real test is whether it authorizes $export.
    # (SmartBackendClient.get() stays generic for interactive servers like Epic.)
    print("5. authenticated, scoped operation (system $export kickoff) ...")
    exp_url = args.base.rstrip("/") + "/$export"
    r = requests.get(
        exp_url, params={"_type": "Patient"},
        headers={"Accept": "application/fhir+json", "Prefer": "respond-async",
                 "Authorization": "Bearer " + client.access_token()},
        timeout=30,
    )
    print(f"   $export -> HTTP {r.status_code}")
    if r.status_code == 202:
        print(f"   Content-Location (async job): {r.headers.get('Content-Location', '(none)')}")
        print("   token authorized a scoped bulk export.")
        print("BACKEND_SERVICES_OK")
    elif r.status_code == 401:
        print("   401 Unauthorized - the access token was REJECTED. AUTH FAILED.")
    else:
        print(f"   unexpected {r.status_code}: {r.text[:200]}")


if __name__ == "__main__":
    main()
