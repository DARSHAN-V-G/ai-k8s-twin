# User Interface Guide

A walkthrough of the AI K8s Twin dashboard panels and design elements.

---

## 1. Top Configuration Bar
- **Workload Parameters**: Set GitHub repository URL, Node CPU/RAM capacity, and k6 Virtual Users / Duration.
- **Optimization Mode Switch**: Toggle between `binary_search` (multi-iteration iterative optimization) and `heuristic` (single-pass validation).
- **Chaos Sequence Selection**: Checkboxes for the 7 individual chaos sequences.

---

## 2. Microservice Resilience Grid (Left Column)
- Displays all discovered services with identity chips (`Deployment • default`).
- **Status Pills**: `[WAITING]`, `[RUNNING]`, `[PASSED]`, or `[FAILED]`.
- **Stage Pipeline Dots**:
  - `[OK]`: Stage passed
  - `[X]`: Stage failed
  - `[..]`: Stage actively running
  - `[-]`: Stage pending
- **Right-Sized Teaser**: Shows `Right-Sized: {Limit} / {Request} RAM • {Limit} / {Request} CPU`.
- **Iteration Count Badge**: Shows total iterations run and safe tolerances.

---

## 3. Workload Inspector (Right Column)

### A. 4-Tile Resilience Tolerances Grid
Displays active bounds and safe tolerance metrics across all 4 dimensions:
1. **RAM STRESS**: Safe tolerance (e.g. `64M`), bounds `[1M, 128M]`, status `[CONVERGED]` / `[TUNING]`.
2. **CPU SATURATION**: Safe tolerance (e.g. `75%`), bounds `[10%, 100%]`, status `[CONVERGED]` / `[TUNING]`.
3. **NETWORK DELAY**: Safe tolerance (e.g. `350ms`), bounds `[10ms, 1500ms]`, status `[CONVERGED]` / `[TUNING]`.
4. **PACKET LOSS**: Safe tolerance (e.g. `4.2%`), bounds `[0.5%, 15.0%]`, status `[CONVERGED]` / `[TUNING]`.

### B. Dual Right-Sizing Grid
Four high-contrast cards displaying:
- **Memory Allocation**: Both `LIMIT` (+25% buffer) and `REQUEST` (baseline steady-state).
- **CPU Allocation**: Both `LIMIT` (+25% buffer) and `REQUEST` (baseline steady-state).
- **Max Memory Observed**: Peak MiB recorded by Prometheus.
- **Max CPU Observed**: Peak millicores recorded by Prometheus.

### C. Trial Stream Timeline
- **Verdict Badges**: Displays `[PASS]` or `[BREACH: {CULPRIT}]` (e.g. `[BREACH: LOSS]`, `[BREACH: RAM]`).
- **Applied 5-Chaos Vector**: Chips displaying RAM, CPU, Delay, Loss, and Partition targets. Culprit dimensions are highlighted in high-contrast red.
- **Step Decision**: Explains the exact mathematical bound update made (e.g. `> Contracted LOSS Upper Bound: [0.5%, 7.8%] -> [0.5%, 3.9%]. Other dimensions held steady.`).
- **Strict Clean Typography**: Zero emojis, utilizing monospace tags and design tokens.

### D. Right-Sized Manifest Preview & One-Click Export
Following multi-stress convergence, the Workload Inspector renders the production-ready Kubernetes manifest:
- **`[COPY YAML]` Button**: Copies the complete optimized YAML manifest directly to the operating system clipboard with a temporary `[COPIED]` visual badge.
- **`[DOWNLOAD YAML]` Button**: Triggers an immediate browser download of `{service}-optimized-deployment.yaml`.
- **Live Code Preview**: Displays the patched deployment specification showing:
  - Guaranteed scheduling floors (`resources.requests`) based on healthy baseline telemetry.
  - Safe resilience ceilings (`resources.limits`) with $+25\%$ buffer.
  - Dynamic replica recommendation (`replicas: 1` or `2`) accompanied by the `ai-k8s-twin.io/replica-rationale` annotation.
  - Dynamically tuned probe timeouts (`timeoutSeconds`) and cold-boot delays (`initialDelaySeconds`).

---

## 4. Live Partitioned Terminal Console
- **Service Tabs**: Toggle between the selected service's isolated stdout/stderr stream and the Global Console.
- **Auto-Scroll Toggle**: Automatically pins terminal view to the latest incoming log entries.
- **Log Search Filter**: Client-side filtering to search log traces for errors, keywords, or status codes.
