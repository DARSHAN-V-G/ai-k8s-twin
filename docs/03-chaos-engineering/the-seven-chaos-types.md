# The 7 Chaos Sequences

AI K8s Twin supports 7 distinct chaos experiments designed to validate container limits, network resilience, and Kubernetes cluster self-healing:

```text
+-------------------+--------------------+--------------------+--------------------+
|  POD KILL         |  CPU STRESS        |  MEMORY STRESS     |  NETWORK DELAY     |
|  (Self-Healing)   |  (Throttling)      |  (OOM Boundary)    |  (Timeouts)        |
+-------------------+--------------------+--------------------+--------------------+
|  NETWORK LOSS     |  NETWORK PARTITION |  NODE FAILURE      |                    |
|  (Retries)        |  (Degradation)     |  (Multi-Node HA)   |                    |
+-------------------+--------------------+--------------------+--------------------+
```

---

## 1. Pod Kill (`pod-kill.yaml`)
- **Mechanism**: Issues an abrupt `SIGKILL` termination to one or more pods matching the target deployment's label selector via `PodChaos`.
- **Purpose**: Validates Kubernetes self-healing. Tests whether:
  - The Deployment controller and ReplicaSet spawn a replacement pod immediately.
  - Readiness probes prevent traffic from routing to unready pods.
  - Client traffic recovers within SLA bounds without persistent downtime.

---

## 2. CPU Stress (`cpu-stress.yaml`)
- **Mechanism**: Injects high CPU stress into the target container via `StressChaos` using `stress-ng`. Stress is applied as a percentage of available CPU (from 10% to 100%).
- **Purpose**: Discovers CPU throttling limits. Tests:
  - How many concurrent requests the pod can process before CPU throttling triggers latency degradation.
  - Informs the calculation of `cpu_request` (baseline reservation) and `cpu_limit` (ceiling with +25% buffer).

---

## 3. Memory Stress (`memory-stress.yaml`)
- **Mechanism**: Injects memory pressure directly into the container cgroup via `StressChaos` using `stress-ng` (from 1MB up to container limits).
- **Purpose**: Pinpoints the exact `OOMKilled` breaking point.
  - Identifies the maximum memory consumption before the Linux cgroup out-of-memory killer terminates the process.
  - Provides empirical data to set `memory_limit` safely above real burst demands.

---

## 4. Network Delay (`network-delay.yaml`)
- **Mechanism**: Injects artificial latency into outgoing network packets via `NetworkChaos` using the Linux `tc` (traffic control) netem subsystem (from 10ms up to 1500ms).
- **Purpose**: Validates timeout handling and gRPC/HTTP connection pools.
  - Tests whether downstream latency causes thread starvation or cascading failures.
  - Verifies whether client timeouts break early rather than hanging user transactions indefinitely.

---

## 5. Network Loss (`network-loss.yaml`)
- **Mechanism**: Injects random packet drops into egress traffic via `NetworkChaos` (from 0.5% up to 15.0%).
- **Purpose**: Tests retry policies and exponential backoffs.
  - Determines whether retry budgets and TCP retransmissions recover dropped packets without leaking HTTP 500 errors to end users.

---

## 6. Network Partition (`network-partition.yaml`)
- **Mechanism**: Injects `iptables` drop rules to completely block network communication between a `source_app` and a `target_app`.
- **Purpose**: Tests graceful degradation and circuit breaking.
  - When a non-critical downstream microservice is severed (e.g. `recommendationservice`), does the upstream service return a fallback response, or does the entire user journey crash?

---

## 7. Node Failure (`node-failure.yaml`)
- **Mechanism**: Simulates an entire Kubernetes worker node outage by freezing or rebooting the node via `Workflow` / `NodeChaos`.
- **Purpose**: Tests multi-node scheduling and high availability.
  - Verifies whether `podAntiAffinity` rules ensure replicas are distributed across different nodes so an outage does not take down all instances of a service.
