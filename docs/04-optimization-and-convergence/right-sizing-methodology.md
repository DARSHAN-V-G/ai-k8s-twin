# Right-Sizing Methodology (Limits & Requests)

## 1. Why Both Limits AND Requests Are Mandatory

In Kubernetes, production deployments require two distinct resource specifications:

1. **`requests` (Scheduling Floor)**:
   - Used by the Kubernetes Scheduler (`kube-scheduler`) to determine which worker node has enough available capacity to host the pod.
   - Guaranteed minimum resource allocation.
2. **`limits` (Runtime Enforcement Ceiling)**:
   - Enforced by the Linux kernel via CFS bandwidth control (for CPU) and cgroup OOM killer (for Memory).
   - Prevents noisy neighbor workloads from monopolizing the node.

---

## 2. Right-Sizing Calculation Formulas

The orchestrator combines **empirical peak resource utilization** and **maximum safe chaos tolerances**:

### Memory Sizing
- **Recommended Memory Limit**:
  $$\text{memory\_limit} = \max\left(64\text{Mi}, \; \text{Baseline In-Use RAM} + (S_{\text{safe, RAM}} \times 1.25)\right)$$
  - Where $S_{\text{safe, RAM}}$ is the maximum safe memory stress survived during binary search.
  - An automated $+25\%$ safety buffer is added to absorb unexpected traffic surges.
- **Recommended Memory Request**:
  $$\text{memory\_request} = \max\left(32\text{Mi}, \; \text{Baseline In-Use RAM}\right)$$
  - Sized directly to the service's baseline steady-state working set to avoid cluster capacity waste.

### CPU Sizing
- **Recommended CPU Limit**:
  $$\text{cpu\_limit} = \max\left(100\text{m}, \; \text{Baseline In-Use CPU} \times 1.25\right)$$
  - Accommodates transient burst compute with $+25\%$ buffer.
- **Recommended CPU Request**:
  $$\text{cpu\_request} = \max\left(50\text{m}, \; \text{Baseline In-Use CPU}\right)$$
  - Guarantees minimum CPU share during high node contention.

---

## 3. Baseline Under-Provisioning Handling

If a service crashes (`OOMKilled`) with **0MB applied stress** (meaning its existing manifest cannot even support baseline traffic):
- `has_passed = False`
- Safe tolerance: `0M`
- The system automatically recommends an upgraded baseline:
  - `memory_limit: 128Mi` or $2\times$ observed peak
  - `memory_request: 64Mi`
  - Flags the service in the dashboard with `[BREACH: RAM] - Baseline capacity insufficient`.
