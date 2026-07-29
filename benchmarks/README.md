# Forge C/C++ benchmark protocols

## Post-v7 runtime launch gate

The five v7 physical attempts are complete and immutable. Later runner changes
must not be used to retry, replace, or backfill a v7 slot.

Before freezing a future protocol, verify the runner process and evidence mount
from inside the LangGraph Compose container:

```bash
/app/backend/.venv/bin/python /app/scripts/forge_benchmark_runner.py \
  runtime-preflight \
  --output-dir /workspace/.compile-sessions/benchmark-evidence-v8
```

The gate requires the backend virtual environment, required runtime imports, the
`deer-flow-dev` LangGraph service, a writable Docker socket, and a writable bind
mount at `/workspace/.compile-sessions`. It also writes and removes a temporary
sentinel in the specified output directory. Only bounded booleans are printed;
container source paths, credentials, exception text, and environment values are
not emitted.

Both `preflight` and `create-attempt` now require an explicit `--output-dir`.
Launch-gate failure occurs before a physical-attempt ID or ledger is created.
The current shared runner intentionally no longer passes the v7 current-tree
collection gate; v7 Git blobs and existing ledgers remain the historical source
of truth.

## Provider canary after v7

Issue #63 defines a non-pilot, single-attempt canary for comparing the RichLab
and DeepSeek provider paths before designing v8. Both conditions use the same
commit-pinned CMake repository and the complete Compile Session plus clean
replay lifecycle. They run serially, never fall back to another model, and
write separate evidence outside the frozen v1-v7 ledgers.

Run each condition from the `deer-flow-dev` LangGraph container with the
backend virtual-environment interpreter:

```bash
/app/backend/.venv/bin/python /app/scripts/forge_provider_canary.py \
  --model gpt-5.5 \
  --output-dir /workspace/.compile-sessions/provider-canary-evidence/richlab

/app/backend/.venv/bin/python /app/scripts/forge_provider_canary.py \
  --model deepseek-v4-flash \
  --output-dir /workspace/.compile-sessions/provider-canary-evidence/deepseek
```

The runner emits only bounded status, counts, timings, identities, and boolean
acceptance gates. It does not emit model text, tool arguments, command output,
credentials, or host paths. A failed condition is preserved as-is and is not
retried or replaced.

## Runnable pilot v7 protocol

`cpp-pilot-v7.json` is the five-case protocol frozen after the v6 calibration exposed three instrumentation gaps. Its runtime baseline includes the Issue #50 pre-build argument gate, Issue #51 separate compiler budgets, and Issue #52 structured artifact-oracle diagnostics. It preserves every v1-v6 manifest, schema, validator, and ledger as historical evidence.

The runtime implementation baseline is `c48a0008d788e0cee05de70df5ff3cefe483f40e`. The v7 protocol keeps the same exact-commit C/C++ cases, CMake/Make/Autotools paths, `compose-dood` control plane, immutable compile image, Compile Session, clean replay, `gpt-5.6-sol` for both roles, RichLab `/v1` endpoint, 120-second provider timeout, zero retries, forbidden fallback, and disabled Memory/Skills.

Compiler limits are no longer overloaded:

- `model_turn_limit: 36` preserves the v6 model-search allowance.
- `graph_recursion_limit: 96` independently covers up to 36 model nodes plus bounded tool and routing nodes.
- `wall_clock_timeout_seconds: 900` gives dependency and native compilation a bounded 15-minute window.
- `post_build_reserve_seconds: 120` reserves deterministic time for submit, clean replay initiation, delivery, and finalization after a successful build.

Validate the protocol from a clean committed Windows or WSL2 checkout, then run preflight inside the frozen Compose/DooD control plane:

```powershell
python scripts/forge_benchmark_v7.py validate-manifest benchmarks/manifests/cpp-pilot-v7.json
```

```bash
python3 scripts/forge_benchmark_runner.py preflight \
  --manifest benchmarks/manifests/cpp-pilot-v7.json
```

