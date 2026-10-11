# Server-Sent Events (SSE) Streaming Protocol

The AI K8s Twin backend communicates real-time progress to frontend clients via an HTTP Server-Sent Events stream at `GET /api/environment-orchestrator/stream`.

---

## 1. Event Types

| Event Name | Purpose | When Triggered |
| :--- | :--- | :--- |
| `discovery` | Discovered microservices in the repo | Immediately after manifest parsing finishes |
| `service_start` | Lifecycle begins for a specific microservice | At start of service deployment |
| `stage_update` | Progression through `deploy`, `pod_kill`, `five_chaos`, `node_failure` | On entry and exit of each stage |
| `iteration_update` | Results and decisions of a binary search trial | After each trial finishes evaluation |
| `service_log` | Diagnostic log lines from kubectl, k6, or prometheus | Continuously during execution |
| `service_result` | Final converged tolerances and sizing recommendations | After service teardown |
| `aggregate_complete`| Entire workload evaluation finished across all services | When the last service completes |
| `error` | Fatal orchestration failure or cluster error | On uncaught exception |

---

## 2. Event Payload Examples

### `iteration_update`
```json
event: iteration_update
data: {
  "service": "cartservice",
  "iteration": 2,
  "max_iterations": 10,
  "parameter": "RAM",
  "tested_value": "64M",
  "sla_passed": false,
  "culprit": "RAM",
  "reason": "Container crashed with OOMKilled.",
  "step_taken": "Contracted RAM Upper Bound: [1M, 128M] -> [1M, 64M] (Container crashed with OOMKilled.). Other dimensions held steady.",
  "vector": {"RAM": 64, "CPU": 55, "DELAY": 755, "LOSS": 7.8},
  "chaos_vector": {"memory": "64M", "cpu": "55%", "delay": "755ms", "loss": "7.8%", "partition": "recommendationservice"},
  "parameters_state": {
    "RAM": {"low": 1, "high": 64, "unit": "M", "diff": 63, "converged": false, "best_safe": 1},
    "CPU": {"low": 10, "high": 100, "unit": "%", "diff": 90, "converged": false, "best_safe": 10},
    "DELAY": {"low": 10, "high": 1500, "unit": "ms", "diff": 1490, "converged": false, "best_safe": 10},
    "LOSS": {"low": 0.5, "high": 15.0, "unit": "%", "diff": 14.5, "converged": false, "best_safe": 0.5}
  },
  "next_midpoint": "32M",
  "converged": false
}
```

### `service_result`
```json
event: service_result
data: {
  "service": "cartservice",
  "status": "passed",
  "optimization": {
    "sla_passed": true,
    "sla_verdict": "Optimal safe tolerances: RAM=64M, CPU=75%, DELAY=350ms, LOSS=4.2% (Converged in 4 iterations)",
    "recommended_config": {
      "memory_limit": "144Mi",
      "memory_request": "64Mi",
      "cpu_limit": "250m",
      "cpu_request": "100m"
    },
    "optimal_values": {
      "RAM": "64M",
      "CPU": "75%",
      "DELAY": "350ms",
      "LOSS": "4.2%"
    }
  }
}
```
