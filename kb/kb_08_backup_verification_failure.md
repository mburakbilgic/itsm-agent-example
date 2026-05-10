# Backup Verification Failures

## Symptoms
- Nightly backup completes "successfully" but post-restore verification fails.
- Checksum or row-count mismatch between source and restored data.
- Storage layer reports the file is intact (ETag matches), yet contents differ logically.

## Likely Causes
- Logical dump (`pg_dump`, `mongodump`) ran without a consistent snapshot — concurrent writes were captured mid-flight.
- Partial-failure not surfaced because the orchestrator only checks process exit code.
- Storage-side issue (rare): silent corruption, but ETag mismatch would catch this.
- Schema or extension mismatch between source and restore target produced different row representations.

## Diagnostic Steps
1. Re-run verification on a different restore target to rule out target-side corruption.
2. Inspect the dump command: was it run inside a transaction snapshot (`pg_dump --serializable-deferrable`, MySQL `--single-transaction`)?
3. Check whether write traffic increased during the backup window.
4. Compare schema versions and extensions between source and restore.

## Mitigation
- Roll forward to the next successful backup if available, or trigger an immediate manual backup using a snapshot-based method.
- Quarantine the suspect backup; do not delete until investigation finishes.

## Long-term Fix
- Use storage snapshots (LVM, EBS, file-system level) to guarantee point-in-time consistency, then `pg_dump` from the snapshot.
- Make verification mandatory and gating: a backup is "successful" only after restore + checksum.
- Track and alert on backup duration and size deltas — sudden changes indicate underlying issues.
- Quarterly disaster-recovery drill that fully restores into staging.
