# Root-Cause Failure Attribution Engine

## 1. The Attribution Problem

In traditional multi-dimensional chaos testing, if any SLA fails (e.g. HTTP 500 or timeout), standard optimization routines assume the container was starved of RAM and reduce memory stress:
$$67\text{M} \to 34\text{M} \to 17\text{M} \to 1\text{M}$$

**The Flaw**: Lowering memory stress cannot fix a severed network connection or an overloaded CPU thread pool. If an HTTP request timed out because network packet loss was 10%, penalizing container RAM down to 1MB produces inaccurate right-sizing recommendations.

---

## 2. Root-Cause Attribution Logic

The attribution function `attribute_failure_cause()` inspects k6 load telemetry and Prometheus container metrics to determine the exact failure dimension:

```text
Trial Execution Metrics
         |
         +---> Pod crashed with OOMKilled?
         |        YES ===> Culprit: RAM
         |
         +---> Error Rate > 1.0%?
         |        YES ===> Culprit: LOSS
         |
         +---> P95 Latency > 1000ms (or Timeout)?
         |        YES ===> Culprit: DELAY
         |
         +---> Container CPU Throttled?
         |        YES ===> Culprit: CPU
         |
         +---> Otherwise ===> General RAM Degradation
```

### Python Implementation (`binary_search_service.py`):
```python
def attribute_failure_cause(k6_result, metrics=None, max_error_rate_percent=1.0, max_p95_ms=1000.0):
    if metrics and metrics.get("oom_killed"):
        return "RAM", "Container crashed with OOMKilled."

    if not k6_result or k6_result.get("status") == "failed":
        reason = k6_result.get("reason", "k6 execution failed.") if k6_result else "No telemetry."
        if "timeout" in str(reason).lower() or "deadline" in str(reason).lower():
            return "DELAY", f"Latency timeout failure: {reason}"
        return "LOSS", f"Request execution failure: {reason}"

    error_rate = k6_result.get("error_rate_percent", 0.0)
    p95_latency = k6_result.get("p95_ms", 0.0)

    if error_rate > max_error_rate_percent:
        return "LOSS", f"Error rate {error_rate:.2f}% breached threshold ({max_error_rate_percent}%)."

    if p95_latency > max_p95_ms:
        return "DELAY", f"P95 latency {p95_latency:.1f}ms breached threshold ({max_p95_ms}ms)."

    if metrics and metrics.get("cpu_throttled"):
        return "CPU", "Severe CPU throttling detected."

    return "RAM", "General performance degradation."
```

---

## 3. Benefits of Attribution

1. **Independent Bound Convergence**: Network bottlenecks contract network bounds, leaving RAM tolerance calculations untouched.
2. **Accurate Right-Sizing**: Prevents under-allocating memory to a service whose actual bottleneck was an upstream network dependency.
3. **Transparent SRE Telemetry**: The UI displays the exact culprit on trial cards: `[BREACH: LOSS]`, `[BREACH: RAM]`, `[BREACH: DELAY]`, or `[BREACH: CPU]`.
