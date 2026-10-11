# Prometheus Telemetry

Granular resource metrics are queried from the in-cluster Prometheus instance via PromQL.

---

## 1. Monitored Metrics & PromQL Queries

### Memory Consumption
```promql
max(container_memory_working_set_bytes{container="<container_name>", namespace="simulation-resource"})
```
- Measures the working set memory (memory currently allocated that the Linux kernel cannot drop or evict).
- Used to compute baseline in-use RAM and verify if the process reached the cgroup limit before OOMKilled.

### CPU Consumption
```promql
max(rate(container_cpu_usage_seconds_total{container="<container_name>", namespace="simulation-resource"}[1m]))
```
- Measures peak rate of CPU cores utilized per second.
- Used to calculate baseline CPU requests and check for CFS CPU throttling.

---

## 2. Kernel Crash Detection

In addition to Prometheus PromQL, the orchestrator inspects the Kubernetes Pod Status:
- `containerStatuses[].lastState.terminated.reason == "OOMKilled"`
- `containerStatuses[].restartCount > previous_restart_count`

When an OOM event is detected, `metrics.oom_killed` is set to `True`, immediately informing the Failure Attribution Engine.
