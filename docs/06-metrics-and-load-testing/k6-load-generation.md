# k6 Load Generation

Load generation tests whether services handle traffic under concurrent chaos stress.

---

## 1. In-Cluster Execution Architecture

Rather than driving load from an external host through port-forward proxies (which can suffer connection limits and NAT bottlenecks), the orchestrator executes k6 directly inside the Kubernetes cluster via a dedicated runner pod:

```yaml
# backend/k6-runner.yaml
apiVersion: v1
kind: Pod
metadata:
  name: k6-runner
  namespace: simulation-resource
spec:
  restartPolicy: Never
  containers:
    - name: k6
      image: grafana/k6:latest
      command: ["k6", "run", "/scripts/test.js"]
```

---

## 2. Load Parameters

- **Virtual Users (VUs)**: Concurrent user simulation threads (e.g. `10` to `50` VUs).
- **Duration**: Duration of constant load application matching the chaos window (e.g. `15s` to `30s`).

---

## 3. Collected Telemetry

At the conclusion of each trial, k6 outputs:
- **`total_requests`**: Total HTTP/gRPC requests dispatched.
- **`failed_requests`**: Requests returning non-2xx responses or connection timeouts.
- **`error_rate_percent`**:
  $$\text{Error Rate} = \frac{\text{Failed Requests}}{\text{Total Requests}} \times 100$$
- **`p95_ms`**: 95th percentile transaction latency in milliseconds.
- **`p99_ms`**: 99th percentile transaction latency in milliseconds.
