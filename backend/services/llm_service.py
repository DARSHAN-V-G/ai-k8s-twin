import os
import json

from services.binary_search_service import generate_heuristic_parameters


ALLOWED_ENVIRONMENTS = {
    "Pod Kill",
    "CPU Stress",
    "Memory Stress",
    "Network Delay",
    "Network Loss",
    "Network Partition",
    "Node Failure"
}


def generate_environment_parameters(
    application,
    environments,
    cpu,
    memory,
    vus,
    duration
):
    """
    Generates chaos environment parameters deterministically without requiring external LLM API calls.
    Maintains backward compatibility with all existing orchestrator and test callers.
    """
    if not isinstance(environments, list):
        raise ValueError(
            "Environments must be a list."
        )

    for environment in environments:
        if environment not in ALLOWED_ENVIRONMENTS:
            raise ValueError(
                f"Invalid environment: {environment}"
            )

    # Use deterministic heuristic engine
    return generate_heuristic_parameters(
        application=application,
        environments=environments,
        cpu=cpu,
        memory=memory,
        vus=vus,
        duration=duration
    )
