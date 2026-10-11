# Chaos Mesh Custom Resource Definitions (CRDs)

AI K8s Twin uses Jinja2 templates located in `backend/chaos/` to dynamically generate Chaos Mesh Custom Resources at runtime.

---

## 1. CRD Template Reference

### A. Pod Kill (`pod-kill.yaml`)
```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
spec:
  action: pod-kill
  mode: {{ mode }}
  selector:
    namespaces:
      - {{ namespace }}
    labelSelectors:
      app: {{ app }}
```
- **`action: pod-kill`**: Terminates the container immediately.
- **`mode: one`**: Targets a single random replica among matching pods.

---

### B. CPU Stress (`cpu-stress.yaml`)
```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
spec:
  mode: {{ mode }}
  selector:
    namespaces:
      - {{ namespace }}
    labelSelectors:
      app: {{ app }}
  stressors:
    cpu:
      workers: {{ workers }}
      load: {{ load }}
  duration: "{{ duration }}"
```
- **`stressors.cpu.load`**: Percent CPU load applied per worker thread.
- **`duration`**: Automatic lifespan after which Chaos Mesh cleans up the stress process.

---

### C. Memory Stress (`memory-stress.yaml`)
```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
spec:
  mode: {{ mode }}
  selector:
    namespaces:
      - {{ namespace }}
    labelSelectors:
      app: {{ app }}
  stressors:
    memory:
      workers: {{ workers }}
      size: "{{ size }}"
  duration: "{{ duration }}"
```
- **`stressors.memory.size`**: Absolute RAM size to allocate inside the cgroup (e.g. `64M`, `128M`).

---

### D. Network Delay & Network Loss (`network-delay.yaml` & `network-loss.yaml`)
```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
spec:
  action: {{ action }}   # delay or loss
  mode: {{ mode }}
  selector:
    namespaces:
      - {{ namespace }}
    labelSelectors:
      app: {{ app }}
  delay:
    latency: "{{ latency }}"
    jitter: "{{ jitter }}"
  loss:
    loss: "{{ loss }}"
  direction: to
  duration: "{{ duration }}"
```
- **`action: delay`**: Injects `delay.latency` (e.g. `120ms`).
- **`action: loss`**: Injects `loss.loss` (e.g. `2.5%`).
- **`direction: to`**: Targets egress traffic sent from the container to dependencies.

---

### E. Network Partition (`network-partition.yaml`)
```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
spec:
  action: partition
  mode: {{ mode }}
  selector:
    namespaces:
      - {{ namespace }}
    labelSelectors:
      app: {{ source_app }}
  direction: to
  target:
    mode: {{ target_mode }}
    selector:
      namespaces:
        - {{ namespace }}
      labelSelectors:
        app: {{ target_app }}
  duration: "{{ duration }}"
```
- **`action: partition`**: Injects drop rules.
- **`source_app`**: Outgoing caller pod.
- **`target_app`**: Destination dependency being isolated.
