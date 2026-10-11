# System Overview

## 1. The Problem
In modern cloud-native architectures, Kubernetes microservices are commonly either:
1. **Grossly Over-Provisioned**: SRE teams allocate arbitrarily high CPU and RAM limits to avoid outages, inflating cloud bills by 40–70%.
2. **Dangerously Under-Provisioned**: Services lack adequate requests or limits, causing random `OOMKilled` crashes, CPU throttling, or cascading network timeouts during peak traffic.
3. **Resilience-Blind**: Teams rarely know how their microservices behave when dependencies suffer latency spikes, packet loss, or network partitions until an actual production incident occurs.

Manual chaos experiments and sizing spreadsheets are slow, error-prone, and cannot keep up with continuous delivery.

---

## 2. The Solution: AI K8s Twin
**AI K8s Twin** is an automated resilience simulation and right-sizing engine. It acts as an autonomous digital twin that:
- Clones a target repository and parses its Kubernetes manifests.
- Deploys microservices into an isolated local Kubernetes simulation environment (Kind or Minikube).
- Subjects workloads to **7 real-world chaos experiments** (Pod Kill, CPU Stress, Memory Stress, Network Delay, Network Loss, Network Partition, Node Failure).
- Runs an iterative **4-dimensional Binary Search Optimization Engine** under concurrent k6 load traffic to pinpoint the exact breaking points and safe operating limits for:
  - Container RAM pressure
  - CPU saturation
  - Network latency tolerance
  - Packet drop tolerance
- Implements **Root-Cause Failure Attribution** to ensure network failures do not penalize RAM bounds, and vice versa.
- Generates **Optimal Right-Sized Configurations** recommending both `memory_limit`, `memory_request`, `cpu_limit`, and `cpu_request` with automated +25% safety buffers.
- Streams live telemetry, decision steps, and trial progress to a modern reactive dashboard via Server-Sent Events (SSE).

---

## 3. Core Feature Matrix

| Capability | Description |
| :--- | :--- |
| **Autonomous Discovery** | Scans Git repositories for Deployment, Service, StatefulSet, and DaemonSet definitions automatically. |
| **In-Place Chaos Swapping** | Deploys pods once per service and dynamically rotates Chaos Mesh CRD manifests, cutting multi-iteration runs from 10 minutes down to ~90 seconds. |
| **4-Param Multi-Vector Convergence** | Explores safe boundaries across RAM, CPU, Delay, and Loss simultaneously. |
| **Root-Cause Attribution** | Automatically detects whether an SLA breach was caused by RAM (`OOMKilled`), Loss (`error_rate > 1%`), Delay (`p95 > 1000ms`), or CPU (throttling), stepping only the culprit dimension. |
| **Dual Right-Sizing** | Outputs both Kubernetes `requests` (for scheduling guarantees) and `limits` (for runtime protection). |
| **Live Telemetry & Logs** | Live-streams trial midpoints, bound updates, PromQL metrics, and k6 telemetry per service with dedicated log tab partitioning. |