Protocol validation and `ready: true` do not themselves authorize collection. Do not create a v7 physical-attempt ledger or issue a model request until the protocol PR is merged and collection is approved as a separate step. Once collection starts, keep the five cases serial, do not retry or replace a consumed slot, and do not pool v7 outcomes with v1-v6.

## Runnable pilot v5

`cpp-pilot-v5.json` is the five-case calibration protocol for the runtime that includes the Issue #32 event-loop ownership fix, Issue #33 non-interactive progress repair, and Issue #34 capability/selection/execution identity contract. It preserves every v1-v4 protocol artifact and physical-attempt ledger, keeps `control_plane_topology: "compose-dood"`, and creates a separate v5 evidence stratum.

The runtime implementation baseline is `afe57d60632b6e49cc951185df0f525f6bb1f294`. A clean runtime HEAD must contain that commit as an ancestor and its 22 frozen runtime components must match the baseline. The model and execution controls remain unchanged: `gpt-5.6-sol` for both roles, the RichLab `/v1` endpoint, `OpenAI_AK`, a 120-second request timeout, zero provider retries, no fallback, one serial backend run, and disabled Memory/Skills.

Every executed v5 attempt records a bounded `build.identity_snapshot`. The snapshot keeps repository build-system capabilities, the manifest-selected path, and the path proven by the supporting build command as separate facts. A switched path is retained as observed evidence and rejected by the offline identity gate; a missing observation remains `null` and is never backfilled from the manifest. The v5 run-record source carries the same three explicit fields.

Validate the manifest on Windows and WSL, then run preflight in the frozen Compose/DooD environment:

```powershell
python scripts/forge_benchmark_v5.py validate-manifest benchmarks/manifests/cpp-pilot-v5.json
```

```bash
python3 scripts/forge_benchmark_runner.py preflight \
  --manifest benchmarks/manifests/cpp-pilot-v5.json
```

Only `ready: true` on a clean committed tree authorizes collection. Create and run one new v5 physical attempt for each of the five cases, strictly serially. Do not pass `--replacement-for`, edit or delete any v1-v4 ledger, or pool outcomes across protocol versions. Once the first v5 ledger is created, the v5 manifest and protocol artifacts are frozen for that collection stratum.

## Historical pilot v4

`cpp-pilot-v4.json` is the five-case calibration protocol for the runtime that includes the Issue #24 async-only compiler delegation fix, Issue #25 expected/observed build-system identity gate, and Issue #26 bounded agent tool-failure and no-compile-progress evidence. It preserves every v1/v2/v3 protocol artifact and existing physical-attempt ledger, keeps `control_plane_topology: "compose-dood"`, and creates a separate v4 evidence stratum.

The runtime implementation baseline is the reviewed PR #29 squash commit `1e4bad22117ad01058310a8625925e7801a8eff2`. A clean runtime HEAD must contain that commit as an ancestor and its 21 frozen runtime components must match the baseline. The five cases and execution controls remain unchanged from v3: `gpt-5.6-sol` for both roles, the RichLab `/v1` endpoint, `OpenAI_AK`, a 120-second request timeout, zero provider retries, no fallback, one serial backend run, and disabled Memory/Skills.

Validate the manifest on Windows and WSL, then run preflight in the frozen Compose/DooD environment:

```powershell
python scripts/forge_benchmark_v4.py validate-manifest benchmarks/manifests/cpp-pilot-v4.json
```

```bash
python3 scripts/forge_benchmark_runner.py preflight \
  --manifest benchmarks/manifests/cpp-pilot-v4.json
```

Only `ready: true` on a clean committed tree authorizes collection. Collection is a later, separately authorized step: create and run one new v4 physical attempt for each of the five cases, strictly serially. Do not pass `--replacement-for`, edit or delete a v1/v2/v3 ledger, or pool outcomes across protocol versions. Once the first v4 ledger is created, the v4 manifest and protocol artifacts are frozen for that collection stratum.

## Historical pilot v3

