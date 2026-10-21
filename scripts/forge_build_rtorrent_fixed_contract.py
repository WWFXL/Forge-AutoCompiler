"""固定系统验证脚本的共同引用/按需只读；执行器仍消费原合同全文。"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from unittest.mock import patch

from forge_build_full_strategy_runtime import StrategyMeter
from forge_build_rtorrent_common import run_strategy as original_run_strategy
from forge_build_rtorrent_shared_values import encode_packet, restore_values
from langchain_core.tools import tool

from deerflow.compile import plan_agent_context as context_module
from deerflow.compile import plan_agent_provenance as provenance_module
from deerflow.compile import unified_plan_equivalent_observed as observed_module
from deerflow.compile.plan_agent_context import EvidenceWorkingSet
from deerflow.compile.plan_workflow import PlanContractError
from deerflow.compile.recovery_text_factors import restore_factor_packet
from deerflow.compile.shared_text_packet import canonical

PREFIX = "forge-fixed-verifier://sha256/"
META = "forge_fixed_verifier_contracts"
FORMAT = "forge-fixed-verifier-reference-v1"
CONTRACT_PROMPT = (
    "\nforge-fixed-verifier://sha256/开头的command是系统固定验证脚本的非执行引用，不是Shell。"
    "完整原脚本仍由固定验证器执行，不能修改/跳过；需要检查全文时用read_fixed_contract按SHA/start_char分段只读。"
    "Workflow仅返回dependency/configure/build动作，系统装配原固定测试和交付；强工具通过run_fixed_tests执行原全文。"
    "引用不包含正确构建方案；先利用任务步骤metadata和源码，不需要将固定测试脚本手工抄入构建动作。"
)


def map_values(value, function):
    if isinstance(value, dict):
        return {k: map_values(v, function) for k, v in value.items()}
    if isinstance(value, list):
        return [map_values(v, function) for v in value]
    return function(value)


class FixedVerifierRegistry:
    def __init__(self, task):
        self.commands, self.step_ids = {}, {}
        for step in task["verification_steps"]:
            command = step["command"]
            if len(command.encode()) < 1024:
                continue
            digest = sha256(command.encode()).hexdigest()
            if digest in self.commands and self.commands[digest] != command:
                raise PlanContractError("固定验证脚本SHA冲突")
            self.commands[digest] = command
            self.step_ids.setdefault(digest, []).append(step["step_id"])
        self.sha256 = sha256(canonical(self.commands)).hexdigest()
        self.metadata = {
            key: dict(
                step_ids=self.step_ids[key],
                utf8_bytes=len(command.encode()),
                characters=len(command),
                access_tool="read_fixed_contract",
                system_owned=True,
            )
            for key, command in self.commands.items()
        }

    def project(self, packet):
        if META in packet:
            raise PlanContractError("固定验证合同元数据冲突")
        references = {command: PREFIX + key for key, command in self.commands.items()}
        result = map_values(
            packet,
            lambda value: references.get(value, value) if isinstance(value, str) else value,
        )
        if not self.commands:
            return result
        result[META] = dict(
            format=FORMAT,
            registry_sha256=self.sha256,
            commands=self.metadata,
            original_canonical_sha256=sha256(canonical(packet)).hexdigest(),
            instruction=CONTRACT_PROMPT,
        )
        if self.restore(result) != packet:
            raise PlanContractError("固定验证合同引用未完整保留原包")
        return result

    def restore(self, view):
        if not self.commands:
            if META in view:
                raise PlanContractError("不存在固定长脚本时出现合同元数据")
            return copy.deepcopy(view)
        meta = view.get(META)
        if not isinstance(meta, dict) or meta.get("format") != FORMAT or meta.get("registry_sha256") != self.sha256 or meta.get("commands") != self.metadata:
            raise PlanContractError("固定验证合同来源或元数据错误")

        def expand(value):
            if isinstance(value, str) and value.startswith(PREFIX):
                key = value[len(PREFIX) :]
                if key not in self.commands:
                    raise PlanContractError("未知固定验证脚本引用")
                return self.commands[key]
            return value

        result = map_values({k: v for k, v in view.items() if k != META}, expand)
        if sha256(canonical(result)).hexdigest() != meta.get("original_canonical_sha256"):
            raise PlanContractError("固定验证合同还原完整哈希错误")
        return result

    def read(self, command_sha256, start_char=0):
        if command_sha256 not in self.commands or type(start_char) is not int or not 0 <= start_char <= len(self.commands[command_sha256]):
            return dict(
                accepted=False,
                error="unknown_contract_or_invalid_range",
                read_request=dict(command_sha256=command_sha256, start_char=start_char),
            )
        command = self.commands[command_sha256]
        content = command[start_char : start_char + 4000].encode()[:8000].decode(errors="ignore")
        end = start_char + len(content)
        return dict(
            accepted=True,
            command_sha256=command_sha256,
            sha256=command_sha256,
            registry_sha256=self.sha256,
            content=content,
            start_char=start_char,
            total_chars=len(command),
            next_char=end if end < len(command) else None,
            read_request=dict(command_sha256=command_sha256, start_char=start_char),
        )

    def tool(self):
        @tool
        def read_fixed_contract(command_sha256: str, start_char: int = 0) -> str:
            """只读系统固定验证脚本；仅接受已声明SHA，按字符偏移读取最多4000字符/8000字节，next_char指向下一段；不能修改或执行。"""
            return json.dumps(self.read(command_sha256, start_char), ensure_ascii=False)

        return read_fixed_contract


class ContractWorkingSet(EvidenceWorkingSet):
    def observe(self, name, arguments, content):
        if name != "read_fixed_contract":
            return super().observe(name, arguments, content)
        row = json.loads(content)
        self.index.append(
            dict(
                tool=name,
                request=arguments,
                accepted=row.get("accepted") is True,
                sha256=row.get("sha256"),
            )
        )
        if row.get("accepted"):
            key = (name, row["command_sha256"], row["start_char"])
            self.entries.pop(key, None)
            self.entries[key] = {"tool": name, **row}
        self.trim()


class ContractMeter(StrategyMeter):
    """只改变共同材料和可读合同工具；资源/计量与原门禁保持。"""

    def __init__(self, *args, registry, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = registry
        self.working_set = ContractWorkingSet()
        self.tracker.limits = replace(
            self.tracker.limits,
            max_model_requests=self.tracker.limits.max_agent_steps + 1,
        )
        self.ledger.append(
            "authorization.request_policy",
            independent_request_cap=None,
            automatic_retry=False,
            technical_request_ceiling="max_agent_steps + 1; nonbinding",
        )
        self.ledger.save(
            "fixed-verifier-contracts.json",
            dict(
                format=FORMAT,
                commands=registry.commands,
                registry_sha256=registry.sha256,
                metadata=registry.metadata,
            ),
        )
        original = self.packet
        self.contract_material_sequence = 0

        def packet():
            projected = original()
            view = registry.project(projected)
            encoded = encode_packet(view)
            if registry.restore(restore_values(restore_factor_packet(encoded))) != projected:
                raise PlanContractError("共同固定验证合同表示不能完整还原")
            self.contract_material_sequence += 1
            self.ledger.save(
                f"contract-material-{self.contract_material_sequence}.json",
                dict(projected=projected, view=view, encoded=encoded),
            )
            return encoded

        self.packet = packet


@contextmanager
def contract_interfaces(registry):
    def tools(original):
        return lambda source, session: [*original(source, session), registry.tool()]

    with (
        patch.object(
            observed_module,
            "safe_readonly_tools",
            tools(observed_module.safe_readonly_tools),
        ),
        patch.object(
            provenance_module,
            "safe_readonly_tools",
            tools(provenance_module.safe_readonly_tools),
        ),
        patch.object(
            context_module,
            "safe_readonly_tools",
            tools(context_module.safe_readonly_tools),
        ),
        patch.object(
            observed_module,
            "OBSERVED_PROMPT",
            observed_module.OBSERVED_PROMPT + CONTRACT_PROMPT,
        ),
        patch.object(
            provenance_module,
            "AUTOMATIC_PROMPT",
            provenance_module.AUTOMATIC_PROMPT + CONTRACT_PROMPT,
        ),
        patch.object(
            context_module,
            "CONTEXT_PROMPT",
            context_module.CONTEXT_PROMPT + CONTRACT_PROMPT,
        ),
    ):
        yield


def run_strategy(*, method, item, protocol, root, model, meter_factory=ContractMeter, **kwargs):
    registry = FixedVerifierRegistry(item["task"])
    with contract_interfaces(registry):
        return original_run_strategy(
            method=method,
            item=item,
            protocol=protocol,
            root=root,
            model=model,
            meter_factory=lambda *args, **options: meter_factory(*args, registry=registry, **options),
            **kwargs,
        )
