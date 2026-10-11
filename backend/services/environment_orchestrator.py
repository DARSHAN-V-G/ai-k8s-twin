import json
import os
import re
import shutil
import subprocess
import tempfile
import time

import yaml
from git import Repo
from services.binary_search_service import (
    generate_heuristic_parameters,
    calculate_bounds,
    evaluate_sla,
    calculate_recommended_config,
    BinarySearchSession,
    MultiParamSearchSession
)
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv


load_dotenv(
    os.path.join(
        os.path.dirname(
            os.path.dirname(__file__)
        ),
        ".env"
    )
)


REPOSITORY_DIRECTORY = os.path.expanduser(
    "~/ai-k8s-twin/temp_repository"
)

GENERATED_DIRECTORY = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "generated"
    )
)

CHAOS_DIRECTORY = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "chaos"
    )
)

ALLOWED_KINDS = {
    "Deployment",
    "StatefulSet",
    "DaemonSet"
}

ALLOWED_ENVIRONMENTS = {
    "Pod Kill",
    "CPU Stress",
    "Memory Stress",
    "Network Delay",
    "Network Loss",
    "Network Partition",
    "Node Failure"
}

FIVE_CHAOS_ENVIRONMENTS = [
    "CPU Stress",
    "Memory Stress",
    "Network Delay",
    "Network Loss",
    "Network Partition"
]

CHAOS_TEMPLATES = {
    "CPU Stress": "cpu-stress.yaml",
    "Memory Stress": "memory-stress.yaml",
    "Network Delay": "network-delay.yaml",
    "Network Loss": "network-packet-loss.yaml",
    "Network Partition": "network-partition.yaml",
    "Node Failure": "node-failure.yaml",
    "Pod Kill": "pod-kill.yaml"
}


def run_command(command):

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            result.stderr.strip()
            or "Command failed."
        )

    return result.stdout.strip()


def clone_repository(github_url):

    if os.path.exists(
        REPOSITORY_DIRECTORY
    ):

        print(
            "Removing previous temporary repository..."
        )

        shutil.rmtree(
            REPOSITORY_DIRECTORY
        )

    try:

        Repo.clone_from(
            github_url,
            REPOSITORY_DIRECTORY
        )

        return REPOSITORY_DIRECTORY

    except Exception:

        shutil.rmtree(
            REPOSITORY_DIRECTORY,
            ignore_errors=True
        )

        raise


def find_yaml_files(project_path):

    yaml_files = []

    for root, dirs, files in os.walk(
        project_path
    ):

        if ".git" in dirs:

            dirs.remove(".git")

        for file in files:

            if (
                file.endswith(".yaml")
                or file.endswith(".yml")
            ):

                yaml_files.append(
                    os.path.join(
                        root,
                        file
                    )
                )

    return yaml_files


def parse_yaml_file(file_path):

    resources = []

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        try:

            documents = yaml.safe_load_all(
                file
            )

            for document in documents:

                if not isinstance(
                    document,
                    dict
                ):

                    continue

                kind = document.get(
                    "kind"
                )

                if kind not in {
                    "Deployment",
                    "StatefulSet",
                    "DaemonSet",
                    "Service",
                    "ConfigMap",
                    "Secret",
                    "Ingress",
                    "Namespace"
                }:

                    continue

                resources.append({
                    "file": file_path,
                    "kind": kind,
                    "resource": document
                })

        except yaml.YAMLError:

            pass

    return resources


def analyze_resources(resources):

    applications = []

    for item in resources:

        resource = item[
            "resource"
        ]

        kind = item[
            "kind"
        ]

        metadata = resource.get(
            "metadata",
            {}
        )

        name = metadata.get(
            "name"
        )

        namespace = metadata.get(
            "namespace",
            "default"
        )

        application = {
            "kind": kind,
            "name": name,
            "namespace": namespace,
            "file": item["file"]
        }

        if kind in ALLOWED_KINDS:

            spec = resource.get(
                "spec",
                {}
            )

            application[
                "replicas"
            ] = spec.get(
                "replicas",
                1
            )

            application[
                "selector"
            ] = spec.get(
                "selector",
                {}
            )

            pod_template = spec.get(
                "template",
                {}
            )

            pod_metadata = pod_template.get(
                "metadata",
                {}
            )

            application[
                "labels"
            ] = pod_metadata.get(
                "labels",
                {}
            )

            pod_spec = pod_template.get(
                "spec",
                {}
            )

            containers = pod_spec.get(
                "containers",
                []
            )

            application[
                "containers"
            ] = []

            for container in containers:

                application[
                    "containers"
                ].append({
                    "name": container.get(
                        "name"
                    ),
                    "image": container.get(
                        "image"
                    ),
                    "ports": container.get(
                        "ports",
                        []
                    ),
                    "resources": container.get(
                        "resources",
                        {}
                    )
                })

        elif kind == "Service":

            spec = resource.get(
                "spec",
                {}
            )

            application[
                "selector"
            ] = spec.get(
                "selector"
            )

            application[
                "ports"
            ] = spec.get(
                "ports",
                []
            )

        applications.append(
            application
        )

    return applications


def get_workloads(applications):

    workloads = []

    seen = set()

    for application in applications:

        if application.get(
            "kind"
        ) not in ALLOWED_KINDS:

            continue

        key = (
            application.get("kind"),
            application.get("namespace"),
            application.get("name")
        )

        if key in seen:

            continue

        seen.add(
            key
        )

        workloads.append(
            application
        )

    if not workloads:

        raise RuntimeError(
            "No application workload found."
        )

    return workloads


def find_application_resource(
    application
):

    file_path = application.get(
        "file"
    )

    if not file_path:

        raise RuntimeError(
            "Application YAML file path is missing."
        )

    if not os.path.isfile(
        file_path
    ):

        raise FileNotFoundError(
            f"Application YAML file not found: "
            f"{file_path}"
        )

    expected_kind = application.get(
        "kind"
    )

    expected_name = application.get(
        "name"
    )

    expected_namespace = application.get(
        "namespace",
        "default"
    )

    release_file = os.path.join(
        os.path.dirname(
            os.path.dirname(
                file_path
            )
        ),
        "release",
        "kubernetes-manifests.yaml"
    )

    files_to_check = [
        release_file,
        file_path
    ]

    for candidate_file in files_to_check:

        if not os.path.isfile(
            candidate_file
        ):

            continue

        with open(
            candidate_file,
            "r",
            encoding="utf-8"
        ) as file:

            documents = yaml.safe_load_all(
                file
            )

            for document in documents:

                if not isinstance(
                    document,
                    dict
                ):

                    continue

                metadata = document.get(
                    "metadata",
                    {}
                )

                kind = document.get(
                    "kind"
                )

                name = metadata.get(
                    "name"
                )

                namespace = metadata.get(
                    "namespace",
                    "default"
                )

                if (
                    kind == expected_kind
                    and name == expected_name
                    and namespace == expected_namespace
                ):

                    return document

    raise RuntimeError(
        f"Could not find {expected_kind} "
        f"{expected_name} in repository manifests."
    )


def generate_optimized_deployment_yaml(
    application,
    recommended_config,
    optimal_tolerances=None
):
    """
    Finds the application's Kubernetes resource manifest, clones it,
    injects the recommended limits and requests, tunes probe timeouts,
    and writes it to generated/{name}-optimized-deployment.yaml.
    """
    import copy
    name = application.get("name")
    try:
        raw_doc = find_application_resource(application)
        doc = copy.deepcopy(raw_doc)
    except Exception:
        # Fallback to minimal deployment spec
        doc = {
            "apiVersion": "apps/v1",
            "kind": application.get("kind", "Deployment"),
            "metadata": {
                "name": name,
                "namespace": application.get("namespace", "default"),
                "labels": {"app": name}
            },
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "metadata": {"labels": {"app": name}},
                    "spec": {
                        "containers": [{
                            "name": "server",
                            "image": name
                        }]
                    }
                }
            }
        }

    spec = doc.get("spec", {})
    template_spec = spec.get("template", {}).get("spec", {}) if "template" in spec else spec
    containers = template_spec.get("containers", [])
    if containers:
        container = containers[0]
        container["resources"] = {
            "requests": {
                "cpu": recommended_config.get("cpu_request", "25m"),
                "memory": recommended_config.get("memory_request", "18Mi")
            },
            "limits": {
                "cpu": recommended_config.get("cpu_limit", "62m"),
                "memory": recommended_config.get("memory_limit", "32Mi")
            }
        }
        for probe_key in ["livenessProbe", "readinessProbe", "startupProbe"]:
            if probe_key in container and isinstance(container[probe_key], dict):
                current_timeout = container[probe_key].get("timeoutSeconds", 1)
                container[probe_key]["timeoutSeconds"] = max(current_timeout, 2)

    yaml_str = yaml.dump(doc, sort_keys=False, default_flow_style=False)

    out_file = os.path.join(
        GENERATED_DIRECTORY,
        f"{name}-optimized-deployment.yaml"
    )
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(yaml_str)

    return yaml_str, out_file