`cpp-pilot-v3.json` is the completed five-case calibration protocol for the runtime that includes the Issue #16 exact-clone ownership fix, Issue #17 runner/session terminalization fix, and Issue #18 provider-reported model identity extraction. It preserves every v1/v2 protocol artifact and existing physical-attempt ledger, keeps `control_plane_topology: "compose-dood"`, and creates a separate v3 evidence stratum. Its five physical attempts are immutable historical evidence and must not be rerun, replaced, or pooled with another protocol version.

The runtime implementation baseline is `371f678e07acc6ae87f80d7544f573332d74fa88`. The reviewed fixes were later restacked and squash-merged, so current main no longer has that old branch commit as an ancestor and is not tree-equivalent to it. Historical audit verifies every frozen runtime blob at the original baseline and every protocol artifact blob at the PR #23 protocol commit `c4b817f315515d8afcc26d572151276aef7bece4`, then requires the inspected HEAD to descend from that protocol commit. This keeps later reviewed runner changes compatible with historical provenance without treating the changed working tree as a valid v3 collection runtime. The model and execution controls remain unchanged from v2: `gpt-5.6-sol` for both roles, the RichLab `/v1` endpoint, `OpenAI_AK`, a 120-second request timeout, zero provider retries, no fallback, one serial backend run, and disabled Memory/Skills.

Validate the frozen manifest and audit its Git provenance with:

```powershell
python scripts/forge_benchmark_v3.py validate-manifest benchmarks/manifests/cpp-pilot-v3.json
python scripts/forge_benchmark_history.py benchmarks/manifests/cpp-pilot-v3.json
```

The old v3 current-tree preflight is expected to reject later reviewed runtime drift. That rejection preserves the frozen collection boundary; it is not permission to rewrite the manifest or create replacement attempts.

## Historical pilot v2

`cpp-pilot-v2.json` is the runnable five-case calibration protocol created after the Issue #11 evidence ledger landed. It keeps the v1 manifest, validator, and Schema byte-for-byte unchanged, freezes the expanded runtime/evidence component set, and records `control_plane_topology: "compose-dood"`. The v2 baseline uses `gpt-5.6-sol` for both roles, 120-second provider timeouts, zero provider retries, no fallback, and disabled Memory/Skills.

The Forge commit in v2 is an implementation baseline, not a self-referential protocol commit. At collection time, the clean runtime HEAD had to contain `d845b735576be706f79fcf0666f66c14929a52cc` as an ancestor while every frozen runtime component still matched that baseline. That launch rule permitted protocol-only commits without allowing runtime drift.

Validate v2 from Windows and WSL before collection, then run preflight in the frozen Compose/DooD environment:

```powershell
python scripts/forge_benchmark_v2.py validate-manifest benchmarks/manifests/cpp-pilot-v2.json
```

```bash
python3 scripts/forge_benchmark_runner.py preflight \
  --manifest benchmarks/manifests/cpp-pilot-v2.json
```

Only `ready: true` authorizes `create-attempt` and a later explicit `run`. Evidence must exist before the first model request. The `run` command additionally verifies that its own process is the `deer-flow-dev` LangGraph Compose service with the host Docker socket mounted read/write; finding an unrelated Compose service from a WSL-native process is not sufficient. The five cases run serially; replacements preserve the original ledger and require `--replacement-for`. The v2 protocol remains pilot calibration, not a formal comparison.

After Issue #11 was rebased and squash-merged, Git ancestry no longer connected the historical baseline to `main`. Audit the frozen v2 assets with the reviewed provenance mapping instead of editing the manifest or pretending the squash commit is the original baseline:

```bash
python3 scripts/forge_benchmark_history.py
```

The audit verifies baseline Git blobs, the reviewed rebased source tree, the exact squash-successor tree, and successor ancestry to the requested HEAD. A disconnected commit is rejected even if it has similar files. This command validates historical provenance only; it does not authorize a new v2 attempt, replacement, or replay.

## Historical protocol v1

This directory defines an auditable pilot protocol for Forge-AutoCompiler. The pilot is **only a clean-replay evidence collection and calibration run**. It is not a formal comparison of exit-code-only, candidate-only, and clean-replay acceptance, and it is not a claim about population-level build performance.

The five repositories are a self-selected calibration set. They are not presented as members of an official CXXCrafter benchmark.

