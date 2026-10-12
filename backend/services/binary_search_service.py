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
            "low": 1,
            "high": max_mem_mb,
            "unit": "Mi",
            "threshold": 1  # Stop search when difference <= 16M (or <= 1M if no trial has passed)
        },
        "CPU Stress": {
            "low": 10,
            "high": 100,
            "unit": "",
            "threshold": 1   # Stop search when within 5%
        },
        "Network Delay": {
            "low": 10,
            "high": 400,
            "unit": "ms",
            "threshold": 1  # Stop search when within 20ms
        },
        "Network Loss": {
            "low": 0.0,
            "high": 1.0,
            "unit": "%",
            "threshold": 0.01  # Stop search when within 0.1%
        }
    }

    return bounds


def calculate_recommended_config(metrics=None, baseline_metrics=None, default_mem_mb=32, default_cpu_m=50, **kwargs):
    """
    Computes recommended Kubernetes resource limits and requests based on
    actual observed telemetry metrics (cAdvisor / kubelet):
    - Memory Limit: peak observed memory under chaos + 25% safety buffer (minimum 32Mi)
    - Memory Request: average/baseline observed memory under low/normal conditions (minimum 16Mi)
    - CPU Limit: peak observed CPU under chaos + 25% safety buffer (minimum 50m)
    - CPU Request: average/baseline observed CPU under normal conditions (minimum 25m)
    """
    metrics = metrics or {}
    base_metrics = baseline_metrics or metrics

    peak_mem_bytes = metrics.get("memory_max") or metrics.get("memory_avg")
    avg_mem_bytes = base_metrics.get("memory_avg") or base_metrics.get("memory_max")

    peak_cpu_cores = metrics.get("cpu_max") or metrics.get("cpu_avg")
    avg_cpu_cores = base_metrics.get("cpu_avg") or base_metrics.get("cpu_max")

    if peak_mem_bytes:
        peak_mem_mb = max(16, int(round(peak_mem_bytes / (1024 * 1024))))
    else:
        peak_mem_mb = default_mem_mb

    if avg_mem_bytes:
        avg_mem_mb = max(16, int(round(avg_mem_bytes / (1024 * 1024))))
    else:
        avg_mem_mb = max(16, int(round(peak_mem_mb * 0.8)))

    if peak_cpu_cores:
        peak_cpu_m = max(50, int(round(peak_cpu_cores * 1000)))
    else:
        peak_cpu_m = default_cpu_m

    if avg_cpu_cores:
        avg_cpu_m = max(25, int(round(avg_cpu_cores * 1000)))
    else:
        avg_cpu_m = max(25, int(round(peak_cpu_m * 0.8)))

    mem_limit = max(32, int(round(peak_mem_mb * 1.25)))
    mem_req = max(16, avg_mem_mb)

    cpu_limit = max(50, int(round(peak_cpu_m * 1.25)))
    cpu_req = max(25, avg_cpu_m)

    return {
        "memory_limit": f"{mem_limit}Mi",
        "memory_request": f"{mem_req}Mi",
        "cpu_limit": f"{cpu_limit}m",
        "cpu_request": f"{cpu_req}m"
    }


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
            parameters["Memory Stress"] = {"value": f"{stress_mb}Mi"}
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
    def __init__(self, parameter_name, low=1, high=128, unit="", threshold=16, max_iterations=10, is_float=False):
        self.parameter_name = parameter_name
        self.is_float = is_float
        self.low = float(low) if is_float else int(low)
        self.high = float(high) if is_float else int(high)
        self.unit = unit
        self.threshold = float(threshold) if is_float else int(threshold)
        self.max_iterations = max_iterations
        self.iteration = 0
        self.has_passed = False
        self.best_passing_value = float(low) if is_float else int(low)
        self.history = []
        self.converged = False

    def next_value(self):
        """Calculates midpoint value for the next trial."""
        if self.is_float:
            mid = round((self.low + self.high) / 2.0, 1)
            if mid == self.low and self.low < self.high:
                mid = round(self.low + 0.1, 1)
            return mid
        mid = (self.low + self.high) // 2
        if mid == self.low and self.low < self.high:
            mid = self.low + 1
        return mid

    def record_result(self, tested_value, passed, reason="", chaos_vector=None):
        """Records trial result and adjusts [low, high] search bounds with step tracking."""
        self.iteration += 1
        prev_low = self.low
        prev_high = self.high

        if passed:
            self.has_passed = True
            self.best_passing_value = tested_value
            # App survived; push higher to find breaking point
            self.low = tested_value
            step_taken = f"Raised Lower Bound: [{prev_low}{self.unit}, {prev_high}{self.unit}] → [{self.low}{self.unit}, {self.high}{self.unit}] (Pushed stress higher)"
        else:
            # App failed; reduce stress
            self.high = tested_value
            step_taken = f"Contracted Upper Bound: [{prev_low}{self.unit}, {prev_high}{self.unit}] → [{self.low}{self.unit}, {self.high}{self.unit}] (Backed off stress)"

        diff = round(self.high - self.low, 1) if self.is_float else (self.high - self.low)
        effective_threshold = self.threshold if self.has_passed else (0.5 if self.is_float else 1)
        if diff <= effective_threshold or self.iteration >= self.max_iterations:
            self.converged = True

        next_mid = self.next_value() if not self.converged else None

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
            "has_passed": self.has_passed,
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