def deploy_application(
    application
):

    name = application.get(
        "name"
    )

    kind = application.get(
        "kind"
    )

    namespace = application.get(
        "namespace",
        "default"
    )

    if kind not in ALLOWED_KINDS:

        raise RuntimeError(
            f"Unsupported workload kind: {kind}"
        )

    print(
        f"\nDeploying {kind} {name} "
        f"to namespace {namespace}..."
    )

    resource = find_application_resource(
        application
    )

    pod_spec = (
        resource
        .get("spec", {})
        .get("template", {})
        .get("spec", {})
    )

    for container in pod_spec.get(
        "containers",
        []
    ):

        for probe_name in [
            "readinessProbe",
            "livenessProbe"
        ]:

            probe = container.get(
                probe_name
            )

            if isinstance(
                probe,
                dict
            ) and (
                "grpc" in probe
                or "httpGet" in probe
                or "tcpSocket" in probe
            ):

                probe[
                    "timeoutSeconds"
                ] = max(
                    probe.get(
                        "timeoutSeconds",
                        1
                    ),
                    5
                )

    service_account_name = pod_spec.get(
        "serviceAccountName"
    )

    documents = []

    if service_account_name:

        print(
            f"Required ServiceAccount: "
            f"{service_account_name}"
        )

        file_path = application.get(
            "file"
        )

        release_file = os.path.join(
            os.path.dirname(
                os.path.dirname(
                    file_path
                )
            ),
            "release",
            "kubernetes-manifests.yaml"
        )

        service_account = None

        if os.path.isfile(
            release_file
        ):

            with open(
                release_file,
                "r",
                encoding="utf-8"
            ) as file:

                for document in yaml.safe_load_all(
                    file
                ):

                    if not isinstance(
                        document,
                        dict
                    ):

                        continue

                    if document.get(
                        "kind"
                    ) != "ServiceAccount":

                        continue

                    metadata = document.get(
                        "metadata",
                        {}
                    )

                    sa_name = metadata.get(
                        "name"
                    )

                    sa_namespace = metadata.get(
                        "namespace",
                        "default"
                    )

                    if (
                        sa_name
                        == service_account_name
                        and sa_namespace
                        == namespace
                    ):

                        service_account = (
                            document
                        )

                        break

        if service_account is None:
            print(
                f"ServiceAccount {service_account_name} not found in release file. "
                f"Creating synthetic ServiceAccount..."
            )
            service_account = {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": service_account_name,
                    "namespace": namespace
                }
            }

        documents.append(
            service_account
        )

    if kind in {
        "Deployment",
        "StatefulSet"
    }:

        spec = resource.setdefault(
            "spec",
            {}
        )

        replicas = spec.get(
            "replicas",
            1
        )

        if replicas < 1:

            spec[
                "replicas"
            ] = 1

    documents.append(
        resource
    )

    temporary_file_path = None

    try:

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8"
        ) as temporary_file:

            yaml.safe_dump_all(
                documents,
                temporary_file,
                sort_keys=False
            )

            temporary_file_path = (
                temporary_file.name
            )

        print(
            "\nApplying Kubernetes resources..."
        )

        output = run_command([
            "kubectl",
            "apply",
            "-f",
            temporary_file_path
        ])

        if output:

            print(output)

    finally:

        if (
            temporary_file_path
            and os.path.exists(
                temporary_file_path
            )
        ):

            os.remove(
                temporary_file_path
            )

    print(
        f"\nWaiting for {kind} {name}..."
    )

    run_command([
        "kubectl",
        "rollout",
        "status",
        f"{kind.lower()}/{name}",
        "-n",
        namespace,
        "--timeout=60s"
    ])

    print(
        f"{kind} {name} is ready."
    )

    return {
        "name": name,
        "kind": kind,
        "namespace": namespace,
        "status": "deployed_and_ready"
    }


def prepare_llm_application(
    application
):

    return {
        "kind": application.get(
            "kind"
        ),
        "name": application.get(
            "name"
        ),
        "namespace": application.get(
            "namespace"
        ),
        "replicas": application.get(
            "replicas",
            1
        ),
        "labels": application.get(
            "labels",
            {}
        ),
        "containers": application.get(
            "containers",
            []
        )
    }


def generate_environment_parameters(
    application,
    environments,
    cpu,
    memory,
    vus,
    duration
):
    print("Using Deterministic Engine for chaos parameter calculation...")
    return generate_heuristic_parameters(
        application=application,
        environments=environments,
        cpu=cpu,
        memory=memory,
        vus=vus,
        duration=duration
    )


def parse_memory(value):

    if value is None:

        return None

    value = str(
        value
    ).strip()

    units = {
        "Ki": 1024,
        "Mi": 1024 ** 2,
        "Gi": 1024 ** 3,
        "K": 1000,
        "M": 1000 ** 2,
        "G": 1000 ** 3
    }

    for unit in sorted(
        units,
        key=len,
        reverse=True
    ):

        if value.endswith(
            unit
        ):

            try:

                number = float(
                    value[
                        :-len(unit)
                    ]
                )

                return (
                    number
                    * units[unit]
                )

            except ValueError:

                return None

    try:

        return float(
            value
        )

    except ValueError:

        return None


def parse_cpu(value):

    if value is None:

        return None

    value = str(
        value
    ).strip()

    if value.endswith("m"):

        try:

            return (
                float(
                    value[:-1]
                )
                / 1000
            )

        except ValueError:

            return None

    try:

        return float(
            value
        )

    except ValueError:

        return None


def validate_environment_parameters(
    result,
    application,
    selected_environments
):

    if not isinstance(
        result,
        dict
    ):

        return False, (
            "LLM result must be a dictionary."
        )

    environments = result.get(
        "environments"
    )

    if not isinstance(
        environments,
        dict
    ):

        return False, (
            "Missing environments object."
        )

    selected_set = set(
        selected_environments
    )

    returned_set = set(
        environments.keys()
    )

    if selected_set != returned_set:

        return False, (
            "LLM environments do not exactly "
            "match selected environments."
        )

    containers = application.get(
        "containers",
        []
    )

    if not containers:

        return False, (
            "Application has no containers."
        )

    container = containers[0]

    resources = container.get(
        "resources",
        {}
    )

    if not isinstance(
        resources,
        dict
    ):

        resources = {}

    limits = resources.get(
        "limits",
        {}
    )

    if not isinstance(
        limits,
        dict
    ):

        limits = {}

    cpu_limit = limits.get(
        "cpu"
    )

    memory_limit = limits.get(
        "memory"
    )

    for environment in selected_environments:

        parameters = environments.get(
            environment
        )

        if not isinstance(
            parameters,
            dict
        ):

            return False, (
                f"Parameters for {environment} "
                f"must be an object."
            )

        value = parameters.get(
            "value"
        )

        if value is None:

            return False, (
                f"Missing value for {environment}."
            )

        if environment == "CPU Stress":

            try:

                cpu_value = float(
                    value
                )

            except (
                ValueError,
                TypeError
            ):

                return False, (
                    "CPU Stress value must "
                    "be numeric."
                )

            if (
                cpu_value <= 0
                or cpu_value > 100
            ):

                return False, (
                    "CPU Stress must be "
                    "between 1 and 100."
                )

            if cpu_limit is not None:

                if parse_cpu(
                    cpu_limit
                ) is None:

                    return False, (
                        "Application CPU "
                        "limit is invalid."
                    )

        elif environment == "Memory Stress":

            memory_value = parse_memory(
                value
            )

            if memory_value is None:

                return False, (
                    "Memory Stress value "
                    "is invalid."
                )

            if memory_value <= 0:

                return False, (
                    "Memory Stress must be "
                    "greater than zero."
                )

            if memory_limit is not None:

                memory_limit_value = parse_memory(
                    memory_limit
                )

                if memory_limit_value is None:

                    return False, (
                        "Application memory "
                        "limit is invalid."
                    )

                if (
                    memory_value
                    > memory_limit_value
                ):

                    return False, (
                        "Memory Stress value "
                        "exceeds application "
                        "memory limit."
                    )

        elif environment == "Network Delay":

            match = re.fullmatch(
                r"(\d+)(ms|s)",
                str(value).strip()
            )

            if not match:

                return False, (
                    "Network Delay must "
                    "use ms or s."
                )

            delay_value = int(
                match.group(1)
            )

            unit = match.group(2)

            if unit == "s":

                delay_ms = (
                    delay_value * 1000
                )

            else:

                delay_ms = delay_value

            if delay_ms <= 0:

                return False, (
                    "Network Delay must "
                    "be greater than zero."
                )

            if delay_ms > 10000:

                return False, (
                    "Network Delay cannot "
                    "exceed 10 seconds."
                )

        elif environment == "Network Loss":

            try:

                loss_value = float(
                    value
                )

            except (
                ValueError,
                TypeError
            ):

                return False, (
                    "Network Loss must "
                    "be numeric."
                )

            if (
                loss_value <= 0
                or loss_value > 100
            ):

                return False, (
                    "Network Loss must be "
                    "greater than 0 and "
                    "at most 100."
                )

    return True, (
        "Environment parameters are valid."
    )