## Versioned files

- `manifests/cpp-pilot-v1.json` freezes the exact pilot inputs and runtime.
- `schemas/forge-cpp-benchmark-v1.schema.json` is a JSON Schema Draft 2020-12 contract for both `document_type: "manifest"` and `document_type: "run_record"` documents.
- `scripts/forge_benchmark.py` validates the manifest and converts local compile-session evidence to append-only normalized JSONL.

Schema version `1.0.0` accepts one baseline condition, exactly five cases, and only C/C++ projects using CMake, Make, or Autotools. Every repository is HTTPS-only and pinned by a complete 40- or 64-character Git object ID. Symbolic, abbreviated, credentialed, query-bearing, and fragment-bearing repository references are invalid.

The manifest's `protocol_artifact_sha256` object freezes the literal bytes of the recorder and this schema. `validate-manifest` resolves those two repository-relative paths, rejects symlinks or path escapes, and compares each file's SHA-256 before accepting the manifest. Editing either protocol artifact therefore invalidates the manifest even when the JSON shape is unchanged.

## Pilot question and boundary

The pilot asks whether the current system can collect complete, bounded evidence for commit-pinned candidate generation and automatic clean replay across a small, deliberately varied C/C++ set. It calibrates collection failures, candidate acceptance, clean-replay acceptance, cleanup, duration, and missing-data handling before model budget is spent on a larger experiment.

The baseline has all of these invariants:

- one backend process and one run at a time;
- the same frozen model for the lead and compiler roles, with fallback forbidden;
- the model endpoint, retry count, request timeout, subagent timeout, and compiler turn limit frozen in the manifest;
- Memory disabled and Skills disabled for every run;
- the original immutable compile image ID, Docker network policy, WSL/Docker facts, and Forge commit/component hashes frozen;
- `clean_replay` as the only acceptance gate used to complete a pilot run.

Memory, Skills, verifier-driven repair, model fallback, parallel execution, and acceptance-gate treatments are not pilot variables. They require a later, separately versioned experiment.

## Frozen cases

| Case | Exact commit | Build system | Pilot oracle |
|---|---|---|---|
| `fmt` | `123913715afeb8a437e6388b4473fcc4753e1c9a` | CMake | candidate `pass`; clean replay `pass` |
| `hiredis` | `60e5075d4ac77424809f855ba3e398df7aacefe8` | Make | candidate `pass`; clean replay `pass` |
| `libcheck` | `11970a7e112dfe243a2e68773f014687df2900e8` | Autotools | candidate `pass`; clean replay `pass` |
| `libgit2` | `338e6fb681369ff0537719095e22ce9dc602dbf0` | CMake plus system dependencies | candidate `pass`; clean replay `pass` |
| `sysstat-nondeterministic` | `b8f987807e7c7ba5c1b2ca8b7b1e9d80e61bce6c` | Autotools | candidate `pass`; clean replay `reject` |

The `sysstat-nondeterministic` case is a controlled negative, not a repository that is expected to fail to build. With `SOURCE_DATE_EPOCH` explicitly absent (represented by JSON `null`), `USE_SCCSID` embeds build time in the valid `sar` ELF. The manifest therefore requires at least two seconds between the accepted build and replay. The product's actual smoke fallback, `./sar --help`, exits zero and has stable output across the two builds, while the ELF SHA-256 changes. Candidate validation should pass and clean replay should reject specifically with `sha256_mismatch`. A candidate rejection, a clean-replay pass, or a rejection for a different reason is an oracle mismatch to investigate, not a result to edit away.

### Case-constraint launch gate

The v1 CLI validates and records experiments; it does not launch the agent or apply `cases[].constraints`. This is a manual pre-run gate. Before the first pilot call, use one reviewed, frozen launch procedure to install `required_system_packages`, pass each `build_arguments.cmake` or `build_arguments.configure` token as a distinct argument, and apply the separate process `environment` object. Do not join argument vectors into a shell string or reinterpret them as environment variables. A `SOURCE_DATE_EPOCH` value of JSON `null` means the variable must be absent from both the candidate and replay process environments; it is not the literal string `null` or `unset`.