def attribute_failure_cause(k6_result, metrics=None, max_error_rate_percent=1.0, max_p95_ms=1000.0):
    """
    Identifies which of the 4 chaos parameters triggered an SLA breach:
    - OOMKilled -> RAM
    - Error rate exceeded -> LOSS
    - P95 latency exceeded -> DELAY
    - CPU throttling / saturation -> CPU
    """
    if metrics and metrics.get("oom_killed"):
        return "RAM", "Container crashed with OOMKilled."

    if not k6_result or k6_result.get("status") == "failed":
        reason = k6_result.get("reason", "k6 test execution failed.") if k6_result else "No k6 telemetry."
        reason_low = str(reason).lower()
        if "timeout" in reason_low or "deadline" in reason_low:
            return "DELAY", f"Latency timeout failure: {reason}"
        return "LOSS", f"Request execution failure: {reason}"

    error_rate = k6_result.get("error_rate_percent", 0.0)
    p95_latency = k6_result.get("p95_ms", 0.0)

    if error_rate > max_error_rate_percent:
        return "LOSS", f"Error rate {error_rate:.2f}% breached threshold ({max_error_rate_percent}%)."

    if p95_latency > max_p95_ms:
        return "DELAY", f"P95 latency {p95_latency:.1f}ms breached threshold ({max_p95_ms}ms)."

    if metrics and metrics.get("cpu_throttled"):
        return "CPU", "Severe CPU throttling detected."

    return "RAM", "General performance degradation."


