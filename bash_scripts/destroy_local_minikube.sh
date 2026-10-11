#!/usr/bin/env bash
# ==============================================================================
# AI K8s Twin - Local Minikube Teardown Script
# Automates: Stopping frontend & backend, destroying Minikube cluster, cleaning up
# ==============================================================================

set -uo pipefail

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

echo -e "${C_BOLD}${C_RED}====================================================${C_RESET}"
echo -e "${C_BOLD}${C_RED} AI K8s Twin: Destroying Environment (Minikube)     ${C_RESET}"
echo -e "${C_BOLD}${C_RED}====================================================${C_RESET}"

# 1. Stop Backend
log_info "Stopping Backend server..."
if [ -f "${REPO_ROOT}/backend.pid" ]; then
    PID=$(cat "${REPO_ROOT}/backend.pid")
    if ps -p "${PID}" >/dev/null 2>&1; then
        kill -9 "${PID}" 2>/dev/null || true
        log_success "Terminated backend process (PID: ${PID})."
    fi
    rm -f "${REPO_ROOT}/backend.pid"
fi
fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true

# 2. Stop Frontend
log_info "Stopping Frontend server..."
if [ -f "${REPO_ROOT}/frontend.pid" ]; then
    PID=$(cat "${REPO_ROOT}/frontend.pid")
    if ps -p "${PID}" >/dev/null 2>&1; then
        kill -9 "${PID}" 2>/dev/null || true
        log_success "Terminated frontend process (PID: ${PID})."
    fi
    rm -f "${REPO_ROOT}/frontend.pid"
fi
fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null || true

# 3. Destroy Minikube Cluster
log_info "Stopping and deleting Minikube cluster..."
if command -v minikube >/dev/null 2>&1; then
    minikube stop 2>/dev/null || true
    minikube delete 2>/dev/null || true
    log_success "Minikube cluster stopped and deleted."
else
    log_warn "Minikube command not found, skipping."
fi

echo -e "\n${C_BOLD}${C_GREEN}====================================================${C_RESET}"
echo -e "${C_BOLD}${C_GREEN} Cleanup Complete! Minikube Environment Destroyed.  ${C_RESET}"
echo -e "${C_BOLD}${C_GREEN}====================================================${C_RESET}\n"
