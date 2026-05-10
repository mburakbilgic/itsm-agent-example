# Deployment Rollout Failures

## Symptoms
- New release pods crash during startup or fail readiness checks.
- Helm release status `failed` or stuck `pending-upgrade`.
- Mixed traffic during the rollout: a percentage of requests hit the bad new version.
- Old version still healthy and serving traffic.

## Likely Causes
- New image bundles a heavier dependency that pushes startup memory above the limit (OOMKilled at start).
- Schema migration ran ahead of the application code change but is incompatible with the old code (or vice versa).
- Configuration map/secret missing a key referenced by the new code.
- Readiness probe is too strict for the new version's slower startup.

## Diagnostic Steps
1. `kubectl rollout status deploy/<name>` — confirm rollout progress.
2. `kubectl describe pod <name>` and `kubectl logs <name> --previous` — read the actual failure.
3. Compare image SBOM between current and previous release for newly-added dependencies.
4. Check that all referenced ConfigMap/Secret keys exist.

## Mitigation
- Roll back: `helm rollback <release> <prev_revision>` or `kubectl rollout undo deploy/<name>`.
- If a migration ran and is incompatible with the old code, you may need a forward-fix instead of rollback. Decide based on whether the migration is reversible.

## Long-term Fix
- Adopt expand/contract migrations: schema changes are always backward-compatible with the previous version of the code.
- Use canary or blue/green deploys with automated abort on error budget burn.
- Run startup smoke tests against the new image in CI before rollout.
- Treat the readiness probe budget as part of the deploy contract; tune it deliberately, not reactively.