class MultiParamSearchSession:
    """
    Manages active bounds, binary search sessions, and failure attribution across all 4 parameters:
    RAM, CPU, DELAY, and LOSS.
    """
    def __init__(self, bounds, max_iterations=10):
        self.bounds = bounds
        self.max_iterations = max_iterations
        self.iteration = 0
        self.history = []
        self.tested_vectors = []
        self.best_passing_vector = None
        self._converged_forced = False

        ram_cfg = bounds.get("Memory Stress", {"low": 1, "high": 128, "unit": "Mi", "threshold": 16})
        cpu_cfg = bounds.get("CPU Stress", {"low": 10, "high": 100, "unit": "%", "threshold": 5})
        delay_cfg = bounds.get("Network Delay", {"low": 10, "high": 400, "unit": "ms", "threshold": 20})
        loss_cfg = bounds.get("Network Loss", {"low": 0.0, "high": 1.0, "unit": "%", "threshold": 0.1})

        self.sessions = {
            "RAM": BinarySearchSession("RAM", low=ram_cfg.get("low", 1), high=ram_cfg["high"], unit=ram_cfg.get("unit", "Mi"), threshold=ram_cfg.get("threshold", 16), max_iterations=max_iterations, is_float=False),
            "CPU": BinarySearchSession("CPU", low=cpu_cfg.get("low", 10), high=cpu_cfg["high"], unit=cpu_cfg.get("unit", "%"), threshold=cpu_cfg.get("threshold", 5), max_iterations=max_iterations, is_float=False),
            "DELAY": BinarySearchSession("DELAY", low=delay_cfg.get("low", 10), high=delay_cfg["high"], unit=delay_cfg.get("unit", "ms"), threshold=delay_cfg.get("threshold", 20), max_iterations=max_iterations, is_float=False),
            "LOSS": BinarySearchSession("LOSS", low=loss_cfg.get("low", 0.0), high=loss_cfg["high"], unit=loss_cfg.get("unit", "%"), threshold=loss_cfg.get("threshold", 0.1), max_iterations=max_iterations, is_float=True),
        }

    @property
    def converged(self):
        return self._converged_forced or all(s.converged for s in self.sessions.values()) or self.iteration >= self.max_iterations

    def next_vector(self):
        """Returns the midpoint values for all 4 parameters for the next trial."""
        return {
            "RAM": self.sessions["RAM"].next_value() if not self.sessions["RAM"].converged else self.sessions["RAM"].best_passing_value,
            "CPU": self.sessions["CPU"].next_value() if not self.sessions["CPU"].converged else self.sessions["CPU"].best_passing_value,
            "DELAY": self.sessions["DELAY"].next_value() if not self.sessions["DELAY"].converged else self.sessions["DELAY"].best_passing_value,
            "LOSS": self.sessions["LOSS"].next_value() if not self.sessions["LOSS"].converged else self.sessions["LOSS"].best_passing_value,
        }

    def record_trial(self, tested_vector, passed, k6_result=None, metrics=None, reason="", recommended_config=None):
        self.iteration += 1
        culprit = None
        trial_reason = reason
        self.tested_vectors.append(dict(tested_vector))

        if recommended_config is None:
            recommended_config = calculate_recommended_config(metrics=metrics)

        if passed:
            # All SLA passed: Advance lower bounds for all non-converged parameters
            self.best_passing_vector = dict(tested_vector)
            step_parts = []
            for name, sess in self.sessions.items():
                if not sess.converged:
                    sess.has_passed = True
                    sess.best_passing_value = tested_vector[name]
                    prev_low = sess.low
                    sess.low = tested_vector[name]
                    diff = round(sess.high - sess.low, 1) if sess.is_float else (sess.high - sess.low)
                    if diff <= sess.threshold:
                        sess.converged = True
                    step_parts.append(f"{name}: [{prev_low}{sess.unit} -> {sess.low}{sess.unit}]")
            step_taken = "Passed SLA. Advanced limits: " + (", ".join(step_parts) if step_parts else "All limits converged.")
            if not trial_reason:
                trial_reason = "SLA satisfied across all tested stress dimensions."
        else:
            # Breached SLA: identify culprit and check if culprit is already at safe floor
            culprit, breach_reason = attribute_failure_cause(k6_result, metrics)
            if not trial_reason:
                trial_reason = breach_reason

            sess = self.sessions[culprit]
            is_culprit_frozen = (sess.high <= sess.low) or (sess.converged and tested_vector[culprit] <= sess.best_passing_value)

            if is_culprit_frozen:
                # The blamed parameter is already at its verified safe limit.
                # The failure was provoked by other elevated non-converged stressors (e.g. CPU or Delay).
                elevated_adjusted = []
                for name, other_sess in self.sessions.items():
                    if name != culprit and not other_sess.converged and tested_vector[name] > other_sess.low:
                        other_sess.high = tested_vector[name]
                        diff_other = round(other_sess.high - other_sess.low, 1) if other_sess.is_float else (other_sess.high - other_sess.low)
                        effective_thresh = other_sess.threshold if other_sess.has_passed else (0.5 if other_sess.is_float else 1)
                        if diff_other <= effective_thresh or other_sess.high <= other_sess.low:
                            other_sess.converged = True
                        elevated_adjusted.append(f"{name}: [{other_sess.low}{other_sess.unit}, {other_sess.high}{other_sess.unit}]")

                if not elevated_adjusted:
                    # No parameter can make further progress; terminate search immediately
                    self._converged_forced = True
                    step_taken = f"Converged: {culprit} reached safe floor ({sess.low}{sess.unit}). Compound stress frontier reached."
                else:
                    step_taken = f"{culprit} is at safe floor ({sess.low}{sess.unit}). Backed off elevated compound stressors: {', '.join(elevated_adjusted)}."
            else:
                prev_high = sess.high
                sess.high = tested_vector[culprit]
                diff = round(sess.high - sess.low, 1) if sess.is_float else (sess.high - sess.low)
                effective_threshold = sess.threshold if sess.has_passed else (0.5 if sess.is_float else 1)
                if diff <= effective_threshold or sess.high <= sess.low:
                    sess.converged = True
                step_taken = f"Contracted {culprit} Upper Bound: [{sess.low}{sess.unit}, {prev_high}{sess.unit}] → [{sess.low}{sess.unit}, {sess.high}{sess.unit}] ({breach_reason}). Other dimensions held steady."

        # Vector Stagnation & Fixed-Point Detector
        next_vector = self.next_vector() if not self.converged else None
        if next_vector is not None:
            if next_vector == tested_vector or next_vector in self.tested_vectors:
                self._converged_forced = True
                next_vector = None
                step_taken += " Reached fixed-point boundary (no further unique vectors). Converged."

        vector_display = {
            "memory": f"{tested_vector['RAM']}Mi",
            "cpu": f"{tested_vector['CPU']}%",
            "delay": f"{tested_vector['DELAY']}ms",
            "loss": f"{tested_vector['LOSS']}%"
        }

        entry = {
            "iteration": self.iteration,
            "vector": tested_vector,
            "chaos_vector": vector_display,
            "passed": passed,
            "sla_passed": passed,
            "culprit": culprit,
            "reason": trial_reason,
            "step_taken": step_taken,
            "next_vector": next_vector,
            "next_midpoint": f"{next_vector['RAM']}Mi" if next_vector else None,
            "converged": self.converged,
            "tested_value": f"{tested_vector['RAM']}Mi",
            "recommended_config": recommended_config,
            "difference": self.sessions["RAM"].high - self.sessions["RAM"].low,
            "parameters_state": {
                name: {
                    "low": s.low,
                    "high": s.high,
                    "unit": s.unit,
                    "diff": round(s.high - s.low, 1) if s.is_float else (s.high - s.low),
                    "converged": s.converged,
                    "best_safe": s.best_passing_value
                }
                for name, s in self.sessions.items()
            }
        }
        self.history.append(entry)
        return entry

    def summary(self):
        optimal_vals = {
            "RAM": f"{self.sessions['RAM'].best_passing_value}{self.sessions['RAM'].unit}",
            "CPU": f"{self.sessions['CPU'].best_passing_value}{self.sessions['CPU'].unit}",
            "DELAY": f"{self.sessions['DELAY'].best_passing_value}{self.sessions['DELAY'].unit}",
            "LOSS": f"{self.sessions['LOSS'].best_passing_value}{self.sessions['LOSS'].unit}"
        }
        if self.best_passing_vector:
            optimal_vals = {
                "RAM": f"{self.best_passing_vector['RAM']}{self.sessions['RAM'].unit}",
                "CPU": f"{self.best_passing_vector['CPU']}{self.sessions['CPU'].unit}",
                "DELAY": f"{self.best_passing_vector['DELAY']}{self.sessions['DELAY'].unit}",
                "LOSS": f"{self.best_passing_vector['LOSS']}{self.sessions['LOSS'].unit}"
            }
        return {
            "iterations_run": self.iteration,
            "converged": self.converged,
            "optimal_values": optimal_vals,
            "best_passing_vector": self.best_passing_vector,
            "parameters": {
                name: s.summary() for name, s in self.sessions.items()
            },
            "history": self.history
        }
