# Opaque provenance rejection observability R0 preregistration

- Issue: #194
- Schema: `forge-opaque-provenance-rejection-observability-gate-1.0.0`
- Scope: experiment-active `agent.tool_failed` evidence only
- Provider calls: 0
- Formal physical attempts: 0
- Model tokens: 0
- Docker: disabled
- Credential access: disabled
- Historical evidence mutation: forbidden

## Atomic observation

Enriched rejection evidence must contain all or none of:

1. `rejection_classification`
2. `action_kind`
3. `model_request_id`
4. `tool_ordinal`
5. `command_sha256`

The raw command, tool arguments, error message, prompt, response, credential, and secret hash remain forbidden. Unknown or ambiguous tool-call origins must use the historical seven-field `agent.tool_failed` payload rather than emit a partial observation.

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

Stop before any R1 checkpoint candidate if a classification is ambiguous, the atomic field group can be partially accepted, a tool origin is correlated incorrectly, a raw value is persisted, historical seven-field events no longer validate, or the gate accesses provider, Docker, credentials, or frozen evidence.