def create_template_environment():

    return Environment(
        loader=FileSystemLoader(
            CHAOS_DIRECTORY
        ),
        autoescape=False
    )


def generate_chaos_yaml(
    environment,
    parameters
):

    if environment not in CHAOS_TEMPLATES:

        raise ValueError(
            f"Unsupported environment: "
            f"{environment}"
        )

    template_environment = (
        create_template_environment()
    )

    template = template_environment.get_template(
        CHAOS_TEMPLATES[environment]
    )

    return template.render(
        **parameters
    )


def generate_compound_chaos_yaml(
    environments,
    parameters
):

    generated_files = []

    for environment in environments:

        if environment not in parameters:

            raise ValueError(
                f"Missing parameters for "
                f"{environment}"
            )

        yaml_content = generate_chaos_yaml(
            environment,
            parameters[environment]
        )

        generated_files.append({
            "environment": environment,
            "yaml": yaml_content
        })

    return generated_files


def get_target_app(
    application
):

    labels = application.get(
        "labels",
        {}
    )

    return labels.get(
        "app",
        application.get(
            "name"
        )
    )


def build_chaos_parameters(
    application,
    environments,
    parameters,
    duration,
    iteration=None
):

    namespace = application.get(
        "namespace",
        "default"
    )

    target_app = get_target_app(
        application
    )

    target_name = re.sub(
        r"[^a-z0-9-]+",
        "-",
        str(target_app).lower()
    ).strip("-")

    chaos_parameters = {}
    iter_suffix = f"-iter{iteration}" if iteration is not None else ""

    for environment in environments:

        value = parameters[
            "environments"
        ][environment].get(
            "value"
        )

        chaos_parameters[
            environment
        ] = {
            "chaos_name": (
                target_name
                + "-"
                + environment
                .lower()
                .replace(" ", "-")
                + iter_suffix
                + "-experiment"
            ),
            "namespace": namespace,
            "mode": "one",
            "target_app": target_app,
            "source_app": target_app,
            "target_mode": "one",
            "workers": 1,
            "duration": duration
        }

        if environment == "CPU Stress":

            chaos_parameters[
                environment
            ][
                "cpu_load"
            ] = value

        elif environment == "Memory Stress":

            chaos_parameters[
                environment
            ][
                "memory_size"
            ] = value

        elif environment == "Network Delay":

            chaos_parameters[
                environment
            ][
                "latency"
            ] = value

            chaos_parameters[
                environment
            ][
                "jitter"
            ] = "10ms"

            chaos_parameters[
                environment
            ][
                "correlation"
            ] = "0"

        elif environment == "Network Loss":

            chaos_parameters[
                environment
            ][
                "loss_percent"
            ] = value

            chaos_parameters[
                environment
            ][
                "correlation"
            ] = "0"

        elif environment == "Network Partition":

            chaos_parameters[
                environment
            ][
                "source_app"
            ] = target_app

            chaos_parameters[
                environment
            ][
                "target_app"
            ] = "recommendationservice" if target_app == "frontend" else target_app

        elif environment == "Pod Kill":

            chaos_parameters[
                environment
            ][
                "target_app"
            ] = target_app

        elif environment == "Node Failure":

            chaos_parameters[
                environment
            ][
                "node_name"
            ] = get_application_node(
                application
            )

    return chaos_parameters


def get_application_pod(
    application
):

    namespace = application.get(
        "namespace",
        "default"
    )

    target_app = get_target_app(
        application
    )

    try:

        output = run_command([
            "kubectl",
            "get",
            "pods",
            "-n",
            namespace,
            "-l",
            f"app={target_app}",
            "-o",
            "json"
        ])

        data = json.loads(
            output
        )

        items = data.get(
            "items",
            []
        )

        if not items:

            return None

        return items[0]

    except (
        RuntimeError,
        json.JSONDecodeError
    ):

        return None


def get_application_node(
    application
):

    pod = get_application_pod(
        application
    )

    if not pod:

        raise RuntimeError(
            "Could not find a running "
            "application pod."
        )

    node_name = (
        pod.get(
            "spec",
            {}
        ).get(
            "nodeName"
        )
    )

    if not node_name:

        raise RuntimeError(
            "Could not determine the "
            "application node."
        )

    return node_name


def get_node_count():

    output = run_command([
        "kubectl",
        "get",
        "nodes",
        "-o",
        "json"
    ])

    data = json.loads(
        output
    )

    return len(
        data.get(
            "items",
            []
        )
    )


