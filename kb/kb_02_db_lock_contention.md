# Database Lock Contention and Deadlocks

## Symptoms
- Sudden jump in p95/p99 query latency without a deployment.
- Errors like `deadlock detected`, `canceling statement due to lock_timeout`, or `still waiting for ShareLock`.
- A small number of long-running transactions visible in `pg_stat_activity` blocking many short ones.

## Likely Causes
- A bulk job (ETL, recompute, mass UPDATE) holding row or table locks.
- Long-running transaction left open by a misbehaving client (idle in transaction).
- Index missing on a foreign key column, causing parent UPDATEs to lock children.
- Hot-row contention on a frequently-updated counter.

## Diagnostic Steps
1. `SELECT * FROM pg_stat_activity WHERE state <> 'idle' ORDER BY query_start;` — find oldest queries and `wait_event`.
2. `SELECT * FROM pg_locks l JOIN pg_stat_activity a ON l.pid = a.pid WHERE NOT granted;` — find blocked sessions.
3. Identify the blocker PID and check whether it belongs to a known batch job.
4. Inspect indexes on tables with frequent UPDATE/DELETE on FK columns.

## Mitigation
- Pause or cancel the offending bulk job: `SELECT pg_cancel_backend(<pid>);`. If it does not respond, `pg_terminate_backend(<pid>)`.
- Increase `lock_timeout` only as a last resort — it hides contention rather than fixing it.

## Long-term Fix
- Schedule heavy batch jobs outside of business hours and chunk them.
- Add the missing index on FK columns.
- Ensure application clients close transactions promptly; alert on `idle in transaction` > N seconds.
- Use `SELECT ... FOR UPDATE SKIP LOCKED` for queue-style workloads.
