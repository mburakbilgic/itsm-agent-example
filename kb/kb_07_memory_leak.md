# Memory Leaks in Long-running Services

## Symptoms
- Resident memory grows linearly with uptime, independent of traffic.
- Pods get OOMKilled at predictable intervals (e.g., every 24-48 hours).
- `container_memory_working_set_bytes` is monotonically non-decreasing.
- Restart "fixes" the issue temporarily.

## Likely Causes
- In-memory cache without an eviction policy (no max size, no TTL).
- Listener / event-handler leak: registrations not removed on cleanup.
- Native memory leak in a C extension (Python `ctypes`, JNI in Java).
- Object pool that grows but never shrinks.

## Diagnostic Steps
1. Take heap snapshots at intervals and diff (`jmap`, `py-spy dump`, Node `--inspect`, Go `pprof heap`).
2. Look for objects whose count grows over time — typical suspects are cache entries, sessions, listener lists.
3. For native leaks, watch RSS while heap is stable: that gap indicates non-managed memory.
4. Correlate growth with traffic patterns; constant growth even at zero RPS implies a non-traffic source.

## Mitigation
- Restart the service to reclaim memory (buys time, not a fix).
- Disable the leaking feature behind a flag if available.

## Long-term Fix
- Replace ad-hoc caches with a proper LRU/LFU implementation with bounded size.
- Add a unit/integration test that runs a long workload and asserts memory stays bounded.
- Add a memory-usage SLO and alert on growth rate, not just absolute usage.
- For language-runtime leaks, profile in CI on every PR using a representative workload.
