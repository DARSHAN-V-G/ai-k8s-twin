#!/usr/bin/env bash
# ==============================================================================
# AI K8s Twin - Local Minikube Deployment Script
# Automates: Minikube cluster start, Metrics Server, Chaos Mesh, Backend, Frontend
# Features: Live streaming server logs with graceful shutdown on Ctrl+C
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Color palette
C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_BLUE='\033[0;34m'
C_CYAN='\033[0;36m'
C_BOLD='\033[1m'

log_info() { echo -e "${C_CYAN}[INFO]${C_RESET} $1"; }
log_success() { echo -e "${C_GREEN}[SUCCESS]${C_RESET} $1"; }
log_warn() { echo -e "${C_YELLOW}[WARN]${C_RESET} $1"; }
log_error() { echo -e "${C_RED}[ERROR]${C_RESET} $1"; }

echo -e "${C_BOLD}${C_BLUE}====================================================${C_RESET}"
echo -e "${C_BOLD}${C_BLUE} AI K8s Twin: Deploying Local Environment (Minikube) ${C_RESET}"
echo -e "${C_BOLD}${C_BLUE}====================================================${C_RESET}"

# 1. Pre-flight checks
log_info "Verifying required tools..."
for cmd in docker minikube kubectl curl python3 node npm; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log_error "Missing required command: '$cmd'. Please install it before proceeding."
        exit 1
    fi
done

if ! docker info >/dev/null 2>&1; then
    log_error "Docker is not running. Please start Docker / Docker Desktop."
    exit 1
fi
log_success "All pre-flight tools verified."

# 1b. Verify / Auto-install k6
if ! command -v k6 >/dev/null 2>&1; then
    log_info "k6 not found. Installing k6 load-testing tool..."
    sudo gpg -k 2>/dev/null || true
    sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69 2>/dev/null || true
    echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list >/dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq k6
    log_success "k6 installed successfully."
else
    log_success "k6 load-testing tool found."
fi

# 2. Minikube Cluster Provisioning
log_info "Checking Minikube status..."
if minikube status >/dev/null 2>&1; then
    log_warn "Minikube is already running."
else
    log_info "Starting Minikube cluster with Docker driver..."
    minikube start --driver=docker --cpus=2 --memory=4096
    log_success "Minikube started."
fi

# 3. Enable Minikube Metrics Server
log_info "Enabling Minikube metrics-server addon..."
minikube addons enable metrics-server
log_success "Metrics Server addon enabled."

# 4. Chaos Mesh Installation
log_info "Checking Chaos Mesh installation..."
if ! kubectl get ns chaos-mesh >/dev/null 2>&1; then
    log_info "Installing Chaos Mesh..."
    curl -sSL https://mirrors.chaos-mesh.org/v2.6.3/install.sh | bash -s -- --local minikube
    log_success "Chaos Mesh installed."
else
    log_warn "Chaos Mesh namespace already exists."
fi

# 5. Backend Server Setup
log_info "Configuring Python Backend..."
cd "${REPO_ROOT}/backend"

VENV_PATH="${HOME}/ai-k8s-twin-venv"
if [ ! -d "${VENV_PATH}" ]; then
    log_info "Creating Python virtualenv at ${VENV_PATH}..."
    python3 -m venv "${VENV_PATH}"
fi

source "${VENV_PATH}/bin/activate"
pip install --upgrade pip -q
log_info "Installing backend dependencies..."
pip install -r "${REPO_ROOT}/backend/requirements.txt" -q
log_success "Backend dependencies installed."

# Kill previous backend if running on port 8000
if lsof -ti :${BACKEND_PORT} >/dev/null 2>&1; then
    log_warn "Port ${BACKEND_PORT} is in use. Terminating previous backend..."
    fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
    sleep 1
fi

log_info "Starting Backend server on port ${BACKEND_PORT}..."
nohup uvicorn main:app --host 0.0.0.0 --port ${BACKEND_PORT} --reload > "${REPO_ROOT}/backend.log" 2>&1 &
BACKEND_PID=$!
echo "${BACKEND_PID}" > "${REPO_ROOT}/backend.pid"

