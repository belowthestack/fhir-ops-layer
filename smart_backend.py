"""
ARFA AOL — SMART Backend Services client (Rung 2).

Implements the SMART App Launch "Backend Services" (system-to-system) auth
handshake: the OAuth2 client-credentials grant with a signed JWT client
assertion. This is the correct flow for an UNATTENDED ops layer (no user
login), and it's standards-defined, so the same client works against the SMART
Health IT sandbox, Epic's backend sandbox, Cerner, etc. Only the registered
client_id + token endpoint change.

Spec: https://hl7.org/fhir/smart-app-launch/backend-services.html

This module is the portable, reusable skill. It needs NO network for its core
correctness (`python smart_backend.py` runs a self-test: keygen -> signed
assertion -> local verify). The live token exchange needs a client_id
registered on the target server (see smart_demo.py).
"""

from __future__ import annotations

import json
import time
import uuid

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def gen_keypair(kid: str | None = None) -> dict:
    """Generate an RSA keypair. Returns the private PEM (keep secret) and the
    public key as a JWK + a one-key JWKS (register this with the server)."""
    kid = kid or uuid.uuid4().hex[:12]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    pub_jwk.update({"kid": kid, "alg": "RS384", "use": "sig", "key_ops": ["verify"]})
    return {"kid": kid, "private_pem": priv_pem, "public_jwk": pub_jwk, "jwks": {"keys": [pub_jwk]}}


def discover(fhir_base: str, timeout: int = 30) -> dict:
    """Fetch the server's SMART configuration (.well-known/smart-configuration),
    which advertises the token_endpoint, supported grant types, scopes, etc."""
    url = fhir_base.rstrip("/") + "/.well-known/smart-configuration"
    r = requests.get(url, headers={"Accept": "application/json"}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def make_client_assertion(client_id: str, token_endpoint: str, private_pem: str,
                          kid: str, ttl: int = 300) -> str:
    """Build the signed JWT client assertion per the Backend Services spec:
    iss == sub == client_id, aud == token_endpoint, short-lived, unique jti."""
    now = int(time.time())
    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": token_endpoint,
        "exp": now + ttl,
        "iat": now,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, private_pem, algorithm="RS384", headers={"kid": kid, "typ": "JWT"})


def get_token(token_endpoint: str, assertion: str, scope: str = "system/*.read",
              timeout: int = 30) -> dict:
    """Exchange the signed assertion for an access token (client-credentials)."""
    data = {
        "grant_type": "client_credentials",
        "client_assertion_type": ASSERTION_TYPE,
        "client_assertion": assertion,
        "scope": scope,
    }
    r = requests.post(
        token_endpoint, data=data,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    ctype = r.headers.get("content-type", "")
    return {"ok": r.ok, "status": r.status_code,
            "body": (r.json() if ctype.startswith("application/json") else r.text[:500])}


def verify_assertion(assertion: str, public_jwk: dict, audience: str) -> dict:
    """Local signature + claim verification (used by the self-test and to prove
    correctness without a network round-trip)."""
    key = RSAAlgorithm.from_jwk(json.dumps(public_jwk))
    return jwt.decode(assertion, key=key, algorithms=["RS384"], audience=audience)


class SmartBackendClient:
    """Ties it together: hold a keypair + a registered client_id, fetch tokens
    (cached until near expiry), and make authenticated FHIR calls."""

    def __init__(self, fhir_base: str, client_id: str, private_pem: str, kid: str,
                 scope: str = "system/*.read", token_endpoint: str | None = None):
        self.fhir_base = fhir_base.rstrip("/")
        self.client_id = client_id
        self.private_pem = private_pem
        self.kid = kid
        self.scope = scope
        self._token_endpoint = token_endpoint
        self._token = None
        self._token_exp = 0

    def token_endpoint(self) -> str:
        if not self._token_endpoint:
            self._token_endpoint = discover(self.fhir_base)["token_endpoint"]
        return self._token_endpoint

    def access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        te = self.token_endpoint()
        assertion = make_client_assertion(self.client_id, te, self.private_pem, self.kid)
        res = get_token(te, assertion, self.scope)
        if not res["ok"] or not isinstance(res["body"], dict) or "access_token" not in res["body"]:
            raise RuntimeError(f"token request failed: {res['status']} {res['body']}")
        self._token = res["body"]["access_token"]
        self._token_exp = time.time() + int(res["body"].get("expires_in", 300))
        return self._token

    def get(self, path: str, params: dict | None = None) -> dict:
        url = self.fhir_base + "/" + path.lstrip("/")
        r = requests.get(url, params=params or {},
                         headers={"Accept": "application/fhir+json",
                                  "Authorization": "Bearer " + self.access_token()},
                         timeout=30)
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    # Network-free correctness self-test: keygen -> sign assertion -> verify.
    kp = gen_keypair()
    aud = "https://example.org/oauth/token"
    assertion = make_client_assertion("demo-client-id", aud, kp["private_pem"], kp["kid"])
    decoded = verify_assertion(assertion, kp["public_jwk"], audience=aud)
    print("keypair kid     :", kp["kid"])
    print("JWKS (register) :", json.dumps(kp["jwks"])[:90], "...")
    print("assertion (head):", assertion[:48], "...")
    print("verified locally: iss=%s aud=%s exp_in=%ss" % (
        decoded["iss"], decoded["aud"], decoded["exp"] - int(time.time())))
    assert decoded["iss"] == decoded["sub"] == "demo-client-id"
    assert decoded["aud"] == aud
    print("SELFTEST_OK")
