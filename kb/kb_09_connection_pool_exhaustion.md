# Connection Pool Exhaustion and Cascading Latency

## Symptoms
- Edge or load balancer returns 504 Gateway Timeout intermittently.
- API gateway / backend logs show "connection pool exhausted" or "queue full".
- A small number of slow downstream calls correlates with broad latency increases.
- CPU and memory on the backend pods look normal, but request latency is high.

## Likely Causes
- A downstream dependency became slow; upstream connections are held open and the pool fills.
- Pool size too small for the concurrency the service receives.
- No client-side timeout, so a stalled call holds a slot indefinitely.
- Retry storm amplifying the issue (every retry occupies another slot).

## Diagnostic Steps
1. Identify the slow dependency: APM trace by p99 span duration, or log-correlate slow request IDs.
2. Inspect pool metrics: in-use vs. max, queue depth, wait time. Saturation of "in-use" is the smoking gun.
3. Check whether timeouts are configured on the HTTP client to the slow dependency.
4. Look for retry policies that fire on timeout — those compound the problem.

## Mitigation
- Reduce timeout to fail fast on the slow downstream, freeing pool slots.
- Disable retries on the slow path temporarily.
- Scale out the downstream (or its connection pool) if the dependency itself is the bottleneck.

## Long-term Fix
- Set explicit, conservative timeouts on every outbound HTTP/DB call.
- Enforce circuit breakers (e.g., Resilience4j, Hystrix-style) for unreliable downstreams.
- Add saturation alerts on connection pools (>80% in-use sustained).
- Use bulkheads to isolate slow dependencies from healthy traffic.
