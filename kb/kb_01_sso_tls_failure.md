# SSO and TLS Handshake Failures

## Symptoms
- Users see HTTP 500 or redirect loops on the SSO callback path.
- Service logs show `x509: certificate signed by unknown authority` or `TLS handshake timeout`.
- JWKS endpoint returns 502 or 504 from the relying party.

## Likely Causes
- Renewed certificate is missing the intermediate CA in its chain.
- Trust store on the client (relying party) is outdated and does not contain the new CA.
- Clock skew between IdP and relying party greater than the token leeway.
- Old certificate cached in connection pools after rotation.

## Diagnostic Steps
1. From the relying party host, run `openssl s_client -connect idp.example:443 -showcerts` and inspect the chain. A short chain (only a leaf) indicates a missing intermediate.
2. Compare the `Issuer` of the leaf certificate against the issuers in the OS / app trust store.
3. Check `date` / NTP sync on both sides.
4. Compare the `kid` in the JWT header with the `kid` values returned by the JWKS endpoint.

## Mitigation
- Re-deploy the IdP edge with the full bundle (`fullchain.pem`, not `cert.pem`).
- Bounce the relying party to flush cached TLS sessions.
- If urgent and safe, temporarily pin the previous CA in the relying party trust store while the chain is fixed.

## Long-term Fix
- Add automated chain-validation tests to the certificate renewal pipeline.
- Add a synthetic monitor that fetches the JWKS endpoint and validates the chain end-to-end.
- Standardize on `fullchain.pem` deployment to avoid bundle-vs-leaf mistakes.
