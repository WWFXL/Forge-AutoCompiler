#!/usr/bin/env python3
"""用户确认RichLab路由/响应标签差异后的独立身份；旧停止证据保持。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import forge_build_experience_comparison as original

base, ROOT = original.base, original.ROOT
PARENT_SESSION = original.SESSION
SESSION = PARENT_SESSION / "richlab-route-v1"
MAIN_ID = "cpp-build-state-experience-route-comparison-flash-v1"
UPDATE_ID = "cpp-build-experience-route-update-flash-v1"
EXTRACT_ID = "cpp-build-state-experience-distillation-richlab-route-v1"
PREREG = "benchmarks/preregistrations/cpp-build-state-experience-richlab-route-v1.md"


def prepare():
    SESSION.mkdir()
    auth = copy.deepcopy(base.load(PARENT_SESSION / "authorization.json"))
    auth.update(
        identities=[EXTRACT_ID, MAIN_ID, UPDATE_ID],
        requested_extraction_model="gpt-6-astra",
        accepted_response_models=["gpt-5.6", "gpt-6-astra"],
        backend_identity_verified=False,
        route_disclosure_authorized_at_utc=datetime.now(UTC).isoformat(),
        parent_authorization=str(PARENT_SESSION / "authorization.json"),
        original_identity_stop=str(PARENT_SESSION / "distillation-closure.json"),
        prior_cost_usd="0.014068",
        scope="原36＋12比较范围，不重置时窗或目标预算",
    )
    original.save(SESSION / "authorization.json", auth)
    original.save(SESSION / "sources.json", base.load(PARENT_SESSION / "sources.json"))
    for new, old in ((MAIN_ID, original.MAIN_ID), (UPDATE_ID, original.UPDATE_ID)):
        parent = ROOT / "benchmarks/manifests" / (old + ".json")
        candidate = copy.deepcopy(base.load(parent))
        candidate.update(
            identity=new,
            parent_prelaunch_candidate=dict(
                path=str(parent.relative_to(ROOT)),
                sha256=base.digest(parent),
                launched=False,
            ),
            seed_sources={
                **candidate["seed_sources"],
                "path": str(SESSION / "sources.json"),
                "sha256": base.digest(SESSION / "sources.json"),
            },
            extraction_provider=dict(
                requested_model="gpt-6-astra",
                accepted_response_models=auth["accepted_response_models"],
                backend_identity_verified=False,
                interpretation="RichLab路由标签与响应标签明确披露，不作官方模型能力或强弱模型比较",
            ),
        )
        for path in ("scripts/forge_build_experience_route_comparison.py", PREREG):
            candidate["components"][path] = base.digest(ROOT / path)
        original.save(ROOT / "benchmarks/manifests" / (new + ".json"), candidate)
    original.save(
        SESSION / "protocol-bindings.json",
        {
            name: base.digest(ROOT / "benchmarks/manifests" / (name + ".json"))
            for name in (MAIN_ID, UPDATE_ID)
        },
    )


def extract_one(source, folder):
    import tomllib

    from openai import OpenAI

    folder.mkdir()
    auth = base.load(SESSION / "authorization.json")
    original.system.OperationWindow(auth["deadline_utc"]).request()
    config = tomllib.loads(Path("/home/yiwei/.codex/config.toml").read_text())
    endpoint = config["model_providers"][config["model_provider"]]["base_url"]
    key = base.load(Path("/home/yiwei/.codex/auth.json"))["OPENAI_API_KEY"]
    kwargs = dict(
        model="gpt-6-astra",
        instructions=original.EXTRACT_PROMPT
        + json.dumps(original.Extraction.model_json_schema(), ensure_ascii=False),
        input=json.dumps(
            {
                k: v
                for k, v in source.items()
                if k not in ("raw_context", "retrieval_text")
            },
            ensure_ascii=False,
        ),
        max_output_tokens=8192,
        reasoning={"effort": "high"},
        store=False,
    )
    original.save(folder / "request.json", kwargs)
    client = OpenAI(base_url=endpoint, api_key=key, timeout=240, max_retries=0)
    started = time.monotonic()
    try:
        response = client.responses.create(**kwargs)
    except Exception as exc:
        original.save(
            folder / "failure.json",
            dict(
                error_class=type(exc).__name__,
                http_status=getattr(exc, "status_code", None),
                unknown_usage=True,
            ),
        )
        raise RuntimeError("Provider异常，无自动重试") from None
    finally:
        client.close()
    original.save(folder / "response.json", response.model_dump(mode="json"))
    if response.usage is None:
        original.save(
            folder / "failure.json",
            dict(unknown_usage=True, error="response_without_usage"),
        )
        raise RuntimeError("经验提炼用量未知")
    usage = response.usage
    receipt = dict(
        requested_model="gpt-6-astra",
        response_model=response.model,
        backend_identity_verified=False,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        cost_usd=str(Decimal(usage.total_tokens) / 1_000_000),
        wall_seconds=time.monotonic() - started,
        price_basis=auth["pricing"],
    )
    original.save(folder / "usage.json", receipt)
    if response.model not in auth["accepted_response_models"]:
        raise RuntimeError("新身份仍遇未授权的响应标识")
    try:
        entries = original.validate_extraction(json.loads(response.output_text), source)
    except (ValueError, TypeError) as exc:
        original.save(
            folder / "rejected.json",
            dict(error=str(exc), source_id=source["source_id"]),
        )
        entries = []
    original.save(folder / "entries.json", entries)
    return entries, receipt


def extract():
    root = SESSION / "distillation"
    root.mkdir()
    sources, entries = base.load(SESSION / "sources.json"), []
    complete, error = False, None
    try:
        for index, source in enumerate(sources, 1):
            new, receipt = extract_one(source, root / f"source-{index}")
            entries.extend(new)
            print(
                json.dumps(
                    dict(source=source["source_id"], entries=len(new), usage=receipt),
                    ensure_ascii=False,
                ),
                flush=True,
            )
        complete = True
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        # 从所有原收据累计，包括身份或内容异常的已付响应。
        receipts = [base.load(p) for p in root.glob("source-*/usage.json")]
        unknown = sum(
            base.load(p).get("unknown_usage", False)
            for p in root.glob("source-*/failure.json")
        )
        original.save(
            root / "result.json",
            dict(
                identity=EXTRACT_ID,
                provider_requests=len(list(root.glob("source-*/request.json"))),
                observed=len(receipts),
                planned=len(sources),
                entries=len(entries),
                complete=complete,
                unknown_usage=unknown,
                error=error,
                cost_usd=str(
                    sum((Decimal(r["cost_usd"]) for r in receipts), Decimal(0))
                ),
                release=subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip(),
            ),
        )
    cost = base.load(root / "result.json")["cost_usd"]
    original.save(
        SESSION / "seed-bank.json",
        dict(
            sources=sources,
            entries=entries,
            preparation_cost_usd=cost,
            requested_model="gpt-6-astra",
            response_models=sorted({r["response_model"] for r in receipts}),
            backend_identity_verified=False,
        ),
    )


def configure():
    original.SESSION = SESSION
    original.MAIN_ID = MAIN_ID
    original.UPDATE_ID = UPDATE_ID
    original.OUTPUTS = {
        MAIN_ID: PARENT_SESSION.parent
        / "forge-state-experience-route-comparison-flash-v1",
        UPDATE_ID: PARENT_SESSION.parent / "forge-experience-route-update-flash-v1",
    }
    original.extract_one = extract_one


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "extract", "main", "update"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "extract":
        extract()
    else:
        configure()
        original.run(MAIN_ID if args.action == "main" else UPDATE_ID)


if __name__ == "__main__":
    main()
