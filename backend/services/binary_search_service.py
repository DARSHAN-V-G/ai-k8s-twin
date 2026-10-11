"""
Binary Search Resilience & Optimization Engine.

Provides deterministic parameter calculation, search bounds derivation,
SLA evaluation, and iterative binary search optimization to replace LLM dependency.
"""

from services.environment_validator import parse_memory, parse_cpu


DEFAULT_SLA = {
    "max_error_rate_percent": 1.0,
    "max_p95_ms": 300.0
}


def calculate_bounds(application, cluster_cpu="2", cluster_memory="4Gi"):
    """
    Derives deterministic [Low, High] bounds for each chaos stressor
    based on container limits and cluster capacity.
    """
    containers = application.get("containers", [])
    primary_container = containers[0] if containers else {}
    resources = primary_container.get("resources", {})
    limits = resources.get("limits", {})
    requests = resources.get("requests", {})

    # Memory limit parsing
    mem_limit_bytes = parse_memory(limits.get("memory"))
    mem_request_bytes = parse_memory(requests.get("memory"))
    cluster_mem_bytes = parse_memory(cluster_memory) or (4 * 1024 * 1024 * 1024)

    if mem_limit_bytes:
        max_mem_mb = max(16, int(mem_limit_bytes / (1000 * 1000)))
    elif mem_request_bytes:
        max_mem_mb = max(16, int((mem_request_bytes * 2) / (1000 * 1000)))
    else:
        max_mem_mb = max(64, int((cluster_mem_bytes * 0.25) / (1000 * 1000)))

    bounds = {
        "Memory Stress": {
            "low": 16,
            "high": max_mem_mb,
            "unit": "M",
            "threshold": 16  # Stop search when difference (high - low) <= 16M
        },
        "CPU Stress": {
            "low": 10,
            "high": 100,
            "unit": "",
            "threshold": 5   # Stop search when within 5%
        },
        "Network Delay": {
            "low": 10,
            "high": 2000,
            "unit": "ms",
            "threshold": 25  # Stop search when within 25ms
        },
        "Network Loss": {
            "low": 1,
            "high": 20,
            "unit": "",
            "threshold": 1   # Stop search when within 1%
        }
    }

    return bounds


def evaluate_sla(k6_result, metrics=None, max_error_rate_percent=None, max_p95_ms=None):
    """
    Evaluates whether an experiment iteration satisfied SLA criteria.
    """
    max_err = max_error_rate_percent if max_error_rate_percent is not None else DEFAULT_SLA["max_error_rate_percent"]
    max_p95 = max_p95_ms if max_p95_ms is not None else DEFAULT_SLA["max_p95_ms"]

    if metrics and metrics.get("oom_killed"):
        return False, "Container crashed with OOMKilled."

    if not k6_result or k6_result.get("status") == "failed":
        reason = k6_result.get("reason", "k6 execution failed.") if k6_result else "No k6 result."
        return False, reason

    error_rate = k6_result.get("error_rate_percent", 0.0)
    p95_latency = k6_result.get("p95_ms", 0.0)

    if error_rate > max_err:
        return False, f"Error rate {error_rate:.2f}% breached threshold ({max_err}%)."

    if p95_latency > max_p95:
        return False, f"P95 latency {p95_latency:.1f}ms breached threshold ({max_p95}ms)."

    return True, f"SLA satisfied (Error rate: {error_rate:.2f}%, P95: {p95_latency:.1f}ms)."


