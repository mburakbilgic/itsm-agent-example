# Disk Pressure on Kubernetes Nodes

## Symptoms
- Node condition `DiskPressure: True`.
- Pods evicted with reason `Evicted: The node was low on resource: ephemeral-storage`.
- Logs from `fluentd`, `fluent-bit`, or other forwarders complain about buffer overflow.
- `journalctl` rotates aggressively or drops messages.

## Likely Causes
- Logging aggregator buffering to local disk because a downstream sink is backpressured.
- Container image layers accumulating because GC threshold is too high.
- Application writing large temp files without cleanup.
- Core dumps from a crashing service piling up.

## Diagnostic Steps
1. SSH or `kubectl debug node/<node>` and run `du -xh / | sort -h | tail -50`.
2. Inspect `/var/log` and the container runtime overlay directory.
3. Check the logging agent's buffer directory size and queue depth.
4. Verify the kubelet image-GC thresholds: `--image-gc-high-threshold`, `--eviction-hard`.

## Mitigation
- Restart the logging aggregator after fixing the downstream sink so its on-disk buffer drains.
- Manually prune unused images: `crictl rmi --prune` or `docker image prune -af`.
- Move the logging buffer to a separate volume.

## Long-term Fix
- Alert on `DiskPressure` and on log-buffer fill ratio before eviction triggers.
- Use a separate persistent volume for log buffers, isolated from the node root disk.
- Right-size the logging downstream (Elasticsearch/Loki) so it does not backpressure for long.
- Review kubelet eviction thresholds against actual disk capacity.