sleep 2
if ps -p "${BACKEND_PID}" >/dev/null; then
    log_success "Backend started (PID: ${BACKEND_PID}) -> http://localhost:${BACKEND_PORT}"
else
    log_error "Backend failed to start. Check ${REPO_ROOT}/backend.log"
    exit 1
fi

# 6. Frontend Server Setup
log_info "Configuring Frontend..."
cd "${REPO_ROOT}/frontend"

if [ ! -d "node_modules" ]; then
    log_info "Installing npm dependencies..."
    npm install
fi

# Kill previous frontend if running on port 5173
if lsof -ti :${FRONTEND_PORT} >/dev/null 2>&1; then
    log_warn "Port ${FRONTEND_PORT} is in use. Terminating previous frontend..."
    fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null || true
    sleep 1
fi

log_info "Starting Frontend dev server on port ${FRONTEND_PORT}..."
nohup npm run dev > "${REPO_ROOT}/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "${FRONTEND_PID}" > "${REPO_ROOT}/frontend.pid"

sleep 2
if ps -p "${FRONTEND_PID}" >/dev/null; then
    log_success "Frontend started (PID: ${FRONTEND_PID}) -> http://localhost:${FRONTEND_PORT}"
else
    log_error "Frontend failed to start. Check ${REPO_ROOT}/frontend.log"
    exit 1
fi

echo -e "\n${C_BOLD}${C_GREEN}====================================================${C_RESET}"
echo -e "${C_BOLD}${C_GREEN} AI K8s Twin (Minikube) Deployed Successfully!      ${C_RESET}"
echo -e "${C_BOLD}${C_GREEN}====================================================${C_RESET}"
echo -e "Dashboard UI:        ${C_BOLD}${C_CYAN}http://localhost:${FRONTEND_PORT}${C_RESET}"
echo -e "Backend API Docs:    ${C_BOLD}${C_CYAN}http://localhost:${BACKEND_PORT}/docs${C_RESET}"
echo -e "Backend Logs:        ${C_YELLOW}${REPO_ROOT}/backend.log${C_RESET}"
echo -e "Frontend Logs:       ${C_YELLOW}${REPO_ROOT}/frontend.log${C_RESET}"

# 7. Live Log Streaming with Graceful Shutdown on Ctrl+C (Option 2)
cleanup_servers() {
    echo -e "\n\n${C_BOLD}${C_YELLOW}[SHUTDOWN] Caught Ctrl+C. Gracefully stopping backend & frontend...${C_RESET}"
    if [ -n "${BACKEND_PID:-}" ] && ps -p "${BACKEND_PID}" >/dev/null 2>&1; then
        kill "${BACKEND_PID}" 2>/dev/null || true
        log_success "Backend process stopped."
    fi
    if [ -n "${FRONTEND_PID:-}" ] && ps -p "${FRONTEND_PID}" >/dev/null 2>&1; then
        kill "${FRONTEND_PID}" 2>/dev/null || true
        log_success "Frontend process stopped."
    fi
    fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
    fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null || true
    rm -f "${REPO_ROOT}/backend.pid" "${REPO_ROOT}/frontend.pid"
    echo -e "${C_BOLD}${C_GREEN}Servers stopped cleanly. Minikube cluster remains active.${C_RESET}"
    echo -e "To tear down the cluster completely, run: ${C_BOLD}bash bash_scripts/destroy_local_minikube.sh${C_RESET}\n"
    exit 0
}

trap cleanup_servers INT TERM

echo -e "\n${C_BOLD}${C_CYAN}====================================================${C_RESET}"
echo -e "${C_BOLD}${C_CYAN}   STREAMING LIVE BACKEND LOGS                     ${C_RESET}"
echo -e "${C_BOLD}${C_CYAN}   Press [Ctrl+C] to gracefully stop servers       ${C_RESET}"
echo -e "${C_BOLD}${C_CYAN}====================================================${C_RESET}\n"

tail -n 20 -f "${REPO_ROOT}/backend.log"