For the sysstat case, the procedure must also create at least the declared two-second separation after compilation in both the candidate recipe and its replay. A recorded successful `sleep 2` after the build is one auditable implementation because successful Bash commands are replayed in order.

Do not start collection until the raw session can demonstrate that these controls were applied without mid-run human repair. If a constraint is missing or the minimum delay cannot be established, stop and classify the slot as a protocol deviation; do not interpret the negative oracle. Automating this launch gate belongs in the next instrumentation/runner phase.

## Gate semantics

The three gates answer different questions and must not be collapsed into one generic "build succeeded" value.

**Exit-code-only** would pass only when a predeclared supporting build command has an explicit zero exit code; it would reject on a non-zero exit code. The current session format has neither a stable command ID nor an explicit exit-code-gate decision. A successful clone, configure, dependency install, smoke command, or arbitrary last successful Bash command is not a build acceptance decision. The v1 recorder therefore does not infer this gate.

**Candidate-only** passes when at least one recognized compiled artifact survives structural validation, required executable smoke testing succeeds, and a safe commit-pinned `repro/build.sh` is generated. It rejects when any of those requirements fails. Candidate generation alone says nothing about reconstruction in a clean environment.

**Clean replay** passes only after candidate-only passes and the candidate recipe is run from the exact source commit in a new container created from the original immutable image ID with empty, attempt-specific workspace and artifact mounts. Recipe exit status, artifact set, type, size, SHA-256, executable smoke result, and cleanup must all match the accepted candidate. A generated recipe without a successful replay is a rejection. Session `completed` additionally requires successful finalization of the original compile container and rechecking the delivered artifacts.

`submit.completed` records the bounded candidate/replay decision, not necessarily successful workflow completion. A later `artifact.finalization_recheck` with `passed: false`, or a `finalize.deferred` with `reason: container_cleanup_failed` before or after submit, is retained as bounded `completion_event` evidence and sets `failure_attribution.completion` to `true`. A post-submit failure may therefore preserve candidate and clean replay as `pass` while `verification_status` is `failed`. A session that reaches `completed` must have `finalized: true`, records completion attribution as `false`, and may not retain a terminal completion failure.

`finalize.completed` records a bounded finalized lifecycle outcome rather than a completion-domain failure. For a completed session it has `reason: null` and `passed: true`; for a finalized `failed`, `cancelled`, or `timed_out` session it preserves that status as `reason` with `passed: null`. Thus a clean-replay pass followed by a finalized interruption may retain both gates as `pass` while completion attribution remains `null`.

Manifest oracle values and normalized semantic gate values are `pass` or `reject`. Raw runtime values such as replay `passed`, `failed`, `timed_out`, and `cancelled` are retained only in the bounded evidence object. An observation that cannot be reconstructed is `null`.

## Instrumentation blocker

The current `session.json` and `workflow.log` are sufficient for this small clean-replay collection/calibration pilot, but they are not sufficient for a defensible three-condition comparison. `CompileSession.verification` and `artifacts` retain only the latest submit snapshot. A terminal `submit.completed` event can carry a `replay_attempt_id`, but there is no stable `submit_attempt_id`, immutable per-submit ledger, or durable link from each replay to the exact command/check/artifact snapshot that produced it. Successful Bash records also do not identify the supporting build command. Terminal model/API errors and retry details may exist only in stream or log telemetry.

Before any formal exit-code-only versus candidate-only versus clean-replay experiment, implement and review all of the following:

1. Create an experiment-attempt record before the first model request.
2. Assign stable command, submit, replay, model-request, and physical-attempt IDs.
3. Persist immutable per-submit snapshots linking command ranges, checks, artifacts, recipe hash, and replay attempt.
4. Persist explicit gate decisions and the supporting build-command ID; never derive exit-code acceptance from an arbitrary command.
5. Capture endpoint retries, terminal API outcomes, selected model, latency, and token telemetry without response bodies or credentials.
6. Persist an ordered failure chain so cleanup or finalization cannot overwrite the primary failure.

