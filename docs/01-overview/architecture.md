# System Architecture & Data Flow

## 1. High-Level Architectural Diagram

```mermaid
flowchart TD
    subgraph UI ["User Interface (Frontend)"]
        Dashboard["React / Vite Dashboard"]
        Inspector["Workload Inspector & Trial Stream"]
        Terminal["Live Partitioned Terminal Logs"]
    end

    subgraph Backend ["Backend Control Plane (FastAPI)"]
        API["FastAPI Orchestrator Routes"]
        Orchestrator["Environment Orchestrator"]
        Discovery["Manifest Parser & Project Analyzer"]
        Engine["MultiParamSearchSession Engine"]
        Attributor["Failure Attribution Engine"]
        Emitter["SSE Event Emitter"]
    end

    subgraph Cluster ["Simulation Kubernetes Cluster (Kind / Minikube)"]
        AppPod["Target Microservice Pods"]
        ChaosMesh["Chaos Mesh Operator & CRD Daemon"]
        Prometheus["Prometheus Monitoring Server"]
        MetricsServer["Kubernetes Metrics Server"]
        k6["k6 Cluster Load Runner"]
    end

    Dashboard -->|POST /start or /stop| API
    API --> Orchestrator
    Orchestrator --> Discovery
    Discovery -->|kubectl apply| AppPod
    Orchestrator --> Engine
    Engine -->|Generate YAML| ChaosMesh
    Orchestrator -->|Trigger k6 Job| k6
    k6 -->|HTTP Traffic| AppPod
    ChaosMesh -->|Kernel Stress / tc / iptables| AppPod
    Prometheus -->|PromQL Scrapes| AppPod
    Orchestrator -->|Collect Metrics| Prometheus
    Orchestrator -->|Collect Load Results| k6
    Orchestrator --> Attributor
    Attributor --> Engine
    Orchestrator --> Emitter
    Emitter -->|SSE Stream /stream| Dashboard
    Emitter -->|Live Telemetry| Inspector
    Emitter -->|Log Lines| Terminal
```

---

## 2. Component Subsystems

### A. Frontend Dashboard (React / Vite)
- Built on modern React with Vite.
- Connects to the backend via a long-lived Server-Sent Events (`EventSource`) connection (`/api/environment-orchestrator/stream`).
- Features:
  - **Microservice Resilience Grid**: Displays all discovered services with statuses (`WAITING`, `RUNNING`, `PASSED`, `FAILED`).
  - **Workload Inspector**: Shows real-time 4-parameter resilience tolerance tiles, dual memory/CPU limits & requests, and observed peaks.
  - **Trial Stream**: Timeline cards displaying applied chaos vectors, culprit failure tags (`[BREACH: LOSS]`, `[BREACH: RAM]`), and bound progressions.
  - **Partitioned Console**: Terminal with toggleable per-service log streams and global system logs.

### B. Backend Control Plane (FastAPI)
- **`environment_orchestrator.py`**: The central coordinator managing service-by-service execution, test phases, manifest generation, and cleanup.
- **`binary_search_service.py`**: Contains `BinarySearchSession` and `MultiParamSearchSession`, managing vector generation, bound adjustments, and failure attribution.
- **`yaml_parser.py` & `project_analyzer.py`**: Parses multi-document YAML manifests, resolving dependencies, containers, limits, requests, and port mappings.
- **`event_emitter.py`**: Thread-safe publisher that broadcasts structured events (`discovery`, `stage_update`, `iteration_update`, `service_result`) across active SSE clients.

### C. Simulation Cluster (Kind or Minikube)
- **Chaos Mesh**: Cloud-native chaos engineering platform injecting stress at the Linux cgroup and kernel network level (`stress-ng`, `tc`, `iptables`).
- **k6 Load Runner**: Runs within the cluster to execute high-volume synthetic user transactions without egress or ingress bottlenecks.
- **Prometheus & Metrics Server**: Collects granular resource consumption metrics (container working set memory and CPU core utilization).

---

## 3. End-to-End Execution Sequence

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Frontend as Dashboard UI
    participant Backend as Environment Orchestrator
    participant K8s as Kubernetes Cluster
    participant Chaos as Chaos Mesh
    participant k6 as k6 Runner
    participant Prom as Prometheus

    User->>Frontend: Clicks "Run All Workloads"
    Frontend->>Backend: POST /api/environment-orchestrator/start
    Backend->>Frontend: SSE "discovery" (Discovered N services)
    
    loop For each Service N
        Backend->>Frontend: SSE "service_start" (Target Service)
        Backend->>K8s: Deploy Microservice Manifests Once
        Backend->>K8s: Wait for Pod Readiness
        
        Note over Backend,Chaos: Stage 1: Pod Kill Evaluation
        Backend->>Chaos: Inject PodKill CRD
        Backend->>k6: Run baseline traffic check
        Backend->>Frontend: SSE "stage_update" (pod_kill: completed)
        
        Note over Backend,Chaos: Stage 2: Multi-Parameter Binary Search Loop
        loop Iterations 1..Max (Until Converged)
            Backend->>Engine: next_vector() -> RAM, CPU, Delay, Loss
            Backend->>Chaos: Apply Compound Chaos YAML (In-place swap)
            Backend->>k6: Run concurrent synthetic user load
            k6-->>Backend: Return request metrics (p95, error rate)
            Prom-->>Backend: Return container memory & CPU peaks
            Backend->>Attributor: attribute_failure_cause(k6, metrics)
            Attributor-->>Backend: Result (Passed or Culprit Dimension)
            Backend->>Engine: record_trial() (Advance or contract bound)
            Backend->>Frontend: SSE "iteration_update" (Vector, Result, Step Taken)
        end
        
        Note over Backend,K8s: Stage 3: Node Failure (if enabled)
        Backend->>Chaos: Inject NodeFailure CRD
        Backend->>Frontend: SSE "stage_update" (node_failure: completed)
        
        Backend->>Backend: Compute Right-Sizing (Limits & Requests +25%)
        Backend->>K8s: Clean up Chaos and Service Workload
        Backend->>Frontend: SSE "service_result" (Optimal Tolerances & Sizing)
    end
    
    Backend->>Frontend: SSE "aggregate_complete"
```
