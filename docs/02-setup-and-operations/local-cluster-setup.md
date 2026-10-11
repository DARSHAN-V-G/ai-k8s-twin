# Local Cluster Setup

AI K8s Twin requires an isolated Kubernetes cluster running **Chaos Mesh**, **Prometheus**, and the **Kubernetes Metrics Server**.

Automated deployment scripts are provided in `bash_scripts/` for both **Kind** and **Minikube**.

---

## Option A: Kind Cluster (Recommended for CI / Linux)

Run the automated Kind setup script:
```bash
chmod +x bash_scripts/deploy_local_kind.sh
./bash_scripts/deploy_local_kind.sh
```

### What `deploy_local_kind.sh` Does:
1. **Creates a Multi-Node Kind Cluster**: Creates a cluster named `ai-k8s-twin` with 1 control plane node and 2 worker nodes.
2. **Mounts the Docker Socket**: Mounts `/var/run/docker.sock` and cgroups into worker nodes so Chaos Mesh can inject stress directly into host containers.
3. **Installs Chaos Mesh CRDs & Controllers**:
   ```bash
   helm repo add chaos-mesh https://charts.chaos-mesh.org
   helm install chaos-mesh chaos-mesh/chaos-mesh \
     -n chaos-mesh --create-namespace \
     --set chaosDaemon.runtime=containerd \
     --set chaosDaemon.socketPath=/run/containerd/containerd.sock
   ```
4. **Installs Prometheus**: Deploys Prometheus in namespace `monitoring` and configures port-forwarding on port `9090`.
5. **Installs Metrics Server**: Deploys the metrics server with `--kubelet-insecure-tls` for local metric aggregation.

To destroy the Kind cluster:
```bash
./bash_scripts/destroy_local_kind.sh
```

---

## Option B: Minikube Cluster (Recommended for macOS / Windows)

Run the automated Minikube setup script:
```bash
chmod +x bash_scripts/deploy_local_minikube.sh
./bash_scripts/deploy_local_minikube.sh
```

### What `deploy_local_minikube.sh` Does:
1. **Starts Minikube** with 4 CPUs, 8192 MB RAM, and the `docker` driver.
2. **Enables Addons**:
   ```bash
   minikube addons enable metrics-server
   minikube addons enable default-storageclass
   ```
3. **Installs Chaos Mesh** in namespace `chaos-mesh` with Docker daemon socket paths:
   ```bash
   helm install chaos-mesh chaos-mesh/chaos-mesh \
     -n chaos-mesh --create-namespace \
     --set chaosDaemon.runtime=docker \
     --set chaosDaemon.socketPath=/var/run/docker.sock
   ```
4. **Installs Prometheus** in namespace `monitoring`.

To destroy the Minikube cluster:
```bash
./bash_scripts/destroy_local_minikube.sh
```

---

## Verification Commands

After the cluster is running, verify all required pods are ready:

```bash
# Verify cluster nodes
kubectl get nodes

# Verify Chaos Mesh operator & daemon pods
kubectl get pods -n chaos-mesh

# Verify Prometheus
kubectl get pods -n monitoring

# Verify metrics server
kubectl top nodes
```