Until that instrumentation exists, pilot records may describe observed candidate and clean-replay outcomes, but they must not support a formal effect-size, superiority, or gate-disagreement claim. [Issue #11](https://github.com/WWFXL/Forge-AutoCompiler/issues/11) tracks this blocker; the formal three-gate experiment must not start until that issue's attempt-ledger and explicit-decision requirements are implemented and reviewed.

## Failure domains

Normalized records keep failure domains separate:

- `model_endpoint`: transport, authentication, rate-limit, provider timeout, or terminal provider failure;
- `agent`: invalid orchestration, tool protocol, turn-limit, or agent termination;
- `build`: configure, dependency, compiler, linker, or build-command failure before candidate submission;
- `candidate_generation`: artifact validation, smoke testing, or replay-recipe generation failure;
- `clean_replay`: replay creation/execution, timeout, or artifact comparison failure;
- `cleanup`: replay-container cleanup failure;
- `completion`: original-container cleanup, finalization, or post-cleanup artifact-delivery failure.

A failure-attribution value of `true` means the available structured evidence positively attributes a failure to that domain. `false` means the evidence explicitly rules it out. `null` means unavailable and must not be interpreted as success. With v1 evidence, `model_endpoint`, `agent`, and `build` normally remain `null`; assigning them from friendly model messages, raw error text, or the last command would fabricate evidence. A `cleanup_failed` classification proves a cleanup-domain failure and makes the clean-replay gate reject, but the runtime can overwrite an earlier replay-body classification; `failure_attribution.clean_replay` must therefore remain `null`, not `false`, in that case.

## Record and missing-data policy

One JSONL line represents one planned `(benchmark_id, case_id, condition, repetition)` slot. The recorder rejects a duplicate slot before append. Session repository URL and commit must match the selected manifest case.

Session-backed physical attempts are retained and are never silently retried under the same slot. A failed attempt consumes its assigned repetition. The current `record` command requires `session.json`, so an endpoint or harness failure before session creation cannot yet be normalized; this is part of the instrumentation blocker, not missing-at-random data. Do not begin pilot collection without a reviewed bounded pre-session attempt ledger. If such a failure occurs before that ledger exists, stop the pilot, preserve available raw telemetry, and report the collection as incomplete rather than rerunning the slot. The pilot has no automatic replacement policy. Any authorized replacement requires an amended, reviewed manifest and a new frozen design; never overwrite or delete the original attempt to improve completion rate.

Missing observations use JSON `null`, never a fabricated `0`, `false`, empty string, `pass`, or `reject`. An observed count of zero is `0`; an observed empty artifact set from a completed submit is `[]`; and an unavailable artifact snapshot or command collection is `null`. When commands are observed, `command_summary` contains integer counters, including real zeroes; when the session has no valid command array, the whole `command_summary` is `null`. Submit state is recorded exactly as `not_observed`, `started`, `aborted`, or `completed`: `submit.started` preserves that a call entered without inventing an outcome, and non-completed submits keep artifacts, verification, candidate, and replay evidence null. Before clone/image initialization, `source.commit_sha` and `source.image_id` may also be null, while `source.session_id` and the manifest-matched `source.repository_url` remain present. A terminal replay retains its attempt/image/commit identity, cleanup result, duration, and timeout; rejected replay evidence also requires a classification. Only `image_identity_unavailable` may preserve a null replay and source image ID after a completed submit. `oracle_match` is left `null` by the collection recorder; oracle analysis is a later derived result and must not mutate source JSONL.

The raw `.compile-sessions` tree remains local, read-only evidence and is not committed. Normalized JSONL is append-only. Preserve the raw session and workflow log used for each record until the pilot audit is complete.

The recorder serializes append operations with an exclusive sibling lock named `.<output-filename>.lock`. It does not automatically reclaim a stale lock because age alone cannot prove that another recorder is dead. If a lock remains after an interruption, first verify that no live recorder owns the target output, then remove the lock manually. Record that removal as a protocol deviation with the available process and file evidence; never delete a lock merely to bypass an active or uncertain writer.

## Secrets and bounded evidence

The manifest stores only the credential environment variable name `OpenAI_AK`. It must never contain the credential value or a hash of that value. Repository URLs cannot contain userinfo, query strings, or fragments. The only permitted process-environment entries are the reviewed `CFLAGS` and `SOURCE_DATE_EPOCH` controls; build-system arguments live in their dedicated token arrays. The validator rejects additional or secret-like environment data.

Run records use a strict property whitelist. Do not add prompts, model messages or responses, command text, stdout/stderr, error text, log content, `.env` content, tokens, credentials, secret hashes, container names, host absolute paths, WSL paths, or raw session dictionaries. Artifact paths are derived only from safe `/artifacts/<relative>` source paths; if that derivation is not safe, `relative_path` is `null`. Smoke output is represented only by its SHA-256.

## Freeze and change control

Validate, review, commit, and record the manifest digest before the first pilot model call. First verify the literal protocol-artifact hashes with `validate-manifest`; then compute the manifest's canonical digest. The manifest and each normalized record declare `manifest_canonicalization: "json-sort-keys-compact-utf8"`. The canonical digest is SHA-256 over UTF-8 JSON produced after parsing with sorted object keys, no insignificant whitespace (`separators=(",", ":")`), Unicode preserved, and non-finite numbers forbidden. Every run record contains that digest. The manifest must not contain `manifest_sha256`; doing so would create a self-referential digest.

After collection starts, do not edit the manifest in place. Any change to cases, commits, oracle, required artifacts, Forge code or component hashes, model policy, prompt/tools/config/Dockerfile, image ID, host/runtime limits, condition, schema, or evidence semantics requires a new manifest identity and review. Existing JSONL remains tied to its original digest. Results from different digests are separate protocol strata and are not pooled by default.

## CLI

Run commands from the repository root. The validator uses the standard library and validates protocol invariants in addition to the JSON Schema contract. The recorder CLI is the authoritative collection validator because JSON Schema cannot express every cross-field, cross-document, or historical relation. In particular, the CLI enforces all of the following:

- `outcome.artifact_count == submit_event.artifact_count == len(artifacts)` and complete, unique accepted artifact paths;
- `submit_event.replay_attempt_id == replay_attempt.attempt_id`, plus outcome/replay status, classification, and cleanup linkage;
- `command_summary.successful_bash + command_summary.failed_bash <= command_summary.total`;
- session repository, commit, build system, compile image, and replay image/commit/timeout identity against the selected manifest case and frozen runtime, with only the bounded `image_identity_unavailable` exception;
- duplicate-slot detection across every existing line of the historical output JSONL, not just the new record.

A record that passes the Schema but has not passed the CLI and historical-output checks is not valid pilot evidence.

Validate the frozen manifest before collection:

```powershell
python scripts/forge_benchmark.py validate-manifest benchmarks/manifests/cpp-pilot-v1.json
```

Normalize one completed or interrupted session and append exactly one JSON object to a local JSONL file:

```powershell
python scripts/forge_benchmark.py record `
  --manifest benchmarks/manifests/cpp-pilot-v1.json `
  --case-id fmt `
  --condition baseline `
  --repetition 1 `
  --session-json C:\path\to\.compile-sessions\thread-id\session-id\session.json `
  --output benchmarks\results\cpp-pilot-v1.local.jsonl
```

The workflow log defaults to `logs/workflow.log` next to the supplied `session.json`. `--workflow-log` exists only for migration and focused testing:

```powershell
python scripts/forge_benchmark.py record `
  --manifest benchmarks/manifests/cpp-pilot-v1.json `
  --case-id sysstat-nondeterministic `
  --condition baseline `
  --repetition 1 `
  --session-json C:\path\to\session.json `
  --workflow-log C:\path\to\workflow.log `
  --output benchmarks\results\cpp-pilot-v1.local.jsonl
```

`record` prints the same canonical normalized object to stdout and appends it once. Treat a validation, identity, secret-scan, missing-evidence, or duplicate-slot error as a stopped run; do not hand-edit JSONL around the failure.
