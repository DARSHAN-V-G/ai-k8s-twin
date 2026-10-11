import os
import sys

sys.path.append(os.path.dirname(__file__))

from services.binary_search_service import (
    calculate_bounds,
    evaluate_sla,
    calculate_recommended_config,
    generate_heuristic_parameters,
    BinarySearchSession,
    MultiParamSearchSession
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
    assert bounds["Memory Stress"]["low"] == 1
    assert bounds["CPU Stress"]["high"] == 100
    assert bounds["Network Delay"]["high"] == 1500
    assert bounds["Network Loss"]["high"] == 15.0
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
    assert bounds["Memory Stress"]["low"] == 1
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



def test_binary_search_session_no_success_searches_down_to_one():
    # If no trial passes, it must continue searching downward until diff <= 1
    session = BinarySearchSession(
        parameter_name="Memory Stress",
        low=1,
        high=134,
        unit="M",
        threshold=16,
        max_iterations=10
    )

    # Simulated breaking point = 0 (every trial breaches / OOMKilled)
    while not session.converged:
        val = session.next_value()
        session.record_result(val, False, "Simulated OOMKilled")

    summary = session.summary()
    assert summary["converged"]
    assert not session.has_passed
    last_diff = session.history[-1]["difference"]
    assert last_diff <= 1, f"Expected diff <= 1 when no trial passed, got {last_diff}"
    print(f"test_binary_search_session_no_success_searches_down_to_one PASSED: search continued until diff={last_diff}M <= 1M")


def test_multi_param_search_session_attribution():
    bounds = {
        "Memory Stress": {"low": 1, "high": 128, "unit": "M", "threshold": 16},
        "CPU Stress": {"low": 10, "high": 100, "unit": "%", "threshold": 5},
        "Network Delay": {"low": 10, "high": 1500, "unit": "ms", "threshold": 25},
        "Network Loss": {"low": 0.5, "high": 15.0, "unit": "%", "threshold": 0.5}
    }
    multi_session = MultiParamSearchSession(bounds=bounds, max_iterations=8)
    v1 = multi_session.next_vector()
    assert v1["RAM"] == 64
    assert v1["CPU"] == 55
    assert v1["DELAY"] == 755
    assert v1["LOSS"] == 7.8

    # 1. Breach due to OOMKilled -> Culprit must be RAM
    entry1 = multi_session.record_trial(
        tested_vector=v1,
        passed=False,
        metrics={"oom_killed": True}
    )
    assert entry1["culprit"] == "RAM"
    assert multi_session.sessions["RAM"].high == 64
    # Other dimensions must hold steady
    assert multi_session.sessions["CPU"].high == 100
    assert multi_session.sessions["DELAY"].high == 1500
    assert multi_session.sessions["LOSS"].high == 15.0

    # 2. Next trial breaches due to Network Loss > 1.0% -> Culprit must be LOSS
    v2 = multi_session.next_vector()
    entry2 = multi_session.record_trial(
        tested_vector=v2,
        passed=False,
        k6_result={"status": "completed", "error_rate_percent": 6.5, "p95_ms": 200.0}
    )
    assert entry2["culprit"] == "LOSS"
    assert multi_session.sessions["LOSS"].high == v2["LOSS"]
    # RAM and DELAY hold steady
    assert multi_session.sessions["RAM"].high == 64
    assert multi_session.sessions["DELAY"].high == 1500

    # 3. Next trial breaches due to P95 latency > 1000ms -> Culprit must be DELAY
    v3 = multi_session.next_vector()
    entry3 = multi_session.record_trial(
        tested_vector=v3,
        passed=False,
        k6_result={"status": "completed", "error_rate_percent": 0.0, "p95_ms": 1350.0}
    )
    assert entry3["culprit"] == "DELAY"
    assert multi_session.sessions["DELAY"].high == v3["DELAY"]

    # 4. Trial passes -> lower bounds should advance for active dimensions
    v4 = multi_session.next_vector()
    entry4 = multi_session.record_trial(
        tested_vector=v4,
        passed=True,
        k6_result={"status": "completed", "error_rate_percent": 0.0, "p95_ms": 150.0}
    )
    assert entry4["culprit"] is None
    assert multi_session.sessions["RAM"].low == v4["RAM"]
    assert multi_session.sessions["CPU"].low == v4["CPU"]
    assert multi_session.sessions["DELAY"].low == v4["DELAY"]
    assert multi_session.sessions["LOSS"].low == v4["LOSS"]

    summary = multi_session.summary()
    assert "optimal_values" in summary
    assert "RAM" in summary["optimal_values"]
    assert "CPU" in summary["optimal_values"]
    assert "DELAY" in summary["optimal_values"]
    assert "LOSS" in summary["optimal_values"]
    print("test_multi_param_search_session_attribution PASSED")


def test_multi_param_stagnation_and_frozen_culprit_termination():
    bounds = {
        "Memory Stress": {"low": 1, "high": 134, "unit": "M", "threshold": 16},
        "CPU Stress": {"low": 10, "high": 100, "unit": "%", "threshold": 5},
        "Network Delay": {"low": 10, "high": 1500, "unit": "ms", "threshold": 25},
        "Network Loss": {"low": 0.5, "high": 15.0, "unit": "%", "threshold": 0.5}
    }
    multi_session = MultiParamSearchSession(bounds=bounds, max_iterations=10)

    # Trial 1: RAM 67M -> PASS
    v1 = multi_session.next_vector()
    multi_session.record_trial(v1, True, k6_result={"status": "completed", "error_rate_percent": 0.0, "p95_ms": 100.0})

    # Trial 2: RAM 100M -> PASS
    v2 = multi_session.next_vector()
    multi_session.record_trial(v2, True, k6_result={"status": "completed", "error_rate_percent": 0.0, "p95_ms": 100.0})

    # Manually converge RAM at [100, 100] (delta 0)
    multi_session.sessions["RAM"].low = 100
    multi_session.sessions["RAM"].high = 100
    multi_session.sessions["RAM"].converged = True
    multi_session.sessions["RAM"].best_passing_value = 100

    # Run remaining trials until converged
    while not multi_session.converged and multi_session.iteration < 10:
        val = multi_session.next_vector()
        multi_session.record_trial(val, False, metrics={"oom_killed": True})

    # The session MUST converge and stop well before max_iterations (10)
    assert multi_session.converged, "Expected multi_session to converge when culprit reached delta 0"
    assert multi_session.iteration <= 6, f"Expected iteration <= 6, got {multi_session.iteration}"

    summary = multi_session.summary()
    assert summary["converged"]
    assert summary["optimal_values"]["RAM"] == "100M"
    print(f"test_multi_param_stagnation_and_frozen_culprit_termination PASSED (terminated cleanly in {multi_session.iteration} iterations)")


def test_calculate_recommended_config():
    # 1. Real measured telemetry metrics: peak memory 28 MiB, peak cpu 117m
    metrics = {
        "memory_max": 28 * 1024 * 1024,
        "memory_avg": 24 * 1024 * 1024,
        "cpu_max": 0.117,
        "cpu_avg": 0.050
    }
    rec1 = calculate_recommended_config(metrics=metrics)
    assert rec1["memory_limit"] == "35Mi"   # int(28 * 1.25) = 35Mi
    assert rec1["memory_request"] == "24Mi"
    assert rec1["cpu_limit"] == "146m"      # int(117 * 1.25) = 146m
    assert rec1["cpu_request"] == "50m"

    # 2. Fallback when telemetry is absent
    rec2 = calculate_recommended_config(metrics=None, default_mem_mb=32, default_cpu_m=50)
    assert rec2["memory_limit"] == "40Mi"   # int(32 * 1.25) = 40Mi
    assert rec2["memory_request"] == "26Mi" # int(32 * 0.8) = 26Mi
    assert rec2["cpu_limit"] == "62m"       # int(50 * 1.25) = 62m
    assert rec2["cpu_request"] == "40m"     # int(50 * 0.8) = 40m

    # 3. Dual metrics: baseline request from Trial 01 (18Mi) and peak limit from Trial 02 (25Mi)
    t1_metrics = {"memory_max": 18 * 1024 * 1024, "memory_avg": 18 * 1024 * 1024, "cpu_max": 0.025, "cpu_avg": 0.025}
    t2_metrics = {"memory_max": 25 * 1024 * 1024, "memory_avg": 20 * 1024 * 1024, "cpu_max": 0.050, "cpu_avg": 0.035}
    rec3 = calculate_recommended_config(metrics=t2_metrics, baseline_metrics=t1_metrics)
    assert rec3["memory_request"] == "18Mi"  # True minimal healthy baseline
    assert rec3["memory_limit"] == "32Mi"    # Peak chaos survived + 25% buffer (max(32, 25*1.25) = 32)
    assert rec3["cpu_request"] == "25m"
    assert rec3["cpu_limit"] == "62m"

    print("test_calculate_recommended_config PASSED")


if __name__ == "__main__":
    test_calculate_bounds_with_limits()
    test_calculate_bounds_without_limits()
    test_generate_heuristic_parameters_validation()
    test_evaluate_sla()
    test_binary_search_session_convergence()
    test_binary_search_session_no_success_searches_down_to_one()
    test_multi_param_search_session_attribution()
    test_multi_param_stagnation_and_frozen_culprit_termination()
    test_calculate_recommended_config()
    print("\nALL BINARY SEARCH ENGINE TESTS PASSED!")


