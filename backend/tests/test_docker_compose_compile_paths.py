from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose-dev.yaml"
MODEL_PROXY_COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose-model-proxy.yaml"


def test_compile_session_mount_and_path_contract_are_applied_to_both_runtimes():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    required_root = "${DEER_FLOW_ROOT:?set DEER_FLOW_ROOT via scripts/docker.sh}"
    assert compose.count(f"{required_root}/.compile-sessions:/workspace/.compile-sessions") == 2
    assert compose.count("DEER_FLOW_WORKSPACE_ROOT=/workspace") == 2
    assert compose.count(f"DEER_FLOW_HOST_WORKSPACE_ROOT={required_root}") == 2
    assert compose.count(f"HOST_PROJECT_ROOT={required_root}") == 2


def test_compose_rejects_an_unset_host_workspace_root():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "${DEER_FLOW_ROOT}/" not in compose
    assert compose.count("${DEER_FLOW_ROOT:?set DEER_FLOW_ROOT via scripts/docker.sh}") == 12


def test_documented_docker_port_matches_compose_mapping():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert '"8000:8000"' in compose
    assert "localhost:2026" not in compose


def test_langgraph_runtime_variables_are_not_expanded_by_compose():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "$${LANGGRAPH_ALLOW_BLOCKING:-0}" in compose
    assert "$${allow_blocking}" in compose
    assert "$${LANGGRAPH_JOBS_PER_WORKER:-10}" in compose


def test_backend_build_and_runtime_receive_uv_timeout():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert compose.count("UV_HTTP_TIMEOUT: ${UV_HTTP_TIMEOUT:-600}") == 2
    assert compose.count("UV_HTTP_TIMEOUT=${UV_HTTP_TIMEOUT:-600}") == 2
    assert compose.count("uv sync --frozen") == 4
    assert compose.count("uv run --frozen") == 2


def test_backend_services_mount_example_config_for_runtime_validation():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert compose.count("../config.example.yaml:/app/config.example.yaml:ro") == 2
    assert compose.count("../scripts:/app/scripts:ro") == 2


def test_backend_services_receive_explicit_model_runtime_proxy_without_credentials():
    compose = MODEL_PROXY_COMPOSE_FILE.read_text(encoding="utf-8")

    assert compose.count("MODEL_RUNTIME_HTTP_PROXY=${MODEL_RUNTIME_HTTP_PROXY:-}") == 2
    assert compose.count("MODEL_RUNTIME_HTTPS_PROXY=${MODEL_RUNTIME_HTTPS_PROXY:-}") == 2
    assert compose.count("MODEL_RUNTIME_NO_PROXY=${MODEL_RUNTIME_NO_PROXY:-") == 2
    assert compose.count('export HTTP_PROXY=\\"$${MODEL_RUNTIME_HTTP_PROXY:-}\\"') == 2
    assert "FORGE_MODEL_PROXY_UPSTREAM" not in compose


def test_frozen_base_compose_does_not_embed_model_proxy_override():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "MODEL_RUNTIME_HTTP_PROXY" not in compose
