# Prerequisites

Before deploying the AI K8s Twin platform, ensure your host environment satisfies the following dependencies:

## 1. Operating System & Hardware
- **Operating System**: Linux (Ubuntu 22.04+ recommended), macOS (Apple Silicon or Intel), or Windows 10/11 with WSL2 enabled.
- **CPU**: Minimum 4 CPU cores (8 cores recommended).
- **RAM**: Minimum 8 GB RAM (16 GB recommended to support running multi-pod microservices and Chaos Mesh daemons).
- **Disk**: Minimum 20 GB free disk space.

---

## 2. Core Software Dependencies

| Tool | Minimum Version | Installation Check | Description |
| :--- | :--- | :--- | :--- |
| **Docker** | $\ge 24.0.0$ | `docker --version` | Container runtime engine required by Kind / Minikube. |
| **kubectl** | $\ge 1.28.0$ | `kubectl version --client` | Kubernetes command-line interface. |
| **Kind** or **Minikube** | Kind $\ge 0.20.0$ or Minikube $\ge 1.32.0$ | `kind version` or `minikube version` | Local Kubernetes simulation cluster. |
| **Helm** | $\ge 3.12.0$ | `helm version` | Kubernetes package manager used for Chaos Mesh and Prometheus. |
| **Python** | $\ge 3.10$ | `python --version` | Python runtime for the FastAPI backend engine. |
| **Node.js** & **npm** | Node $\ge 18.0.0$, npm $\ge 9.0.0$ | `node --version && npm --version` | JavaScript runtime for the React / Vite frontend. |
| **Git** | $\ge 2.34.0$ | `git --version` | Used to clone target application repositories. |

---

## 3. Python Virtual Environment Setup

Create and activate a dedicated virtual environment in the repository root:

```bash
# On Linux / macOS
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install backend dependencies:
```bash
pip install -r backend/requirements.txt
```

---

## 4. Frontend Dependencies Setup

Navigate to the `frontend/` directory and install required npm packages:
```bash
cd frontend
npm install
cd ..
```
