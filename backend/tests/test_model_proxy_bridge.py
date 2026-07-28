from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "model_proxy_bridge.py"
SPEC = importlib.util.spec_from_file_location("model_proxy_bridge", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
model_proxy_bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model_proxy_bridge)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://127.0.0.1:7897", ("127.0.0.1", 7897)),
        ("http://localhost:8080/", ("localhost", 8080)),
    ],
)
def test_parse_upstream_accepts_only_loopback_http(value, expected):
    assert model_proxy_bridge._parse_upstream(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:7897",
        "http://0.0.0.0:7897",
        "http://192.168.1.2:7897",
        "http://user:password@127.0.0.1:7897",
        "http://127.0.0.1:7897/path",
    ],
)
def test_parse_upstream_rejects_lan_credentials_and_paths(value):
    with pytest.raises(model_proxy_bridge.BridgeError):
        model_proxy_bridge._parse_upstream(value)


def test_stale_state_is_removed_without_signalling_unowned_pid(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"pid": 1234}\n', encoding="utf-8")
    monkeypatch.setattr(model_proxy_bridge, "_owned_process", lambda _pid: False)

    args = type("Args", (), {"state_dir": str(tmp_path)})()
    assert model_proxy_bridge._stop(args) == 0
    assert not state_path.exists()
    assert "stale_state_removed" in capsys.readouterr().out


def test_start_reuses_only_an_identical_running_bridge(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"pid": 1234, "listen_host": "172.17.0.1", "listen_port": 17897, "upstream_host": "127.0.0.1", "upstream_port": 7897}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(model_proxy_bridge, "_owned_process", lambda _pid: True)
    monkeypatch.setattr(model_proxy_bridge, "_docker_gateway", lambda: "172.17.0.1")
    monkeypatch.setattr(
        model_proxy_bridge,
        "_terminate_owned_process",
        lambda *_args: (_ for _ in ()).throw(AssertionError("identical bridge must not restart")),
    )

    args = type(
        "Args",
        (),
        {
            "state_dir": str(tmp_path),
            "upstream": "http://127.0.0.1:7897",
            "listen_port": 17897,
        },
    )()
    assert model_proxy_bridge._start(args) == 0
    assert '"status": "running"' in capsys.readouterr().out


def test_start_replaces_a_running_bridge_when_configuration_changes(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"pid": 1234, "listen_host": "172.17.0.1", "listen_port": 17897, "upstream_host": "127.0.0.1", "upstream_port": 7897}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(model_proxy_bridge, "_owned_process", lambda _pid: True)
    monkeypatch.setattr(model_proxy_bridge, "_docker_gateway", lambda: "172.17.0.1")
    terminated = []
    monkeypatch.setattr(model_proxy_bridge, "_terminate_owned_process", lambda _state_dir, pid: terminated.append(pid))

    class Started(RuntimeError):
        pass

    monkeypatch.setattr(model_proxy_bridge.subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(Started))
    args = type(
        "Args",
        (),
        {
            "state_dir": str(tmp_path),
            "upstream": "http://127.0.0.1:7898",
            "listen_port": 17897,
        },
    )()
    with pytest.raises(Started):
        model_proxy_bridge._start(args)
    assert terminated == [1234]


@pytest.mark.parametrize(
    ("listen_host", "listen_port", "upstream_host", "upstream_port"),
    [
        ("0.0.0.0", 17897, "127.0.0.1", 7897),
        ("172.17.0.1", 17897, "192.168.1.2", 7897),
        ("172.17.0.1", 0, "127.0.0.1", 7897),
    ],
)
def test_serve_endpoint_validation_rejects_public_or_invalid_addresses(
    listen_host,
    listen_port,
    upstream_host,
    upstream_port,
):
    with pytest.raises(model_proxy_bridge.BridgeError):
        model_proxy_bridge._validate_relay_endpoint(listen_host, listen_port, upstream_host, upstream_port)
