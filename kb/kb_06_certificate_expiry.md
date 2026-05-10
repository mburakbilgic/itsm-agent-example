# TLS Certificate Expiry and Rotation Issues

## Symptoms
- Browsers display `NET::ERR_CERT_DATE_INVALID`.
- Clients log `certificate has expired or is not yet valid`.
- Sudden cliff of failed handshakes at midnight UTC.
- Internal service-to-service TLS calls fail after a known renewal window.

## Likely Causes
- Manual renewal forgotten; cert simply expired.
- cert-manager `Certificate` resource healthy but the secret was not propagated to all consuming pods (no rolling restart).
- Renewed cert installed but missing intermediate CA bundle.
- HSM/KMS-backed key signing failed silently.

## Diagnostic Steps
1. `openssl s_client -connect host:443 -servername host </dev/null | openssl x509 -noout -dates` — inspect `notBefore` / `notAfter`.
2. Check cert-manager: `kubectl get certificate -A` and `kubectl describe certificate <name>`.
3. Verify the chain length: a leaf-only response indicates a missing intermediate.
4. Compare the certificate hash served by the endpoint against the hash in the secret.

## Mitigation
- Reissue with `kubectl annotate certificate <name> cert-manager.io/issue-temporary-certificate=true` (or trigger a manual renew).
- Rolling restart of pods that mount the cert secret: `kubectl rollout restart deploy/<name>`.
- Hot-fix by uploading a known-good cert to the load balancer while the pipeline is repaired.

## Long-term Fix
- Alert at least 30 and 7 days before expiry on every cert in production.
- Automate rotation via cert-manager + ACME.
- Add a synthetic monitor that does a real TLS handshake (not just a TCP connect).
- Ensure pods that consume cert secrets restart on secret change (e.g., reloader).