def collect_result_metrics(
    application,
    recovery_result,
    k6_result=None
):

    namespace = application.get(
        "namespace",
        "default"
    )

    name = application.get(
        "name"
    )

    metrics = {
        "cpu_avg": None,
        "cpu_max": None,
        "memory_avg": None,
        "memory_max": None,
        "requests_per_second": None,
        "p95_latency_ms": None,
        "p99_latency_ms": None,
        "error_rate_percent": None,
        "pod_restarts": 0,
        "available_replicas": 0,
        "oom_killed": False,
        "recovery_time_seconds": (
            recovery_result.get(
                "recovery_time_seconds"
            )
            if recovery_result
            else None
        ),
        "collection_errors": [],
        "sources": {
            "cpu_avg": "kubectl top",
            "cpu_max": "kubectl top",
            "memory_avg": "kubectl top",
            "memory_max": "kubectl top",
            "requests_per_second": "k6 pending",
            "p95_latency_ms": "k6 pending",
            "p99_latency_ms": "k6 pending",
            "error_rate_percent": "k6 pending",
            "pod_restarts": "kubectl pod status",
            "available_replicas": "kubectl deployment status",
            "oom_killed": "kubectl pod status",
            "recovery_time_seconds": "Pod Kill recovery timer"
        }
    }

    if k6_result and k6_result.get(
        "status"
    ) == "completed":

        metrics[
            "requests_per_second"
        ] = k6_result.get(
            "requests_per_second"
        )
        metrics[
            "p95_latency_ms"
        ] = k6_result.get(
            "p95_ms"
        )
        metrics[
            "p99_latency_ms"
        ] = k6_result.get(
            "p99_ms"
        )
        metrics[
            "error_rate_percent"
        ] = k6_result.get(
            "error_rate_percent"
        )
        metrics[
            "sources"
        ][
            "requests_per_second"
        ] = "k6"
        metrics[
            "sources"
        ][
            "p95_latency_ms"
        ] = "k6"
        metrics[
            "sources"
        ][
            "p99_latency_ms"
        ] = "k6"
        metrics[
            "sources"
        ][
            "error_rate_percent"
        ] = "k6"

    elif k6_result:

        reason = k6_result.get(
            "reason",
            "k6 did not complete"
        )

        for metric_name in [
            "requests_per_second",
            "p95_latency_ms",
            "p99_latency_ms",
            "error_rate_percent"
        ]:

            metrics[
                "sources"
            ][
                metric_name
            ] = "k6: " + reason

    try:

        deployment = json.loads(
            run_command([
                "kubectl",
                "get",
                "deployment",
                name,
                "-n",
                namespace,
                "-o",
                "json"
            ])
        )

        metrics[
            "available_replicas"
        ] = deployment.get(
            "status",
            {}
        ).get(
            "availableReplicas",
            0
        ) or 0

    except (
        RuntimeError,
        json.JSONDecodeError
    ):

        pass

    if metrics[
        "cpu_avg"
    ] is None:

        try:

            pod = get_application_pod(
                application
            )

            if pod:

                pod_name = pod.get(
                    "metadata",
                    {}
                ).get(
                    "name"
                )

                pod_uid = pod.get(
                    "metadata",
                    {}
                ).get(
                    "uid"
                )
                node_name = pod.get(
                    "spec",
                    {}
                ).get(
                    "nodeName"
                )

                stats = json.loads(
                    run_command([
                        "kubectl",
                        "get",
                        "--raw",
                        f"/api/v1/nodes/{node_name}/proxy/stats/summary"
                    ])
                )

                pod_stats = next(
                    item for item in stats.get(
                        "pods",
                        []
                    )
                    if (
                        item.get("podRef", {}).get("uid") == pod_uid
                        or (
                            item.get("podRef", {}).get("name")
                            == pod_name
                            and item.get("podRef", {}).get("namespace")
                            == namespace
                        )
                    )
                )
                container_stats = pod_stats.get(
                    "containers",
                    []
                )[0]
                cpu_usage = container_stats.get(
                    "cpu",
                    {}
                ).get(
                    "usageNanoCores"
                )
                memory_usage = container_stats.get(
                    "memory",
                    {}
                ).get(
                    "workingSetBytes"
                )

                if cpu_usage is None:

                    raise RuntimeError(
                        "Kubelet stats did not include CPU usage."
                    )

                if memory_usage is None:

                    raise RuntimeError(
                        "Kubelet stats did not include memory usage."
                    )

                time.sleep(1)
                metrics["cpu_avg"] = cpu_usage / 1000000000
                metrics["cpu_max"] = metrics["cpu_avg"]
                metrics["memory_avg"] = memory_usage
                metrics["memory_max"] = memory_usage
                metrics["sources"]["cpu_avg"] = "kubelet stats summary"
                metrics["sources"]["cpu_max"] = "kubelet stats summary"
                metrics["sources"]["memory_avg"] = "kubelet stats summary"
                metrics["sources"]["memory_max"] = "kubelet stats summary"

        except (
            RuntimeError,
            ValueError,
            IndexError,
            OSError,
            KeyError,
            json.JSONDecodeError
        ):

            metrics[
                "collection_errors"
            ].append(
                "Kubelet CPU/memory stats unavailable."
            )
            metrics["sources"]["cpu_avg"] = "kubelet stats unavailable"
            metrics["sources"]["cpu_max"] = "kubelet stats unavailable"
            metrics["sources"]["memory_avg"] = "kubelet stats unavailable"
            metrics["sources"]["memory_max"] = "kubelet stats unavailable"

    try:

        pod_data = json.loads(
            run_command([
                "kubectl",
                "get",
                "pods",
                "-n",
                namespace,
                "-l",
                f"app={get_target_app(application)}",
                "-o",
                "json"
            ])
        )

        for pod in pod_data.get("items", []):

            statuses = pod.get(
                "status",
                {}
            ).get(
                "containerStatuses",
                []
            )

            for status in statuses:

                metrics[
                    "pod_restarts"
                ] += status.get(
                    "restartCount",
                    0
                )

                if status.get(
                    "lastState",
                    {}
                ).get(
                    "terminated",
                    {}
                ).get(
                    "reason"
                ) == "OOMKilled":

                    metrics[
                        "oom_killed"
                    ] = True

    except (
        RuntimeError,
        json.JSONDecodeError
    ):

        pass

    try:

        top = run_command([
            "kubectl",
            "top",
            "pods",
            "-n",
            namespace,
            "-l",
            f"app={get_target_app(application)}",
            "--no-headers"
        ])

        cpu_values = []
        memory_values = []

        for line in top.splitlines():

            columns = line.split()

            if len(columns) < 3:

                continue

            cpu_values.append(
                parse_cpu(columns[1])
            )
            memory_values.append(
                parse_memory(columns[2])
            )

        cpu_values = [
            value for value in cpu_values
            if value is not None
        ]
        memory_values = [
            value for value in memory_values
            if value is not None
        ]

        if cpu_values:

            metrics["cpu_avg"] = sum(
                cpu_values
            ) / len(cpu_values)
            metrics["cpu_max"] = max(
                cpu_values
            )

        if memory_values:

            metrics["memory_avg"] = sum(
                memory_values
            ) / len(memory_values)
            metrics["memory_max"] = max(
                memory_values
            )

    except RuntimeError as error:

        metrics[
            "collection_errors"
        ].append(
            "kubectl top unavailable: " + str(error)
        )

    return metrics


def scale_application(
    application,
    replicas
):

    kind = application.get(
        "kind"
    )

    name = application.get(
        "name"
    )

    namespace = application.get(
        "namespace",
        "default"
    )

    if kind not in {
        "Deployment",
        "StatefulSet"
    }:

        return

    run_command([
        "kubectl",
        "scale",
        kind.lower(),
        name,
        "--replicas",
        str(replicas),
        "-n",
        namespace
    ])


def cleanup_application(
    application
):

    try:

        replicas = application.get(
            "replicas",
            1
        )

        if replicas < 1:

            replicas = 1

        scale_application(
            application,
            replicas
        )

        print(
            f"Restored {application.get('name')} "
            f"to {replicas} replicas."
        )

    except RuntimeError as error:

        print(
            f"Application cleanup warning: {error}"
        )


def write_yaml_file(
    filename,
    generated_chaos
):

    os.makedirs(
        GENERATED_DIRECTORY,
        exist_ok=True
    )

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        for index, item in enumerate(
            generated_chaos
        ):

            file.write(
                item["yaml"]
            )

            if index < (
                len(generated_chaos) - 1
            ):

                file.write(
                    "\n---\n"
                )


def parse_duration(
    duration
):

    duration = str(
        duration
    ).strip()

    if duration.endswith("s"):

        return float(
            duration[:-1]
        )

    if duration.endswith("m"):

        return (
            float(
                duration[:-1]
            )
            * 60
        )

    raise ValueError(
        "Duration must use s or m."
    )


def analyze_k6_results(
    filename,
    duration_metric="http_req_duration",
    failure_metric="http_req_failed"
):

    latencies = []
    requests = 0
    failed_requests = 0

    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            try:

                data = json.loads(line)

            except json.JSONDecodeError:

                continue

            if (
                data.get("type") == "Point"
                and data.get("metric") == duration_metric
            ):

                duration_value = data["data"]["value"]
                requests += 1

                if duration_value > 0:

                    latencies.append(
                        duration_value
                    )

            if (
                data.get("type") == "Point"
                and data.get("metric") == failure_metric
                and data["data"]["value"] == 1
            ):

                failed_requests += 1

    latencies.sort()

    def percentile(
        values,
        percentage
    ):

        index = (
            (len(values) - 1)
            * percentage
            / 100
        )
        lower = int(index)
        upper = min(
            lower + 1,
            len(values) - 1
        )
        weight = index - lower

        return values[lower] + (
            values[upper] - values[lower]
        ) * weight

    return {
        "requests": requests,
        "failed_requests": failed_requests,
        "error_rate_percent": (
            failed_requests / requests * 100
            if requests
            else 0
        ),
        "p95_ms": percentile(latencies, 95)
        if latencies
        else None,
        "p99_ms": percentile(latencies, 99)
        if latencies
        else None
    }


