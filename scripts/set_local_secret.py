#!/usr/bin/env python3
"""Atomically update an allowed secret in the Git-ignored local .env file."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_NAMES = {"DEEPSEEK_API_KEY", "FORGE_MODEL_PROXY_BRIDGE_PORT", "FORGE_MODEL_PROXY_UPSTREAM", "OpenAI_AK"}
SECRET_RE = re.compile(r"^sk-[A-Za-z0-9_-]+$")
PROXY_RE = re.compile(r"^http://(?:127\.0\.0\.1|localhost):[1-9][0-9]{0,4}/?$")
PORT_RE = re.compile(r"^[1-9][0-9]{0,4}$")


class SecretError(RuntimeError):
    """Raised when a local secret update is unsafe."""


def update_env(path: Path, name: str, value: str) -> None:
    if name not in ALLOWED_NAMES:
        raise SecretError("Unsupported secret variable")
    valid = {
        "DEEPSEEK_API_KEY": SECRET_RE,
        "OpenAI_AK": SECRET_RE,
        "FORGE_MODEL_PROXY_UPSTREAM": PROXY_RE,
        "FORGE_MODEL_PROXY_BRIDGE_PORT": PORT_RE,
    }[name].fullmatch(value)
    if not valid:
        raise SecretError("Local value does not match the expected format")
    if path.is_symlink():
        raise SecretError("Refusing to update a symlink")

    existing = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    lines = existing.splitlines()
    replacement = f"{name}={value}"
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(f"{name}="):
            if not replaced:
                output.append(replacement)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        if output and output[-1] != "":
            output.append("")
        output.append(replacement)

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(output).rstrip("\n") + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", choices=sorted(ALLOWED_NAMES), required=True)
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    args = parser.parse_args()
    value = sys.stdin.read().strip() if not sys.stdin.isatty() else getpass.getpass(f"{args.name}: ").strip()
    try:
        update_env(args.env_file, args.name, value)
    except (OSError, SecretError) as error:
        print(json.dumps({"updated": False, "name": args.name, "classification": type(error).__name__}, sort_keys=True))
        return 2
    print(json.dumps({"updated": True, "name": args.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
