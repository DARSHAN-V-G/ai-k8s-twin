import os
import sys

sys.path.append(os.path.dirname(__file__))

from services.binary_search_service import (
    calculate_bounds,
    evaluate_sla,
    generate_heuristic_parameters,
    BinarySearchSession
)
from services.environment_validator import validate_environment_parameters


def test_calculate_bounds_with_limits():
    app = {
        "name": "payment",
        "containers": [{
            "name": "payment",
            "resources": {
                "limits": {"memory": "128Mi", "cpu": "500m"}
            }
        }]
    }
    bounds = calculate_bounds(app, cluster_cpu="2", cluster_memory="4Gi")
    assert bounds["Memory Stress"]["high"] == 134 or bounds["Memory Stress"]["high"] == 128 or bounds["Memory Stress"]["high"] > 100
    assert bounds["Memory Stress"]["low"] == 16
    assert bounds["CPU Stress"]["high"] == 100
    assert bounds["Network Delay"]["high"] == 2000
    print("test_calculate_bounds_with_limits PASSED")


def test_calculate_bounds_without_limits():
    app = {
        "name": "payment",
        "containers": [{
            "name": "payment",
            "resources": {}
        }]
    }
    bounds = calculate_bounds(app, cluster_cpu="4", cluster_memory="8Gi")
    assert bounds["Memory Stress"]["high"] > 0
    assert bounds["Memory Stress"]["low"] == 16
    print("test_calculate_bounds_without_limits PASSED")


def test_generate_heuristic_parameters_validation():
    app = {
        "kind": "Deployment",
        "name": "simulation-payment",
        "namespace": "simulation-resource",
        "replicas": 1,
        "containers": [{
            "name": "payment",
            "image": "nginx:latest",
            "ports": [{"containerPort": 80}],
            "resources": {
                "requests": {"cpu": "100m", "memory": "64Mi"},
                "limits": {"cpu": "500m", "memory": "128Mi"}
            }
        }]
    }
    environments = [
        "CPU Stress",
        "Memory Stress",
        "Network Delay",
        "Network Loss",
        "Pod Kill",
        "Network Partition",
        "Node Failure"
    ]
    params = generate_heuristic_parameters(
        application=app,
        environments=environments,
        cpu="2",
        memory="4Gi",
        vus="10",
        duration="30s"
    )

    assert "environments" in params
    assert "CPU Stress" in params["environments"]
    assert "Memory Stress" in params["environments"]
    assert "Network Delay" in params["environments"]
    assert "Network Loss" in params["environments"]
    assert "Pod Kill" in params["environments"]
    assert params["environments"]["Pod Kill"].get("value") == "1"
    assert "Network Partition" in params["environments"]
    assert "Node Failure" in params["environments"]

    # Validate against environment_validator
    valid, message = validate_environment_parameters(params, app)
    assert valid, f"Validation failed: {message}"
    print(f"test_generate_heuristic_parameters_validation PASSED: {message}")


def test_evaluate_sla():
    # Passing k6 result
    good_k6 = {
        "status": "completed",
        "error_rate_percent": 0.5,
        "p95_ms": 120.0
    }
    passed, reason = evaluate_sla(good_k6)
    assert passed
    assert "SLA satisfied" in reason

    # Breaching error rate
    bad_err_k6 = {
        "status": "completed",
        "error_rate_percent": 3.2,
        "p95_ms": 150.0
    }
    passed, reason = evaluate_sla(bad_err_k6)
    assert not passed
    assert "Error rate" in reason

    # Breaching latency
    bad_lat_k6 = {
        "status": "completed",
        "error_rate_percent": 0.0,
        "p95_ms": 450.0
    }
    passed, reason = evaluate_sla(bad_lat_k6)
    assert not passed
    assert "P95 latency" in reason

    # OOMKilled
    passed, reason = evaluate_sla(good_k6, metrics={"oom_killed": True})
    assert not passed
    assert "OOMKilled" in reason
    print("test_evaluate_sla PASSED")


def test_binary_search_session_convergence():
    session = BinarySearchSession(
        parameter_name="Memory Stress",
        low=16,
        high=134,
        unit="M",
        threshold=16,
        max_iterations=8
    )

    # Simulated breaking point at 90M
    breaking_point = 90

    while not session.converged:
        val = session.next_value()
        test_passed = val <= breaking_point
        chaos_vector = {
            "memory": f"{val}M",
            "cpu": "60%",
            "delay": "100ms",
            "loss": "3%",
            "partition": "shippingservice"
        }
        entry = session.record_result(val, test_passed, "simulation", chaos_vector=chaos_vector)
        assert "difference" in entry
        assert "chaos_vector" in entry

    summary = session.summary()
    assert summary["converged"]
    last_diff = session.history[-1]["difference"]
    assert last_diff <= 16
    assert int(summary["max_safe_tolerance"].rstrip("M")) <= breaking_point
    print(f"test_binary_search_session_convergence PASSED: converged at {summary['max_safe_tolerance']} in {summary['iterations_run']} iterations (diff={last_diff}M <= 16M)")



if __name__ == "__main__":
    test_calculate_bounds_with_limits()
    test_calculate_bounds_without_limits()
    test_generate_heuristic_parameters_validation()
    test_evaluate_sla()
    test_binary_search_session_convergence()
    print("\nALL BINARY SEARCH ENGINE TESTS PASSED!")
