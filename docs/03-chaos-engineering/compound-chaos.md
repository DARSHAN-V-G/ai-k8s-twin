# Compound Chaos Simulation & In-Place Swapping

## 1. The Compound Chaos Concept

Isolated, single-stressor testing fails to reveal compound production failures where multiple resource and network constraints strike simultaneously:
- A database query slows down (Network Delay) while packet retries surge (Network Loss).
- Container memory usage grows (Memory Stress) while processing threads spike (CPU Stress).

AI K8s Twin combines **5 chaos stressors** into a single unified multi-document YAML manifest executed in parallel during Stage 2:
1. `Memory Stress`
2. `CPU Stress`
3. `Network Delay`
4. `Network Loss`
5. `Network Partition`

---

## 2. In-Place Chaos Swapping (Fast Iteration Cycle)

### The Problem with Naive Redeployment
If an orchestrator destroys and recreates the Kubernetes deployment on every trial iteration:
- Container image pulling, init-containers, and readiness probes add 40–90 seconds per trial.
- Running 6 binary search iterations across 10 microservices would take **over 60 minutes**.

### The Solution: Persistent Deployments with In-Place Manifest Swapping
```text
[Deploy Microservice Once]
       |
       +---> Iteration 1: Apply chaos-iter-1.yaml  (Run k6 -> Collect telemetry -> Evaluate)
       |                   Delete chaos-iter-1.yaml
       |
       +---> Iteration 2: Apply chaos-iter-2.yaml  (Run k6 -> Collect telemetry -> Evaluate)
       |                   Delete chaos-iter-2.yaml
       |
       +---> Iteration 3: Apply chaos-iter-3.yaml  (Run k6 -> Collect telemetry -> Evaluate)
       |                   Delete chaos-iter-3.yaml
       |
[Clean Up Workload on Convergence]
```

1. The target microservice is deployed **once** when its lifecycle begins.
2. For each search iteration:
   - The engine generates a new compound YAML file: `generated/{service}-five-chaos-iter{N}.yaml`.
   - The previous chaos manifest is removed, and the new manifest is applied via `kubectl apply -f`.
   - Chaos Mesh attaches the new cgroup and network rules to the existing running pod in under 1 second.
3. If a container crashes with `OOMKilled`, the orchestrator pauses for 2 seconds while Kubernetes restarts the container, then applies the next gentler trial without tearing down the deployment.
4. Total iteration time is strictly bounded by the k6 load duration (e.g. 15s) plus 2s cleanup, allowing 5 iterations to finish in **~85 seconds**.
