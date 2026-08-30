# Opaque provenance rejection observability R0 preregistration

- Issue: #194
- Schema: `forge-opaque-provenance-rejection-observability-gate-1.0.0`
- Scope: experiment-active legacy `agent.tool_failed` plus versioned companion observation
- Provider calls: 0
- Formal physical attempts: 0
- Model tokens: 0
- Docker: disabled
- Credential access: disabled
- Historical evidence mutation: forbidden

## Atomic observation

Historical `agent.tool_failed` remains byte- and Schema-compatible with its seven fields. A linked `agent.tool_rejection_observed` companion event contains `failure_id` plus all or none of:

1. `rejection_classification`
2. `action_kind`
3. `model_request_id`
4. `tool_ordinal`
5. `command_sha256`

The raw command, tool arguments, error message, prompt, response, credential, and secret hash remain forbidden. Unknown or ambiguous tool-call origins emit only the historical seven-field `agent.tool_failed` event rather than a partial companion observation. The R0 adapter and registry are versioned experiment components; shared historical evidence and model/tool-error middleware files remain byte-identical.

## Deterministic gate cases

The zero-provider gate must distinguish:

| Fixture | Rejection classification | Action kind |
| --- | --- | --- |
| compound inspection shell | `compound_shell_forbidden` | `inspection` |
| unsupported `command_role` | `invalid_command_role` | `command` |
| frozen build directory drift | `repair_build_directory_drift` | `repair_build` |
| frozen staged artifact drift | `artifact_stage_identity_drift` | `artifact_stage` |
| fifth inspection claim | `inspection_budget_exhausted` | `inspection` |

All five failures share one synthetic model request and must preserve request-local tool ordinals `1..5`. Their `command_sha256` values must match the in-memory tool calls while the raw commands remain absent from the temporary ledger.

## Stop rules

Stop before any R1 checkpoint candidate if a classification is ambiguous, the companion field group can be partially emitted, a failure link or tool origin is correlated incorrectly, a raw value is persisted, historical seven-field events or frozen shared component hashes drift, or the gate accesses provider, Docker, credentials, or frozen evidence.
