# Right-Sizing & Manifest Tuning Methodology

## 1. Why Both Limits AND Requests Are Mandatory

In Kubernetes, production deployments require two distinct resource specifications:

1. **`requests` (Scheduling Floor)**:
   - Used by the Kubernetes Scheduler (`kube-scheduler`) to determine which worker node has enough available capacity to host the pod.
   - Guaranteed minimum resource allocation.
2. **`limits` (Runtime Enforcement Ceiling)**:
   - Enforced by the Linux kernel via CFS bandwidth control (for CPU) and cgroup OOM killer (for Memory).
   - Prevents noisy neighbor workloads from monopolizing the node.

---

## 2. Dual-Metrics Sizing Formula

Rather than using a single test run to determine both numbers, the engine utilizes **Dual-Metrics Sizing**:

- **Baseline Request (`resources.requests`)**:
  - Sampled from the cleanest, lowest-stress passing trial (e.g., Trial 01 with minimal chaos) to capture true steady-state working set size.
  - Sized without inflating node reservations for chaos spikes that rarely occur.
  $$\text{memory\_request} = \max\left(18\text{Mi}, \; \text{Baseline In-Use RAM}\right)$$
  $$\text{cpu\_request} = \max\left(25\text{m}, \; \text{Baseline In-Use CPU}\right)$$

- **Resilience Ceiling (`resources.limits`)**:
  - Sampled from the highest-stress trial survived during Stage 2 Multi-Chaos search, plus an automated $+25\%$ buffer.
  - Guarantees that when extreme network buffering or traffic spikes hit, the container will not be terminated by the kernel `OOMKilled` killer.
  $$\text{memory\_limit} = \max\left(32\text{Mi}, \; \text{Peak Chaos RAM} \times 1.25\right)$$
  $$\text{cpu\_limit} = \max\left(62\text{m}, \; \text{Peak Chaos CPU} \times 1.25\right)$$

---

## 3. Dynamic 4-Case Replica Decision Framework

Rather than hardcoding a static replica count, the engine evaluates the microservice architecture against **4 production criteria** to determine whether `replicas: 1` is optimal or `replicas: 2` is required for High Availability (HA):

| Case | Scenario | Decision | Rationale |
| :--- | :--- | :--- | :--- |
| **Case 1** | **Asynchronous Queue / Background Workers** (`worker`, `consumer`, `queue`, `processor`, `job`) | `replicas: 1` | Incoming jobs wait safely in the message queue (Kafka/RabbitMQ) for the 5–8s restart window. Zero HTTP user requests fail and no data is lost. Running 2 replicas would double compute costs without user benefit. |
| **Case 2** | **Fast Recovery With Client Retries** (lightweight microservice with $\text{recovery\_time} \le 1.5\text{s}$) | `replicas: 1` | The container restarts so quickly that upstream client retry policies (e.g., Envoy service mesh or gRPC retries) completely mask the restart. Customer-facing error rate remains $0.0\%$. |
| **Case 3** | **Stateful Singletons (Single-Writer Constraint)** (`StatefulSet`, SQLite, single-leader coordinator) | `replicas: 1` | Running 2 replicas would cause split-brain or data corruption due to dual writers competing for local file locks or disk storage. |
| **Case 4** | **Non-Production / Dev Environments** (`namespace` is `dev`, `staging`, `test`, or cost priority enabled) | `replicas: 1` | Cost optimization takes precedence over multi-replica redundancy. A brief 5-second hiccup during failure is acceptable to save 50% cloud compute spend. |
| **Default** | **Synchronous User-Facing Production Workload** ($\text{recovery\_time} > 1.5\text{s}$ in production) | `replicas: 2` | Synchronous API where restart induces customer downtime; multi-replica redundancy with rolling update support is strictly required. |

The decision and rationale are permanently embedded into the manifest annotations:
```yaml
metadata:
  annotations:
    ai-k8s-twin.io/replica-rationale: "Case 1: Asynchronous Worker/Queue Consumer (jobs buffer safely in queue during restart, 0 HTTP failures)"
```

---

## 4. Dynamic Health Probe Calibration

Static probe timeouts often cause false-positive container restarts during transient network latency spikes or cold-boot delays. The engine dynamically tunes health probes using empirical metrics:

### A. Dynamic `timeoutSeconds` (Latency-Adaptive)
Calculated directly from that service's validated maximum safe network delay ($S_{\text{safe, DELAY}}$) with a 25% safety buffer:
$$\text{timeoutSeconds} = \max\left(1, \; \left\lceil \frac{S_{\text{safe, DELAY (ms)}} \times 1.25}{1000} \right\rceil\right)$$

- **400ms survived delay** $\rightarrow$ `timeoutSeconds: 1`
- **1127ms survived delay** $\rightarrow$ `timeoutSeconds: 2`
- **2100ms survived delay** $\rightarrow$ `timeoutSeconds: 3`

### B. Dynamic `initialDelaySeconds` (Cold-Boot Adaptive)
Derived directly from the measured restart duration recorded during **Stage 1 (Pod Kill)**:
$$\text{initialDelaySeconds} = \max\left(2, \; \text{round}(\text{recovery\_time\_seconds} \times 0.75)\right)$$

This prevents `kubelet` from prematurely failing readiness probes while the application runtime or JVM is still initializing.

---

## 5. Right-Sized Manifest Generation & Export

At the conclusion of each service's lifecycle run, the engine:
1. Deep-clones the original Kubernetes deployment manifest from the cloned repository.
2. Patches the optimal `resources.requests` and `resources.limits`.
3. Sets `spec.replicas` and adds the `ai-k8s-twin.io/replica-rationale` annotation.
4. Tunes `readinessProbe`, `livenessProbe`, and `startupProbe` with calibrated `timeoutSeconds` and `initialDelaySeconds`.
5. Emits the resulting YAML to `backend/generated/{service}-optimized-deployment.yaml`.
6. Streams the manifest over SSE to the frontend dashboard, where operators can inspect, copy, or download it with one click.
