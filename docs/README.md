# AI K8s Twin — Documentation Hub

Welcome to the comprehensive documentation for **AI K8s Twin**, an automated resilience testing, chaos engineering, and right-sizing optimization platform for Kubernetes microservices.

---

## Documentation Index

### [01. Overview](01-overview/)
- [System Overview](01-overview/system-overview.md) — Problem statement, core mission, and feature breakdown.
- [Architecture & Data Flow](01-overview/architecture.md) — End-to-end component interactions, control loops, and subsystem architecture.

### [02. Setup & Operations](02-setup-and-operations/)
- [Prerequisites](02-setup-and-operations/prerequisites.md) — Required system tools (Docker, Minikube/Kind, Helm, Python, Node.js).
- [Local Cluster Setup](02-setup-and-operations/local-cluster-setup.md) — Step-by-step cluster bootstrap with Chaos Mesh, Prometheus, and Metrics Server.
- [Operational Runbook](02-setup-and-operations/runbook.md) — Starting backend & frontend services, troubleshooting, and verification checks.

### [03. Chaos Engineering](03-chaos-engineering/)
- [The 7 Chaos Types](03-chaos-engineering/the-seven-chaos-types.md) — Deep dive into Pod Kill, CPU Stress, Memory Stress, Network Delay, Network Loss, Network Partition, and Node Failure.
- [Chaos Mesh CRDs](03-chaos-engineering/chaos-mesh-crds.md) — YAML templates, selectors, traffic directions, and injection actions.
- [Compound Chaos](03-chaos-engineering/compound-chaos.md) — 5-Chaos simultaneous injection and zero-downtime in-place manifest swapping.

### [04. Optimization & Convergence](04-optimization-and-convergence/)
- [Binary Search Engine](04-optimization-and-convergence/binary-search-engine.md) — Multi-parameter binary search algorithm, active bounds, and convergence thresholds.
- [Failure Attribution Engine](04-optimization-and-convergence/failure-attribution.md) — Root-cause failure isolation (OOMKilled $\to$ RAM, Packet drop $\to$ Loss, Latency $\to$ Delay, Throttling $\to$ CPU).
- [Right-Sizing Methodology](04-optimization-and-convergence/right-sizing-methodology.md) — Dual recommendation generation for both Limits and Requests with +25% safety margins.

### [05. Orchestrator & Pipeline](05-orchestrator-and-pipeline/)
- [Lifecycle Pipeline](05-orchestrator-and-pipeline/lifecycle-pipeline.md) — Discovery $\to$ Deploy $\to$ Pod Kill $\to$ 5-Chaos $\to$ Node Failure $\to$ Teardown.
- [Manifest Parsing & Discovery](05-orchestrator-and-pipeline/manifest-parsing.md) — Git cloning, multi-document AST parsing, and resource dependency analysis.
- [SSE Streaming Protocol](05-orchestrator-and-pipeline/sse-streaming-protocol.md) — Real-time Server-Sent Events architecture and event definitions.

### [06. Metrics & Load Testing](06-metrics-and-load-testing/)
- [k6 Load Generation](06-metrics-and-load-testing/k6-load-generation.md) — In-cluster load execution, Virtual Users (VUs), and traffic generation.
- [Prometheus Telemetry](06-metrics-and-load-testing/prometheus-telemetry.md) — PromQL queries for container memory working sets and CPU saturation.
- [SLA Evaluation Criteria](06-metrics-and-load-testing/sla-evaluation.md) — Threshold evaluation for error rate, P95 latency, and kernel OOM kills.

### [07. API & Payload Schemas](07-api-and-schemas/)
- [REST API Reference](07-api-and-schemas/rest-api-reference.md) — FastAPI endpoints for orchestration control and status monitoring.
- [Event Payload Schemas](07-api-and-schemas/event-payload-schemas.md) — JSON schemas for all telemetry events.

### [08. Frontend Dashboard](08-frontend-dashboard/)
- [UI Architecture](08-frontend-dashboard/ui-architecture.md) — React state management, EventSource handling, and layout organization.
- [User Interface Guide](08-frontend-dashboard/user-interface-guide.md) — Navigating the Microservice Resilience Grid, 4-Tile Tolerance Cards, and Trial Stream.
