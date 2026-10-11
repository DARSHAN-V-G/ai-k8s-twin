# Service Level Agreement (SLA) Criteria

To determine whether a binary search trial passed or breached, `evaluate_sla()` enforces strict quantitative thresholds:

---

## 1. SLA Threshold Matrix

| Metric | Pass Threshold | Breach Condition | Attributed Culprit |
| :--- | :---: | :---: | :---: |
| **Error Rate** | $\le 1.0\%$ | $> 1.0\%$ | **LOSS** |
| **P95 Latency** | $\le 1000\text{ms}$ | $> 1000\text{ms}$ | **DELAY** |
| **Container State** | No Crash | `OOMKilled == true` | **RAM** |
| **CPU Saturation** | Stable | `cpu_throttled == true` | **CPU** |

---

## 2. Evaluation Logic (`binary_search_service.py`)

```python
def evaluate_sla(k6_result, metrics=None, max_error_rate_percent=1.0, max_p95_ms=1000.0):
    if metrics and metrics.get("oom_killed"):
        return False, "Container crashed with OOMKilled."

    if not k6_result:
        return False, "No k6 test telemetry received."

    if k6_result.get("status") == "failed":
        return False, f"Load test execution failed: {k6_result.get('reason', 'Unknown error')}"

    error_rate = k6_result.get("error_rate_percent", 0.0)
    p95_latency = k6_result.get("p95_ms", 0.0)

    if error_rate > max_error_rate_percent:
        return False, f"Error rate {error_rate:.2f}% breached threshold ({max_error_rate_percent}%)."

    if p95_latency > max_p95_ms:
        return False, f"P95 latency {p95_latency:.1f}ms breached threshold ({max_p95_ms}ms)."

    return True, f"SLA satisfied (Error rate: {error_rate:.2f}%, P95: {p95_latency:.1f}ms)."
```
