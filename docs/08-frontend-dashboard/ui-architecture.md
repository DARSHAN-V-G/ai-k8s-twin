# Frontend Dashboard Architecture

The frontend is a single-page application built on **React 18** and **Vite**, using standard Vanilla CSS with design system design tokens defined in `:root`.

---

## 1. Directory Structure

```text
frontend/
├── index.html                   # HTML entry point with Google Fonts (JetBrains Mono & Plus Jakarta Sans)
├── package.json                 # Node dependencies
├── vite.config.js               # Dev server configuration with backend proxy
└── src/
    ├── main.jsx                 # React root mount
    ├── index.css                # Global resets and CSS variables
    ├── App.jsx                  # Main application state and layout
    └── App.css                  # Design system rules, grid layouts, cards, and animations
```

---

## 2. Core State Model (`App.jsx`)

- **`services`**: Array of discovered workloads:
  ```javascript
  {
    name: 'cartservice',
    status: 'running',        // waiting | running | passed | failed
    stages: { deploy: 'completed', pod_kill: 'completed', five_chaos: 'running', node_failure: 'pending' },
    iterations: [ ... ],      // array of trial results
    optimization: { ... },    // final right-sized config & tolerances
    metrics: { ... }
  }
  ```
- **`serviceLogs` & `globalLogs`**: Partitioned log stores separating service-specific logs from global orchestration events.
- **`selectedServiceName`**: Currently inspected microservice in the Workload Inspector.
- **`isUserInspectingRef`**: Prevents the UI from pulling focus away if the user manually clicks to inspect a different microservice card while another service is actively executing.

---

## 3. Streaming Event Loop

```javascript
const eventSource = new EventSource('/api/environment-orchestrator/stream')
eventSource.addEventListener('iteration_update', (e) => {
  const payload = JSON.parse(e.data)
  // Updates trials state immutably and logs step decision
})
```
