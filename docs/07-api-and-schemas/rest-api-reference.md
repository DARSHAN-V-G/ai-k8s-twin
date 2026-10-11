# REST API Reference

The backend exposes FastAPI endpoints on port `8000`.

---

## 1. Start Orchestration Execution
- **Endpoint**: `POST /api/environment-orchestrator/start`
- **Request Body**:
  ```json
  {
    "github_url": "https://github.com/GoogleCloudPlatform/microservices-demo.git",
    "cpu": "2",
    "memory": "4Gi",
    "vus": "10",
    "duration": "30s",
    "mode": "binary_search",
    "environments": [
      "Pod Kill",
      "CPU Stress",
      "Memory Stress",
      "Network Delay",
      "Network Loss",
      "Network Partition",
      "Node Failure"
    ],
    "target_service": "cartservice"   // Optional: run single service instead of all
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "status": "started",
    "message": "Orchestrator pipeline started in background."
  }
  ```

---

## 2. Stop Orchestration Execution
- **Endpoint**: `POST /api/environment-orchestrator/stop`
- **Response**: `200 OK`
  ```json
  {
    "status": "stopped",
    "message": "Stop signal sent to orchestrator."
  }
  ```

---

## 3. Server-Sent Events Stream
- **Endpoint**: `GET /api/environment-orchestrator/stream`
- **Headers**:
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
- **Description**: Streams continuous real-time progress events to the dashboard UI.
