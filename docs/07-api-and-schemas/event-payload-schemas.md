# Event Payload Schemas

Specification of all JSON payloads transmitted across the Server-Sent Events (`EventSource`) stream.

---

## 1. `discovery`
Emitted once manifest discovery parses all services in the repository.
```json
{
  "total": 11,
  "services": [
    {
      "name": "cartservice",
      "kind": "Deployment",
      "namespace": "default"
    },
    {
      "name": "productcatalogservice",
      "kind": "Deployment",
      "namespace": "default"
    }
  ]
}
```

---

## 2. `service_start`
Emitted when the pipeline advances to evaluate a specific microservice.
```json
{
  "service": "cartservice",
  "index": 1,
  "total": 11
}
```

---

## 3. `stage_update`
Emitted when a pipeline stage status changes.
```json
{
  "service": "cartservice",
  "stage": "five_chaos",         // deploy | pod_kill | five_chaos | node_failure
  "status": "running",           // pending | running | completed | failed
  "iteration": 1,
  "max_iterations": 10,
  "tested_value": "64M"
}
```

---

## 4. `iteration_update`
Emitted after each binary search trial completes.
```json
{
  "service": "cartservice",
  "iteration": 2,
  "max_iterations": 10,
  "parameter": "RAM",
  "tested_value": "64M",
  "sla_passed": false,
  "reason": "Container crashed with OOMKilled.",
  "culprit": "RAM",
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

---

## 5. `service_result`
Emitted when a service completes its full lifecycle.
```json
{
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
  },
  "metrics": {
    "memory_max": 67108864,
    "cpu_max": 0.18
  }
}
```
