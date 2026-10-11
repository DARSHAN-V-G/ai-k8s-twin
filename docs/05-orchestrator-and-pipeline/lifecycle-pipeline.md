# Lifecycle Pipeline

The **Environment Orchestrator** executes workloads sequentially microservice by microservice to avoid cross-workload interference.

---

## 1. Pipeline Stages

```text
+---------------------------------------------------------------------------------+
|                                 DISCOVERY                                       |
|  - Clone Git Repository -> Parse Multi-Document Manifests -> Discover Services  |
+---------------------------------------------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                        SERVICE N LIFECYCLE (e.g. cartservice)                   |
|                                                                                 |
|  [DEPLOY WORKLOAD ONCE] -> Wait for Pod Readiness & Service Ports               |
|                                                                                 |
|  [STAGE 1: POD KILL]    -> Kill pod -> Check self-healing recovery              |
|                                                                                 |
|  [STAGE 2: 5-CHAOS]     -> Multi-Param Binary Search Loop (Trials 1..Converged) |
|                            In-place swap of RAM, CPU, Delay, Loss, Partition    |
|                                                                                 |
|  [STAGE 3: NODE FAIL]   -> Simulate worker node crash -> Check scheduling       |
|                                                                                 |
|  [RIGHT-SIZING]         -> Calculate Requests & Limits (+25% buffer)            |
|                                                                                 |
|  [TEARDOWN]             -> Delete Chaos CRDs & Workload Deployment              |
+---------------------------------------------------------------------------------+
                                         |
                                         v
                            Advance to Service N + 1
```

---

## 2. Service-Wise Isolation Guarantee

1. **Port-Forwarding Isolation**: During each service's active run, only that service's ports and k6 load tests are bound.
2. **Cluster Cleanliness**: After a service finishes Stage 3, all injected Chaos Mesh CRDs and application deployments are completely purged before the next service starts.
3. **Reproducibility**: Experiments run in clean state without lingering cgroup limits or modified `iptables` rules.
