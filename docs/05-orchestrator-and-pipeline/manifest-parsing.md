# Manifest Parsing & Discovery

The discovery subsystem scans repository codebases to identify deployable Kubernetes microservices without manual configuration.

---

## 1. Discovery Process

1. **Repository Cloning (`github_service.py`)**:
   - Clones target GitHub repository using `GitPython` into a local staging directory.
2. **Recursive YAML Discovery (`yaml_parser.py`)**:
   - Scans directories for `.yaml` and `.yml` files.
   - Parses multi-document YAML files containing `---` separators.
3. **AST Resource Analysis (`project_analyzer.py`)**:
   - Evaluates each parsed dictionary against supported Kubernetes workload kinds:
     - `Deployment`
     - `StatefulSet`
     - `DaemonSet`
     - `Service`
     - `ServiceAccount`

---

## 2. Extracted Application Schema

For every discovered service, the analyzer extracts:
```json
{
  "name": "cartservice",
  "kind": "Deployment",
  "namespace": "default",
  "replicas": 1,
  "containers": [
    {
      "name": "server",
      "image": "gcr.io/google-samples/microservices-demo/cartservice:v0.8.0",
      "ports": [{"containerPort": 7070}],
      "resources": {
        "requests": {"cpu": "200m", "memory": "64Mi"},
        "limits": {"cpu": "300m", "memory": "128Mi"}
      }
    }
  ],
  "labels": {"app": "cartservice"},
  "service_ports": [7070]
}
```

This metadata informs:
- Initial binary search upper bounds for RAM and CPU.
- Label selectors injected into Chaos Mesh YAML templates.
- Target endpoints and ports used by k6 load test scripts.
