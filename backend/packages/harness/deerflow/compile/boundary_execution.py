"""三策略共用的独立B入口；原始记录和replay执行同一个边界包装。"""

from __future__ import annotations

from deerflow.compile.generated_file_boundary import guarded_command, original_command
from deerflow.compile.plan_agent_canary import ToolBuildService
from deerflow.compile.source_preparation import PreparedWorkflow


class BoundaryWorkflow(PreparedWorkflow):
    def __init__(self, *, boundary, **kwargs):
        self.boundary = boundary
        super().__init__(**kwargs)

    def _command_evidence(self, record):
        row = super()._command_evidence(record)
        row["command"] = original_command(self.boundary, record.command)
        row["file_boundary_sha256"] = self.boundary.fingerprint()
        return row


class BoundaryToolService(ToolBuildService):
    def __init__(self, *, boundary, **kwargs):
        self.boundary = boundary
        super().__init__(**kwargs)

    def execute(self, command, role, workdir):
        return super().execute(guarded_command(self.boundary, command, workdir), role, workdir)

    def observe(self):
        row = super().observe()
        for record in row["commands"]:
            record["command"] = original_command(self.boundary, record["command"])
        row["file_boundary_sha256"] = self.boundary.fingerprint()
        return row
