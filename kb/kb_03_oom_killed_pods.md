# OOMKilled Pods After Deployment

## Symptoms
- Pods reach `Running` briefly then exit with code 137.
- `kubectl describe pod` shows `Last State: Terminated, Reason: OOMKilled`.
- Application logs end with `OutOfMemoryError`, `MemoryError`, or no log at all (kernel kill).
- CrashLoopBackOff after several restart attempts.

## Likely Causes
- New release shipped a heavier dependency (model, image processing, embedded data).
- Container memory limit unchanged while baseline memory grew.
- JVM `-Xmx` configured higher than the cgroup limit.
- Memory leak that blows past the limit faster than restarts can absorb.

## Diagnostic Steps
1. `kubectl describe pod <name>` — confirm `OOMKilled` and current `resources.limits.memory`.
2. Compare the container image diff between the failing release and the previous one (`docker history`, image size).
3. If a JVM, dump heap with `jcmd <pid> GC.heap_dump` or run with `-XX:+HeapDumpOnOutOfMemoryError`.
4. Check `container_memory_working_set_bytes` over time to distinguish a sudden ramp from a slow leak.

## Mitigation
- Roll back to the previous release: `helm rollback <release> <prev_revision>` or `kubectl rollout undo`.
- If rollback is not viable, raise the memory limit temporarily to stabilize while investigating.

## Long-term Fix
- Add a startup memory benchmark to CI that fails on regressions over a threshold.
- Right-size limits with VPA recommendations.
- For JVMs, set `-XX:MaxRAMPercentage` instead of a fixed `-Xmx`.
- Ensure new dependencies that load models/data are reviewed for memory cost.