def run_k6_http(
    application,
    vus,
    duration
):

    containers = application.get(
        "containers",
        []
    )

    ports = (
        containers[0].get("ports", [])
        if containers
        else []
    )

    http_port = next(
        (
            port.get("containerPort")
            for port in ports
            if port.get("containerPort") in {80, 8080}
        ),
        None
    )

    if http_port is None:

        return {
            "status": "skipped",
            "reason": "Workload does not expose an HTTP port.",
            "source": "k6"
        }

    name = application.get(
        "name"
    )

    namespace = application.get(
        "namespace",
        "default"
    )

    duration_seconds = parse_duration(
        duration
    )

    temporary_script = None
    output_file = None
    port_forward = None

    try:

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            delete=False,
            encoding="utf-8"
        ) as script_file:

            script_file.write(
                "import http from 'k6/http';\n"
                "export const options = { vus: "
                + str(vus)
                + ", duration: '"
                + str(duration)
                + "' };\n"
                "export default function () { "
                "http.get('http://127.0.0.1:18080'); }\n"
            )
            temporary_script = script_file.name

        output_file = tempfile.NamedTemporaryFile(
            suffix=".json",
            delete=False
        ).name

        port_forward = subprocess.Popen([
            "kubectl",
            "port-forward",
            f"deployment/{name}",
            f"18080:{http_port}",
            "-n",
            namespace
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        time.sleep(2)

        result = subprocess.run([
            "k6",
            "run",
            "--out",
            f"json={output_file}",
            temporary_script
        ], capture_output=True, text=True, timeout=duration_seconds + 30)

        if result.returncode != 0:

            return {
                "status": "failed",
                "reason": result.stderr.strip()
                or "k6 execution failed.",
                "source": "k6"
            }

        parsed = analyze_k6_results(
            output_file
        )
        parsed[
            "requests_per_second"
        ] = parsed[
            "requests"
        ] / duration_seconds
        parsed[
            "status"
        ] = "completed"
        parsed[
            "source"
        ] = "k6"
        return parsed

    except (
        OSError,
        RuntimeError,
        subprocess.TimeoutExpired
    ) as error:

        return {
            "status": "failed",
            "reason": str(error),
            "source": "k6"
        }

    finally:

        if port_forward:

            port_forward.terminate()

        for path in [
            temporary_script,
            output_file
        ]:

            if path and os.path.exists(path):

                os.remove(path)


def run_k6_grpc(
    application,
    vus,
    duration
):

    grpc_workloads = {
        "currencyservice": {
            "port": 7000,
            "method": "CurrencyService/Convert",
            "request": (
                "{from: { currencyCode: 'USD', units: 1, nanos: 0 }, "
                "toCode: 'EUR'}"
            )
        },
        "productcatalogservice": {
            "port": 3550,
            "method": "ProductCatalogService/ListProducts",
            "request": "{}"
        },
        "adservice": {
            "port": 9555,
            "method": "AdService/GetAds",
            "request": "{contextKeys: ['clothing']}"
        },
        "shippingservice": {
            "port": 50051,
            "method": "ShippingService/GetQuote",
            "request": (
                "{address: {streetAddress: '1 Main St', city: 'New York', "
                "state: 'NY', country: 'US', zipCode: 10001}, items: []}"
            )
        }
    }

    workload = grpc_workloads.get(
        application.get("name")
    )

    if workload is None:

        return {
            "status": "skipped",
            "reason": "No gRPC k6 contract is configured for this workload.",
            "source": "k6"
        }

    proto_file = os.path.join(
        REPOSITORY_DIRECTORY,
        "protos",
        "demo.proto"
    )

    if not os.path.isfile(proto_file):

        return {
            "status": "skipped",
            "reason": "The workload gRPC proto was not found.",
            "source": "k6"
        }

    namespace = application.get(
        "namespace",
        "default"
    )
    duration_seconds = parse_duration(duration)
    script_file = None
    output_file = None
    port_forward = None

    try:

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            delete=False,
            encoding="utf-8"
        ) as file:

            file.write(
                "import grpc from 'k6/net/grpc';\n"
                "export const options = { vus: "
                + str(vus)
                + ", duration: '"
                + str(duration)
                + "' };\n"
                "const client = new grpc.Client();\n"
                "client.load(['"
                + os.path.dirname(proto_file)
                + "'], 'demo.proto');\n"
                "export default function () {\n"
                "  client.connect('127.0.0.1:17000', { plaintext: true });\n"
                "  client.invoke('hipstershop."
                + workload["method"]
                + "', "
                + workload["request"]
                + ");\n"
                "  client.close();\n"
                "}\n"
            )
            script_file = file.name

        output_file = tempfile.NamedTemporaryFile(
            suffix=".json",
            delete=False
        ).name

        port_forward = subprocess.Popen([
            "kubectl",
            "port-forward",
            f"deployment/{application.get('name')}",
            f"17000:{workload['port']}",
            "-n",
            namespace
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        time.sleep(2)

        result = subprocess.run([
            "k6",
            "run",
            "--out",
            f"json={output_file}",
            script_file
        ], capture_output=True, text=True, timeout=duration_seconds + 30)

        if result.returncode != 0:

            return {
                "status": "failed",
                "reason": result.stderr.strip()
                or "gRPC k6 execution failed.",
                "source": "k6"
            }

        parsed = analyze_k6_results(
            output_file,
            "grpc_req_duration",
            "grpc_req_failed"
        )
        parsed["requests_per_second"] = (
            parsed["requests"] / duration_seconds
        )
        parsed["status"] = "completed"
        parsed["source"] = "k6"
        return parsed

    except (
        OSError,
        RuntimeError,
        subprocess.TimeoutExpired
    ) as error:

        return {
            "status": "failed",
            "reason": str(error),
            "source": "k6"
        }

    finally:

        if port_forward:

            port_forward.terminate()

        for path in [script_file, output_file]:

            if path and os.path.exists(path):

                os.remove(path)


def apply_chaos_file(
    yaml_file
):

    print(
        f"\nApplying: {yaml_file}"
    )

    output = run_command([
        "kubectl",
        "apply",
        "-f",
        yaml_file
    ])

    print(output)

    return output


def cleanup_chaos(
    namespace,
    resource_types,
    yaml_file=None
):

    print(
        "\nCleaning up Chaos Mesh resources..."
    )

    if yaml_file and os.path.exists(yaml_file):
        try:
            run_command([
                "kubectl",
                "delete",
                "-f",
                yaml_file,
                "--ignore-not-found",
                "--timeout=15s"
            ])
        except Exception as error:
            print(f"Cleanup yaml warning: {error}")

    for resource_type in resource_types:

        try:

            run_command([
                "kubectl",
                "delete",
                resource_type,
                "--all",
                "-n",
                namespace,
                "--ignore-not-found",
                "--timeout=15s"
            ])

        except RuntimeError as error:

            print(
                f"Cleanup warning: {error}"
            )

    print(
        "Chaos cleanup completed."
    )


def wait_for_application_recovery(
    application,
    timeout=120
):

    namespace = application.get(
        "namespace",
        "default"
    )

    target_app = get_target_app(
        application
    )

    print(
        "\nWaiting for application recovery..."
    )

    deadline = (
        time.time()
        + timeout
    )

    while time.time() < deadline:

        try:

            output = run_command([
                "kubectl",
                "get",
                "pods",
                "-n",
                namespace,
                "-l",
                f"app={target_app}",
                "-o",
                "json"
            ])

            data = json.loads(
                output
            )

            for pod in data.get(
                "items",
                []
            ):

                phase = (
                    pod.get(
                        "status",
                        {}
                    ).get(
                        "phase"
                    )
                )

                statuses = (
                    pod.get(
                        "status",
                        {}
                    ).get(
                        "containerStatuses",
                        []
                    )
                )

                ready = any(
                    status.get(
                        "ready",
                        False
                    )
                    for status in statuses
                )

                if (
                    phase == "Running"
                    and ready
                ):

                    print(
                        "Application recovered."
                    )

                    return True

        except (
            RuntimeError,
            json.JSONDecodeError
        ):

            pass

        time.sleep(
            3
        )

    print(
        "Application recovery was not "
        "confirmed within the timeout."
    )

    return False


def execute_pod_kill(
    application,
    yaml_file
):

    namespace = application.get(
        "namespace",
        "default"
    )

    print(
        "\n========================================"
    )

    print(
        "STAGE 1: POD KILL"
    )

    print(
        "========================================"
    )

    start_time = time.time()

    apply_chaos_file(
        yaml_file
    )

    print(
        "\nPod Kill is active."
    )

    recovered = (
        wait_for_application_recovery(
            application
        )
    )

    recovery_time = time.time() - start_time

    cleanup_chaos(
        namespace,
        [
            "podchaos"
        ]
    )

    return {
        "environment": "Pod Kill",
        "start_time": start_time,
        "end_time": time.time(),
        "recovered": recovered,
        "recovery_time_seconds": recovery_time,
        "status": (
            "completed"
            if recovered
            else "completed_without_confirmed_recovery"
        )
    }


def execute_five_chaos(
    application,
    yaml_file,
    duration,
    vus,
    active_environments=None
):

    namespace = application.get(
        "namespace",
        "default"
    )

    envs_to_run = active_environments or FIVE_CHAOS_ENVIRONMENTS

    print(
        "\n========================================"
    )

    print(
        f"STAGE 2: COMPOUND CHAOS ({len(envs_to_run)} ENVIRONMENTS)"
    )

    print(
        "========================================"
    )

    for env in envs_to_run:
        print(f"- {env}")

    print(
        "\nAll selected environments will be "
        "applied together."
    )

    start_time = time.time()

    apply_chaos_file(
        yaml_file
    )

    if application.get(
        "name"
    ) in {
        "currencyservice",
        "productcatalogservice",
        "adservice",
        "shippingservice"
    }:

        k6_result = run_k6_grpc(
            application,
            vus,
            duration
        )

    else:

        k6_result = run_k6_http(
            application,
            vus,
            duration
        )

    seconds = parse_duration(
        duration
    )

    print(
        f"\nCompound chaos environments running "
        f"simultaneously for {duration}..."
    )

    time.sleep(
        seconds
    )

    print(
        "\nCompound chaos duration completed."
    )

    cleanup_chaos(
        namespace,
        [
            "stresschaos",
            "networkchaos"
        ],
        yaml_file=yaml_file
    )

    recovered = (
        wait_for_application_recovery(
            application
        )
    )

    recovery_time = time.time() - start_time

    return {
        "environments": envs_to_run,
        "start_time": start_time,
        "end_time": time.time(),
        "duration": duration,
        "simultaneous": True,
        "recovered": recovered,
        "recovery_time_seconds": recovery_time,
        "k6": k6_result,
        "status": "completed"
    }


def execute_node_failure(
    application,
    yaml_file,
    duration
):

    namespace = application.get(
        "namespace",
        "default"
    )

    print(
        "\n========================================"
    )

    print(
        "STAGE 3: NODE FAILURE"
    )

    print(
        "========================================"
    )

    node_count = get_node_count()

    if node_count < 2:

        message = (
            "Node Failure cannot be executed. "
            "The cluster has only one node. "
            "Create a multi-node kind cluster "
            "before running Node Failure."
        )

        print(
            f"\n{message}"
        )

        return {
            "environment": "Node Failure",
            "status": "not_executed",
            "reason": message
        }

    start_time = time.time()

    node_name = get_application_node(
        application
    )

    print(
        f"\nTarget node: {node_name}"
    )

    apply_chaos_file(
        yaml_file
    )

    seconds = parse_duration(
        duration
    )

    print(
        f"\nNode Failure running for "
        f"{duration}..."
    )

    time.sleep(
        seconds
    )

    cleanup_chaos(
        namespace,
        [
            "nodechaos"
        ]
    )

    recovered = (
        wait_for_application_recovery(
            application
        )
    )

    recovery_time = time.time() - start_time

    return {
        "environment": "Node Failure",
        "node": node_name,
        "start_time": start_time,
        "end_time": time.time(),
        "duration": duration,
        "recovered": recovered,
        "recovery_time_seconds": recovery_time,
        "status": (
            "completed"
            if recovered
            else "completed_without_confirmed_recovery"
        )
    }


def process_application(
    application,
    environments,
    cpu,
    memory,
    vus,
    duration,
    mode="binary_search",
    event_emitter=None,
    **kwargs
):

    name = application.get(
        "name"
    )

    namespace = application.get(
        "namespace",
        "default"
    )

    print(
        "\n========================================"
    )

    print(
        f"PROCESSING APPLICATION: {name}"
    )

    print(
        "========================================"
    )

    deployment_result = None

    try:

        print(
            "\nDeploying application..."
        )

        if event_emitter:
            event_emitter.emit("stage_update", {
                "service": name,
                "stage": "deploy",
                "status": "running"
            })

        deployment_result = deploy_application(
            application
        )

        if event_emitter:
            event_emitter.emit("stage_update", {
                "service": name,
                "stage": "deploy",
                "status": "completed"
            })

        llm_application = (
            prepare_llm_application(
                application
            )
        )

        print(
            "\nGenerating environment parameters..."
        )

        parameters = (
            generate_environment_parameters(
                application=llm_application,
                environments=environments,
                cpu=cpu,
                memory=memory,
                vus=vus,
                duration=duration
            )
        )

        print(
            "\nGenerated parameters:"
        )

        print(
            json.dumps(
                parameters,
                indent=2
            )
        )

        print(
            "\nValidating parameters..."
        )

        valid, message = (
            validate_environment_parameters(
                parameters,
                application,
                environments
            )
        )

        if not valid:

            raise RuntimeError(
                f"Environment validation failed: "
                f"{message}"
            )

        print(
            "Parameters validated successfully."
        )

        target_app = get_target_app(
            application
        )

        chaos_parameters = (
            build_chaos_parameters(
                application=application,
                environments=environments,
                parameters=parameters,
                duration=duration
            )
        )

        os.makedirs(
            GENERATED_DIRECTORY,
            exist_ok=True
        )

        result = {
            "application": application,
            "deployment": deployment_result,
            "workload": {
                "vus": vus,
                "duration": duration
            },
            "chaos": {},
            "stages": {}
        }

        pod_kill_parameters = {
            "Pod Kill": chaos_parameters[
                "Pod Kill"
            ]
        }

        pod_kill_yaml = (
            generate_chaos_yaml(
                "Pod Kill",
                pod_kill_parameters[
                    "Pod Kill"
                ]
            )
        )

        pod_kill_file = os.path.join(
            GENERATED_DIRECTORY,
            f"{name}-pod-kill.yaml"
        )

        with open(
            pod_kill_file,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                pod_kill_yaml
            )

        print(
            f"\nGenerated Pod Kill YAML: "
            f"{pod_kill_file}"
        )

        if event_emitter:
            event_emitter.emit("stage_update", {
                "service": name,
                "stage": "pod_kill",
                "status": "running"
            })

        pod_kill_result = (
            execute_pod_kill(
                application,
                pod_kill_file
            )
        )

        result[
            "stages"
        ][
            "pod_kill"
        ] = pod_kill_result

        if event_emitter:
            event_emitter.emit("stage_update", {
                "service": name,
                "stage": "pod_kill",
                "status": "completed",
                "details": pod_kill_result
            })

        # --------------------------------
        # Binary Search Optimization Loop (Stage 2)
        # --------------------------------
        effective_mode = mode if mode in ["binary_search", "heuristic"] else "binary_search"
        bounds = calculate_bounds(application, cpu, memory)
        # --------------------------------
        # Multi-Parameter Optimization Engine (Stage 2)
        # --------------------------------
        effective_mode = mode if mode in ["binary_search", "heuristic"] else "binary_search"
        bounds = calculate_bounds(application, cpu, memory)
        max_iters = 10 if effective_mode == "binary_search" else 1

        multi_session = MultiParamSearchSession(bounds=bounds, max_iterations=max_iters)

        best_five_chaos_result = None
        best_metrics = None
        last_five_chaos_file = None
        initial_peak_mem = (result.get("metrics") or {}).get("memory_max") or 0
        initial_peak_cpu = (result.get("metrics") or {}).get("cpu_max") or 0
        baseline_mem_mb = int(initial_peak_mem / (1024 * 1024)) if initial_peak_mem else 32
        baseline_cpu_m = int(initial_peak_cpu * 1000) if initial_peak_cpu else 50

        print(f"\n========================================")
        print(f"RESILIENCE & MULTI-PARAM OPTIMIZATION LOOP ({name})")
        print(f"Mode: {effective_mode} | Testing 4 Dimensions: RAM, CPU, DELAY, LOSS")
        print(f"Bounds: RAM [{bounds['Memory Stress']['low']}M, {bounds['Memory Stress']['high']}M] | CPU [{bounds['CPU Stress']['low']}%, {bounds['CPU Stress']['high']}%] | DELAY [{bounds['Network Delay']['low']}ms, {bounds['Network Delay']['high']}ms] | LOSS [{bounds['Network Loss']['low']}%, {bounds['Network Loss']['high']}%]")
        print(f"========================================")

        while not multi_session.converged and multi_session.iteration < multi_session.max_iterations:
            if event_emitter and getattr(event_emitter, 'is_stopped', False):
                print(f"\nExecution stopped by user request for {name}.")
                break

            current_vector = multi_session.next_vector()
            current_iter = multi_session.iteration + 1
            print(f"\n--- [Iteration {current_iter}] Testing Compound Vector: RAM {current_vector['RAM']}M | CPU {current_vector['CPU']}% | DELAY {current_vector['DELAY']}ms | LOSS {current_vector['LOSS']}% ---")

            if "Memory Stress" in parameters.get("environments", {}):
                parameters["environments"]["Memory Stress"]["value"] = f"{current_vector['RAM']}M"
            if "CPU Stress" in parameters.get("environments", {}):
                parameters["environments"]["CPU Stress"]["value"] = str(current_vector["CPU"])
            if "Network Delay" in parameters.get("environments", {}):
                parameters["environments"]["Network Delay"]["value"] = f"{current_vector['DELAY']}ms"
            if "Network Loss" in parameters.get("environments", {}):
                parameters["environments"]["Network Loss"]["value"] = str(current_vector["LOSS"])

            iter_chaos_parameters = build_chaos_parameters(
                application=application,
                environments=environments,
                parameters=parameters,
                duration=duration,
                iteration=current_iter
            )

            active_compound_environments = [
                env for env in FIVE_CHAOS_ENVIRONMENTS
                if env in environments and env in iter_chaos_parameters
            ]

            five_chaos_parameters = {
                env: iter_chaos_parameters[env]
                for env in active_compound_environments
            }

            iter_five_chaos_yaml = generate_compound_chaos_yaml(
                active_compound_environments,
                five_chaos_parameters
            )

            iter_five_chaos_file = os.path.join(
                GENERATED_DIRECTORY,
                f"{name}-five-chaos-iter{current_iter}.yaml"
            )
            write_yaml_file(iter_five_chaos_file, iter_five_chaos_yaml)
            last_five_chaos_file = iter_five_chaos_file

            chaos_vector = {
                "memory": f"{current_vector['RAM']}M",
                "cpu": f"{current_vector['CPU']}%",
                "delay": f"{current_vector['DELAY']}ms",
                "loss": f"{current_vector['LOSS']}%",
                "partition": str(five_chaos_parameters.get("Network Partition", {}).get("target_app", "None"))
            }

            if event_emitter:
                event_emitter.emit("stage_update", {
                    "service": name,
                    "stage": "five_chaos",
                    "status": "running",
                    "iteration": current_iter,
                    "max_iterations": multi_session.max_iterations,
                    "tested_value": f"{current_vector['RAM']}M",
                    "chaos_vector": chaos_vector
                })

            five_chaos_result = execute_five_chaos(
                application,
                iter_five_chaos_file,
                duration,
                vus,
                active_environments=active_compound_environments
            )

            iter_metrics = collect_result_metrics(
                application,
                pod_kill_result,
                five_chaos_result.get("k6")
            )

            if iter_metrics:
                cur_mem = iter_metrics.get("memory_max") or 0
                cur_cpu = iter_metrics.get("cpu_max") or 0
                if cur_mem:
                    baseline_mem_mb = max(baseline_mem_mb, int(cur_mem / (1024 * 1024)))
                if cur_cpu:
                    baseline_cpu_m = max(baseline_cpu_m, int(cur_cpu * 1000))

            iter_rec_config = calculate_recommended_config(metrics=iter_metrics)

            k6_stage = five_chaos_result.get("k6", {})
            sla_passed, sla_reason = evaluate_sla(k6_stage, iter_metrics)

            step_entry = multi_session.record_trial(
                current_vector,
                sla_passed,
                k6_result=k6_stage,
                metrics=iter_metrics,
                reason=sla_reason,
                recommended_config=iter_rec_config
            )

            print(f"Iteration {current_iter} Result: {'PASSED' if sla_passed else 'BREACHED'} ({step_entry['reason']})")
            print(f"Culprit Dimension: {step_entry['culprit'] or 'None (All Passed)'}")
            print(f"Decision Step: {step_entry['step_taken']}")
            print(f"Iteration Sizing Config: Memory Limit={iter_rec_config['memory_limit']}, Request={iter_rec_config['memory_request']} | CPU Limit={iter_rec_config['cpu_limit']}, Request={iter_rec_config['cpu_request']}")

            if sla_passed or best_five_chaos_result is None:
                best_five_chaos_result = five_chaos_result
                best_metrics = iter_metrics

            if event_emitter:
                event_emitter.emit("iteration_update", {
                    "service": name,
                    "iteration": step_entry["iteration"],
                    "max_iterations": multi_session.max_iterations,
                    "parameter": step_entry.get("culprit") or "Compound",
                    "tested_value": f"{current_vector['RAM']}M",
                    "sla_passed": step_entry["passed"],
                    "reason": step_entry["reason"],
                    "step_taken": step_entry["step_taken"],
                    "culprit": step_entry["culprit"],
                    "vector": current_vector,
                    "parameters_state": step_entry["parameters_state"],
                    "difference": step_entry["difference"],
                    "difference_str": f"{step_entry['difference']}M",
                    "next_midpoint": step_entry["next_midpoint"],
                    "converged": step_entry["converged"],
                    "chaos_vector": chaos_vector,
                    "recommended_config": iter_rec_config
                })

            if effective_mode == "heuristic":
                break

            if not multi_session.converged:
                time.sleep(2)

        result["stages"]["five_chaos"] = best_five_chaos_result

        if event_emitter:
            event_emitter.emit("stage_update", {
                "service": name,
                "stage": "five_chaos",
                "status": "completed",
                "details": best_five_chaos_result
            })

        node_failure_result = None
        node_failure_file = None
        if "Node Failure" in environments and "Node Failure" in chaos_parameters:
            node_failure_parameters = {
                "Node Failure": chaos_parameters["Node Failure"]
            }

            node_failure_yaml = generate_chaos_yaml(
                "Node Failure",
                node_failure_parameters["Node Failure"]
            )

            node_failure_file = os.path.join(
                GENERATED_DIRECTORY,
                f"{name}-node-failure.yaml"
            )

            with open(node_failure_file, "w", encoding="utf-8") as file:
                file.write(node_failure_yaml)

            print(f"\nGenerated Node Failure YAML: {node_failure_file}")

            if event_emitter:
                event_emitter.emit("stage_update", {
                    "service": name,
                    "stage": "node_failure",
                    "status": "running"
                })

            node_failure_result = execute_node_failure(
                application,
                node_failure_file,
                duration
            )

            result["stages"]["node_failure"] = node_failure_result

            if event_emitter:
                event_emitter.emit("stage_update", {
                    "service": name,
                    "stage": "node_failure",
                    "status": "completed",
                    "details": node_failure_result
                })

        result["metrics"] = best_metrics or collect_result_metrics(
            application,
            pod_kill_result,
            best_five_chaos_result.get("k6") if best_five_chaos_result else None
        )

        result["chaos"] = parameters
        result["target_app"] = target_app
        result["generated_files"] = {
            "pod_kill": pod_kill_file,
            "five_chaos": last_five_chaos_file,
            "node_failure": node_failure_file
        }

        # --------------------------------
        # Complete Right-Sizing & Convergence Summary (Limits & Requests)
        # --------------------------------
        service_passed = any(it["passed"] for it in multi_session.history)
        peak_mem_bytes = result.get("metrics", {}).get("memory_max") or 0
        peak_cpu_cores = result.get("metrics", {}).get("cpu_max") or 0
        baseline_mem_mb = int(peak_mem_bytes / (1024 * 1024)) if peak_mem_bytes else 32
        baseline_cpu_m = int(peak_cpu_cores * 1000) if peak_cpu_cores else 50

        multi_summary = multi_session.summary()
        safe_ram_mb = multi_session.best_passing_vector["RAM"] if (service_passed and multi_session.best_passing_vector) else (multi_session.sessions["RAM"].best_passing_value if service_passed else 0)
        safe_cpu_pct = multi_session.best_passing_vector["CPU"] if (service_passed and multi_session.best_passing_vector) else (multi_session.sessions["CPU"].best_passing_value if service_passed else 10)

        passing_trials = [it for it in multi_session.history if it["passed"]]
        if passing_trials:
            min_passing_trial = min(
                passing_trials,
                key=lambda it: (
                    (it.get("metrics") or {}).get("memory_avg")
                    or (it.get("metrics") or {}).get("memory_max")
                    or 999999999
                )
            )
            baseline_metrics = min_passing_trial.get("metrics")
        else:
            baseline_metrics = best_metrics or result.get("metrics")

        final_rec_config = calculate_recommended_config(
            metrics=best_metrics or result.get("metrics"),
            baseline_metrics=baseline_metrics
        )
        recommended_mem_limit = final_rec_config["memory_limit"]
        recommended_mem_request = final_rec_config["memory_request"]
        recommended_cpu_limit = final_rec_config["cpu_limit"]
        recommended_cpu_request = final_rec_config["cpu_request"]

        # Generate production-ready right-sized Kubernetes manifest
        optimized_yaml_str, optimized_yaml_file = generate_optimized_deployment_yaml(
            application=application,
            recommended_config={
                "memory_limit": recommended_mem_limit,
                "memory_request": recommended_mem_request,
                "cpu_limit": recommended_cpu_limit,
                "cpu_request": recommended_cpu_request
            },
            optimal_tolerances=optimal_vals
        )
        print(f"\nGenerated Right-Sized Manifest: {optimized_yaml_file}")

        optimal_vals = multi_summary["optimal_values"]

        sla_verdict = (
            f"Optimal safe tolerances: RAM={optimal_vals['RAM']}, CPU={optimal_vals['CPU']}, DELAY={optimal_vals['DELAY']}, LOSS={optimal_vals['LOSS']} (Converged in {multi_session.iteration} iterations)"
            if service_passed
            else f"All {multi_session.iteration} iterations breached SLA: {multi_session.history[-1]['reason'] if multi_session.history else 'Unknown'}"
        )

        optimization_summary = {
            "sla_passed": service_passed,
            "sla_verdict": sla_verdict,
            "bounds": bounds,
            "recommended_config": {
                "memory_limit": recommended_mem_limit,
                "memory_request": recommended_mem_request,
                "cpu_limit": recommended_cpu_limit,
                "cpu_request": recommended_cpu_request
            },
            "optimal_values": optimal_vals,
            "max_safe_tolerance": optimal_vals["RAM"] if service_passed else "0M",
            "iterations": multi_session.history,
            "summary": multi_summary,
            "optimized_yaml": optimized_yaml_str,
            "optimized_yaml_file": optimized_yaml_file
        }
        result["optimization"] = optimization_summary
        result["generated_files"]["optimized_deployment"] = optimized_yaml_file

        print("\n========================================")
        print("MULTI-PARAMETER CONVERGENCE SUMMARY")
        print("========================================")
        print(f"Overall Status:        {'PASSED' if service_passed else 'FAILED'}")
        print(f"SLA Verdict:           {sla_verdict}")
        print(f"Optimal Limits:        RAM {optimal_vals['RAM']} | CPU {optimal_vals['CPU']} | DELAY {optimal_vals['DELAY']} | LOSS {optimal_vals['LOSS']}")
        print(f"Recommended Limits:    {recommended_mem_limit} Memory | {recommended_cpu_limit} CPU")
        print(f"Recommended Requests:  {recommended_mem_request} Memory | {recommended_cpu_request} CPU")
        print("========================================")

        result["status"] = "completed"

        result_file = os.path.join(
            GENERATED_DIRECTORY,
            f"{name}-environment-result.json"
        )

        with open(result_file, "w", encoding="utf-8") as file:
            json.dump(result, file, indent=2)

        print(f"\nResult saved: {result_file}")

        if event_emitter:
            event_emitter.emit("service_result", {
                "service": name,
                "status": "passed" if service_passed else "failed",
                "optimization": optimization_summary,
                "optimized_yaml": optimized_yaml_str,
                "optimized_yaml_file": optimized_yaml_file,
                "metrics": result.get("metrics"),
                "stages": result.get("stages")
            })

        return result

    finally:

        if deployment_result:

            cleanup_application(
                application
            )


def run_environment(
    github_url,
    cpu,
    memory,
    vus,
    duration,
    environments=None,
    mode="binary_search",
    target_service=None,
    event_emitter=None,
    **kwargs
):

    print(
        "\n========================================"
    )

    print(
        "AI KUBERNETES ENVIRONMENT SIMULATOR"
    )

    print(
        "========================================"
    )

    if not github_url:
        raise ValueError(
            "GitHub repository URL is required."
        )

    environments = environments or [
        "Pod Kill",
        "CPU Stress",
        "Memory Stress",
        "Network Delay",
        "Network Loss",
        "Network Partition",
        "Node Failure"
    ]

    print(
        "\nSelected environment sequence:"
    )

    for environment in environments:

        print(
            f"  - {environment}"
        )

    project_path = clone_repository(
        github_url
    )

    print(
        "\nRepository:"
    )

    print(
        project_path
    )

    yaml_files = find_yaml_files(
        project_path
    )

    print(
        f"\nDiscovered {len(yaml_files)} YAML files."
    )

    resources = []

    for yaml_file in yaml_files:

        resources.extend(
            parse_yaml_file(
                yaml_file
            )
        )

    print(
        f"Parsed {len(resources)} Kubernetes resources."
    )

    applications = analyze_resources(
        resources
    )

    workloads = get_workloads(
        applications
    )

    print(
        f"\nDetected {len(workloads)} workloads."
    )

    if event_emitter:
        event_emitter.emit("discovery", {
            "total": len(workloads),
            "services": [
                {
                    "name": w.get("name"),
                    "namespace": w.get("namespace", "default"),
                    "kind": w.get("kind", "Deployment")
                }
                for w in workloads
            ]
        })

    if target_service == "discovery_only":
        print("\nDiscovery-only mode completed. Discovered workloads published to console.")
        return []

    target_workloads = [w for w in workloads if w.get("name") == target_service] if target_service else workloads
    if target_service and not target_workloads:
        print(f"Target service '{target_service}' not found. Available: {[w.get('name') for w in workloads]}")
        target_workloads = workloads

    results = []

    for index, application in enumerate(
        target_workloads,
        start=1
    ):
        if event_emitter and getattr(event_emitter, 'is_stopped', False):
            print("\nOrchestration run stopped by user request.")
            break

        app_name = application.get("name")

        if event_emitter:
            event_emitter.active_service = app_name
            event_emitter.emit("service_start", {
                "service": app_name,
                "index": index,
                "total": len(target_workloads),
                "namespace": application.get("namespace", "default")
            })

        print(
            "\n----------------------------------------"
        )

        print(
            f"Application {index}/{len(workloads)}"
        )

        print(
            f"Name: {app_name}"
        )

        print(
            f"Namespace: "
            f"{application.get('namespace', 'default')}"
        )

        print(
            "----------------------------------------"
        )

        try:

            result = process_application(
                application=application,
                environments=environments,
                cpu=cpu,
                memory=memory,
                vus=vus,
                duration=duration,
                mode=mode,
                event_emitter=event_emitter
            )

            results.append(
                result
            )

        except Exception as error:

            print(
                f"\nApplication failed: {error}"
            )

            metrics = collect_result_metrics(
                application,
                None
            )

            failed_item = {
                "application": application,
                "status": "failed",
                "error": str(error),
                "metrics": metrics
            }

            results.append(failed_item)

            if event_emitter:
                event_emitter.emit("service_result", {
                    "service": app_name,
                    "status": "failed",
                    "error": str(error),
                    "metrics": metrics
                })

        finally:
            if event_emitter:
                event_emitter.active_service = None

    aggregate_file = os.path.join(
        GENERATED_DIRECTORY,
        "environment-results.json"
    )

    os.makedirs(
        GENERATED_DIRECTORY,
        exist_ok=True
    )

    with open(
        aggregate_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            results,
            file,
            indent=2
        )

    if event_emitter:
        event_emitter.emit("aggregate_complete", {
            "status": "completed",
            "total": len(results),
            "results": results
        })

    print(
        "\n========================================"
    )

    print(
        "ENVIRONMENT SIMULATION COMPLETED"
    )

    print(
        "========================================"
    )

    print(
        f"\nAggregate result: {aggregate_file}"
    )

    return results


def generate_environment():
    return run_environment(
        github_url=input("\nGitHub repository URL: ").strip(),
        cpu=input("Available CPU: ").strip(),
        memory=input("Available memory: ").strip(),
        vus=input("k6 VUs: ").strip(),
        duration=input("Experiment duration: ").strip()
    )


if __name__ == "__main__":

    generate_environment()