def generate_heuristic_parameters(application, environments, cpu="2", memory="4Gi", vus="10", duration="30s"):
    """
    Fast single-shot deterministic calculation scaling parameters to application size.
    Drop-in replacement for LLM parameter generation.
    """
    containers = application.get("containers", [])
    primary_container = containers[0] if containers else {}
    resources = primary_container.get("resources", {})
    limits = resources.get("limits", {})
    requests = resources.get("requests", {})

    # 1. Memory Stress
    mem_limit_bytes = parse_memory(limits.get("memory"))
    mem_request_bytes = parse_memory(requests.get("memory"))
    cluster_bytes = parse_memory(memory) or (4 * 1024 * 1024 * 1024)

    if mem_limit_bytes:
        # 75% of limit
        stress_mb = max(16, int((mem_limit_bytes * 0.75) / (1000 * 1000)))
    elif mem_request_bytes:
        stress_mb = max(16, int((mem_request_bytes * 1.25) / (1000 * 1000)))
    else:
        stress_mb = max(64, int((cluster_bytes * 0.15) / (1000 * 1000)))

    # 2. CPU Stress
    replicas = application.get("replicas", 1)
    base_cpu_stress = 60
    redundancy_bonus = min(25, max(0, (replicas - 1) * 5))
    cpu_stress_val = str(base_cpu_stress + redundancy_bonus)

    # 3. Network Delay & Loss
    dur_str = str(duration).strip()
    dur_sec = float(dur_str[:-1]) if dur_str.endswith("s") else (float(dur_str[:-1]) * 60 if dur_str.endswith("m") else 30)
    delay_ms = "100ms" if dur_sec <= 30 else "150ms"
    loss_val = "3"

    app_name = application.get("name", "app")

    parameters = {}
    for env in environments:
        if env == "CPU Stress":
            parameters["CPU Stress"] = {"value": cpu_stress_val}
        elif env == "Memory Stress":
            parameters["Memory Stress"] = {"value": f"{stress_mb}M"}
        elif env == "Network Delay":
            parameters["Network Delay"] = {"value": delay_ms}
        elif env == "Network Loss":
            parameters["Network Loss"] = {"value": loss_val}
        elif env == "Pod Kill":
            parameters["Pod Kill"] = {"value": "1", "target": app_name}
        elif env == "Network Partition":
            parameters["Network Partition"] = {"value": "1", "target": app_name}
        elif env == "Node Failure":
            parameters["Node Failure"] = {"value": "1", "node": "simulation-node"}

    return {"environments": parameters}


class BinarySearchSession:
    """
    Manages state across binary search iterations for a target stress parameter.
    """
    def __init__(self, parameter_name, low, high, unit="", threshold=16, max_iterations=8):
        self.parameter_name = parameter_name
        self.low = low
        self.high = high
        self.unit = unit
        self.threshold = threshold
        self.max_iterations = max_iterations
        self.iteration = 0
        self.best_passing_value = low
        self.history = []
        self.converged = False

    def next_value(self):
        """Calculates midpoint value for the next trial."""
        mid = (self.low + self.high) // 2
        return mid

    def record_result(self, tested_value, passed, reason="", chaos_vector=None):
        """Records trial result and adjusts [low, high] search bounds with step tracking."""
        self.iteration += 1
        prev_low = self.low
        prev_high = self.high

        if passed:
            self.best_passing_value = tested_value
            # App survived; push higher to find breaking point
            self.low = tested_value
            step_taken = f"Raised Lower Bound: [{prev_low}{self.unit}, {prev_high}{self.unit}] → [{self.low}{self.unit}, {self.high}{self.unit}] (Pushed stress higher)"
        else:
            # App failed; reduce stress
            self.high = tested_value
            step_taken = f"Contracted Upper Bound: [{prev_low}{self.unit}, {prev_high}{self.unit}] → [{self.low}{self.unit}, {self.high}{self.unit}] (Backed off stress)"

        diff = self.high - self.low
        if diff <= self.threshold or self.iteration >= self.max_iterations:
            self.converged = True

        next_mid = ((self.low + self.high) // 2) if not self.converged else None

        entry = {
            "iteration": self.iteration,
            "parameter": self.parameter_name,
            "value": tested_value,
            "tested_value": f"{tested_value}{self.unit}",
            "display": f"{tested_value}{self.unit}",
            "passed": passed,
            "reason": reason,
            "previous_bounds": [f"{prev_low}{self.unit}", f"{prev_high}{self.unit}"],
            "new_bounds": [f"{self.low}{self.unit}", f"{self.high}{self.unit}"],
            "difference": diff,
            "difference_str": f"{diff}{self.unit}",
            "step_taken": step_taken,
            "next_midpoint": f"{next_mid}{self.unit}" if next_mid is not None else None,
            "converged": self.converged,
            "chaos_vector": chaos_vector or {}
        }
        self.history.append(entry)
        return entry

    def summary(self):
        """Returns the final convergence verdict and recommended values."""
        return {
            "parameter": self.parameter_name,
            "iterations_run": self.iteration,
            "converged": self.converged,
            "breaking_point_threshold": f"{self.high}{self.unit}",
            "max_safe_tolerance": f"{self.best_passing_value}{self.unit}",
            "history": self.history
        }
