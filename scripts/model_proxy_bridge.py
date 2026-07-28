#!/usr/bin/env python3
"""Expose a Windows loopback HTTP proxy only to the WSL Docker bridge."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import select
import signal
import socket
import socketserver
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DIR = REPO_ROOT / ".compile-sessions" / "model-proxy-bridge"
DEFAULT_LISTEN_PORT = 17897


class BridgeError(RuntimeError):
    """Raised when the bridge cannot be managed safely."""


def _emit(**payload: object) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def _docker_gateway() -> str:
    result = subprocess.run(
        ["docker", "network", "inspect", "bridge", "--format", "{{(index .IPAM.Config 0).Gateway}}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    gateway = result.stdout.strip()
    address = ipaddress.ip_address(gateway)
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_private:
        raise BridgeError("Docker bridge gateway must be a private IPv4 address")
    return gateway


def _parse_upstream(value: str) -> tuple[str, int]:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise BridgeError("Upstream must be an HTTP proxy on Windows loopback")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise BridgeError("Upstream credentials, paths, queries, and fragments are forbidden")
    if parsed.port is None:
        raise BridgeError("Upstream proxy port is required")
    return parsed.hostname, parsed.port


def _state_path(state_dir: Path) -> Path:
    return state_dir / "state.json"


def _read_state(state_dir: Path) -> dict | None:
    try:
        payload = json.loads(_state_path(state_dir).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _owned_process(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return False
    return "model_proxy_bridge.py" in cmdline and " serve " in f" {cmdline} "


def _remove_state_if_owner(state_dir: Path, pid: int) -> None:
    state = _read_state(state_dir)
    if state and state.get("pid") == pid:
        _state_path(state_dir).unlink(missing_ok=True)


def _validate_relay_endpoint(listen_host: str, listen_port: int, upstream_host: str, upstream_port: int) -> None:
    address = ipaddress.ip_address(listen_host)
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_private or address.is_unspecified or address.is_loopback or address.is_link_local:
        raise BridgeError("Listen address must be a private Docker IPv4 gateway")
    if upstream_host not in {"127.0.0.1", "localhost", "::1"}:
        raise BridgeError("Upstream host must remain on Windows loopback")
    if not 1 <= listen_port <= 65_535 or not 1 <= upstream_port <= 65_535:
        raise BridgeError("Relay ports must be between 1 and 65535")


def _terminate_owned_process(state_dir: Path, pid: int) -> None:
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _owned_process(pid):
        time.sleep(0.05)
    if _owned_process(pid):
        raise BridgeError("Proxy bridge did not stop within the deadline")
    _state_path(state_dir).unlink(missing_ok=True)


class _RelayHandler(socketserver.BaseRequestHandler):
    upstream: tuple[str, int]

    def handle(self) -> None:
        upstream = socket.create_connection(self.upstream, timeout=5)
        sockets = [self.request, upstream]
        try:
            while True:
                readable, _, _ = select.select(sockets, [], [], 30)
                for source in readable:
                    data = source.recv(65_536)
                    if not data:
                        return
                    target = upstream if source is self.request else self.request
                    target.sendall(data)
        finally:
            upstream.close()


class _RelayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _serve(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    _validate_relay_endpoint(args.listen_host, args.listen_port, args.upstream_host, args.upstream_port)
    handler = type("ConfiguredRelayHandler", (_RelayHandler,), {"upstream": (args.upstream_host, args.upstream_port)})
    server = _RelayServer((args.listen_host, args.listen_port), handler)
    pid = os.getpid()
    state = {
        "pid": pid,
        "listen_host": args.listen_host,
        "listen_port": args.listen_port,
        "upstream_host": args.upstream_host,
        "upstream_port": args.upstream_port,
    }
    _state_path(state_dir).write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")

    def _terminate(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _terminate)
    signal.signal(signal.SIGINT, _terminate)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _remove_state_if_owner(state_dir, pid)
    return 0


def _start(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    upstream_host, upstream_port = _parse_upstream(args.upstream)
    listen_host = _docker_gateway()
    expected = {
        "listen_host": listen_host,
        "listen_port": args.listen_port,
        "upstream_host": upstream_host,
        "upstream_port": upstream_port,
    }
    state = _read_state(state_dir)
    if state and _owned_process(int(state.get("pid", 0))):
        if all(state.get(name) == value for name, value in expected.items()):
            _emit(status="running", **state)
            return 0
        _terminate_owned_process(state_dir, int(state["pid"]))
    if state:
        _state_path(state_dir).unlink(missing_ok=True)

    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "bridge.log"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "serve",
        "--state-dir",
        str(state_dir),
        "--listen-host",
        listen_host,
        "--listen-port",
        str(args.listen_port),
        "--upstream-host",
        upstream_host,
        "--upstream-port",
        str(upstream_port),
    ]
    with log_path.open("ab") as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = _read_state(state_dir)
        if state and state.get("pid") == process.pid and _owned_process(process.pid):
            _emit(status="started", **state)
            return 0
        if process.poll() is not None:
            break
        time.sleep(0.05)
    if process.poll() is None:
        process.terminate()
    raise BridgeError("Proxy bridge did not become ready")


def _stop(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    state = _read_state(state_dir)
    if not state:
        _emit(status="stopped")
        return 0
    pid = int(state.get("pid", 0))
    if not _owned_process(pid):
        _state_path(state_dir).unlink(missing_ok=True)
        _emit(status="stale_state_removed")
        return 0
    _terminate_owned_process(state_dir, pid)
    _emit(status="stopped")
    return 0


def _status(args: argparse.Namespace) -> int:
    state = _read_state(Path(args.state_dir))
    if state and _owned_process(int(state.get("pid", 0))):
        _emit(status="running", **state)
        return 0
    _emit(status="stopped")
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.set_defaults(state_dir=str(DEFAULT_STATE_DIR))
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    start.add_argument("--upstream", required=True)
    start.add_argument("--listen-port", type=int, default=DEFAULT_LISTEN_PORT)

    stop = subparsers.add_parser("stop")
    stop.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))

    status = subparsers.add_parser("status")
    status.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))

    serve = subparsers.add_parser("serve")
    serve.add_argument("--state-dir", required=True)
    serve.add_argument("--listen-host", required=True)
    serve.add_argument("--listen-port", required=True, type=int)
    serve.add_argument("--upstream-host", required=True)
    serve.add_argument("--upstream-port", required=True, type=int)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.command == "start":
            return _start(args)
        if args.command == "stop":
            return _stop(args)
        if args.command == "status":
            return _status(args)
        return _serve(args)
    except (BridgeError, OSError, subprocess.SubprocessError, ValueError) as error:
        _emit(status="error", classification=type(error).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
