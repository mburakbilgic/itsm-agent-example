# CoreDNS and DNS Resolution Failures

## Symptoms
- Application errors like `dial tcp: lookup <host> on 10.96.0.10:53: read udp i/o timeout`.
- Intermittent failures to a specific external domain while internal service-to-service traffic is fine.
- Calling the external API by IP works, by hostname fails.
- CoreDNS logs `plugin/errors: forward .: i/o timeout`.

## Likely Causes
- CoreDNS upstream forwarder (e.g., `8.8.8.8` or VPC resolver) is unreachable or rate-limiting.
- CoreDNS pod restarted with stale config or one replica unhealthy while still in service endpoints.
- conntrack table on a node is full, dropping UDP DNS responses.
- A `NetworkPolicy` blocks egress to the resolver after a recent change.

## Diagnostic Steps
1. From a debug pod: `dig @10.96.0.10 api.processor.example` and from each node: `dig @<upstream>`.
2. `kubectl logs -n kube-system -l k8s-app=kube-dns` — look for forwarder timeouts.
3. Check `nf_conntrack_count` vs `nf_conntrack_max` on nodes.
4. Test from the node host (bypassing CoreDNS) to isolate cluster vs. upstream issue.

## Mitigation
- Restart CoreDNS pods: `kubectl -n kube-system rollout restart deploy/coredns`.
- Temporarily switch the upstream forwarder to a known-good resolver.
- For an unblocking workaround, pin the failing host to its IP in the application config.

## Long-term Fix
- Enable CoreDNS metrics and alert on forward error rate.
- Use NodeLocal DNSCache to reduce conntrack pressure and improve reliability.
- Add multiple upstream resolvers in CoreDNS forward config.
- Add a synthetic check that resolves critical external hostnames every minute.
