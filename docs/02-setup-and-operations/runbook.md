# Operational Runbook

This guide covers starting the backend and frontend, running experiments, and troubleshooting operational issues.

---

## 1. Starting the Platform

### Terminal 1: Backend Server (FastAPI)
Activate your Python environment and start the Uvicorn ASGI server:
```bash
# In repository root
source venv/bin/activate  # Or .\venv\Scripts\Activate.ps1 on Windows
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
The backend API documentation is available at: `http://localhost:8000/docs`

### Terminal 2: Frontend Dashboard (Vite + React)
```bash
cd frontend
npm run dev
```
Open your browser at: `http://localhost:5173`

The Vite dev server automatically proxies all `/api` requests to `http://127.0.0.1:8000`.

---

## 2. Running an Experiment

1. Open `http://localhost:5173`.
2. In the **Workload Configuration** panel:
   - **Target GitHub Repository**: Enter the Git clone URL (default: Google Cloud Microservices Demo).
   - **Cluster Specs**: Enter Node CPU (e.g. `2`) and RAM (e.g. `4Gi`).
   - **k6 Load Parameters**: Enter Virtual Users (e.g. `10`) and Duration (e.g. `30s`).
   - **Optimization Engine**: Select `binary_search` (default) or `heuristic`.
3. Choose desired chaos sequences from the **Chaos Selection** grid.
4. Click **"Run All Workloads"** to evaluate the whole repository sequentially, or click **"Discover Workloads"** to inspect manifests and click **"RUN"** on an individual microservice card.
5. Inspect the live progress in the **Microservice Resilience Grid**, **Workload Inspector**, and **Terminal Console**.

---

## 3. Troubleshooting Common Issues

### Issue A: Port-forwarding fails or connection refused
- **Cause**: Kubernetes pod or service has not reached ready state.
- **Fix**: Check `kubectl get pods -A` to verify `chaos-mesh`, `prometheus`, and workload pods are `Running` and not in `ImagePullBackOff`.

### Issue B: Chaos Mesh injection fails with "daemon socket error"
- **Cause**: The Chaos Daemon pod cannot reach the container runtime socket.
- **Fix**: On Kind, ensure `chaosDaemon.runtime=containerd` and `socketPath=/run/containerd/containerd.sock`. On Minikube with docker driver, ensure `chaosDaemon.runtime=docker` and `socketPath=/var/run/docker.sock`.

### Issue C: Gateway pod (frontend) returns 100% HTTP 500
- **Cause**: Self-partitioning severed incoming traffic.
- **Fix**: Verify that in compound chaos, `Network Partition` targets leaf services (e.g. `recommendationservice`) rather than `frontend` self-blackout. This safeguard is enforced in `environment_orchestrator.py:build_chaos_parameters`.

### Issue D: Stopping an in-flight experiment
- Click **"STOP EXPERIMENT"** in the top bar or click **"STOP"** on the active service card.
- Alternatively, send a POST request:
  ```bash
  curl -X POST http://localhost:8000/api/environment-orchestrator/stop
  ```
