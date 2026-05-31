# Pointing the connector at Epic's sandbox (SMART Backend Services)

The code is ready: `epic_demo.py` runs the same `smart_backend.py` client that's verified end to end against the SMART reference sandbox. Only the registered client_id and the base URL differ. The remaining work is Epic's app registration, which is account-bound and manual (Epic's vendor gate, not a code gap).

## One-time setup
1. Generate a keypair and publish the **public** JWKS at an HTTPS URL you control (a public key is meant to be published; the private key never leaves your machine):
   ```python
   import smart_backend as sb, json, os
   os.makedirs("epic_keys", exist_ok=True)
   kp = sb.gen_keypair()
   open("epic_keys/private.pem", "w").write(kp["private_pem"])      # SECRET, git-ignored
   json.dump(kp["jwks"], open("epic_keys/jwks.json", "w"), indent=2) # host this at <YOUR_JWKS_URL>
   print("kid:", kp["kid"])
   ```
2. Go to <https://fhir.epic.com>, sign in, **Build Apps -> Create**:
   - Application Audience: **Backend Systems** (system-to-system, no user login)
   - SMART on FHIR Version: **R4**; SMART Scope Version: **v1**; FHIR ID Scheme: **Unconstrained**
   - Incoming APIs (R4): **Patient.Read, Patient.Search, Encounter.Read, Encounter.Search**. Outgoing APIs: none.
3. **JWK Set URL** (Epic fetches your public key from a URL; it is not a file upload):
   - Non-Production JWK Set URL: `<YOUR_JWKS_URL>` (e.g. `https://your-domain.example/jwks.json`)
   - Production JWK Set URL: a separate key/URL when you actually go live.
4. Required text: a short Summary + Description (read-only operations layer, no clinical decisions), Intended Purposes = Administrative Tasks, Intended Users = Healthcare Administration/Executive.
5. Save. Epic assigns a **Non-Production Client ID**. Copy it.
6. **Wait for activation.** Epic can take up to ~60 minutes to fetch and activate the JWKS for non-production. Token requests fail until then. That is expected, not a bug.

## Run it
```bash
python epic_demo.py --client-id <YOUR_NON_PRODUCTION_CLIENT_ID>
```
Expected: discovery -> token exchange -> read of an Epic sandbox test patient -> `EPIC_BACKEND_OK`.

Endpoints (Epic sandbox, R4):
- FHIR base: `https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4`
- Token endpoint: discovered automatically from the base's `.well-known/smart-configuration`.

## Claim discipline
- Allowed once it works: **"validated against Epic's public sandbox via SMART Backend Services."**
- Not allowed: "we integrate with Epic." That means production access at a real health system, which requires a client sponsor and Epic's production review.

The handshake is the engineering skill, and it is the same one verified against the SMART reference sandbox. This step is gated by Epic's vendor process and a key-activation delay, by design. Only the client_id and base URL change.
