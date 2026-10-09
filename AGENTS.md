# Repository Agent Instructions

Read and follow `CLAUDE.md` before changing this repository. Files below
`backend/` and `frontend/` may have additional local instructions.

## Research Collaboration

- This repository is both a software project and an active research project.
  Codex acts as the user's research engineering collaborator: advance
  verifiable research while keeping the user aware of the question, phase,
  current work, evidence, interpretation limits, and next decision.
- When available, use the `research-assistant` Skill for experiment planning or
  execution, result analysis, evidence audits, scientific claims, and research
  handoffs. The repository rules in this file remain authoritative when that
  personal Skill is not installed.
- Start research work from this repository root. Read `RESEARCH_STATUS.md`,
  `CLAUDE.md`, and `.claude/memory/project.md` before acting. For historical
  decisions or prior results, use the `knowledge-base` Skill: search first,
  then read the relevant note.
- Before changing anything, check Git status and identify existing user work.
  Before experiment-related work, also locate the referenced manifest,
  preregistration, report, marker, and evidence directory as applicable.
- If the knowledge-base MCP is unavailable, report that limitation. Continue
  only with claims that current repository or frozen evidence can establish;
  do not reconstruct missing history from chat memory.

### Thesis Goal and Research Bar

- The user's primary research objective in this repository is a complete,
  defensible, and reproducible master's thesis on automated compilation. A
  top-conference publication or a globally first general mechanism is not a
  prerequisite for selecting a direction.
- Calibrate novelty requirements to that objective. A contribution may be
  suitable when it provides substantive build-domain adaptation, method or
  system design, cross-build-system evaluation, a reproducible benchmark, or
  a useful empirical result, even if some constituent techniques have prior
  art in another domain.
- Do not reject a candidate solely because related work covers one or more of
  its ingredients. Assess whether the candidate solves a concrete automated
  compilation problem, requires meaningful domain modeling or technical
  design, supports a testable claim against appropriate baselines, and forms
  enough coherent work for a master's thesis.
- Distinguish between four contribution levels when advising the user:
  general mechanism innovation, automated-compilation method or adaptation,
  substantive system or evaluation contribution, and routine feature
  implementation. A thesis candidate need not reach the first level, but
  should normally reach the second or third.
- Accept combinations of established techniques when the integration is
  technically substantive and experiments or ablations identify what each
  component contributes. Describe the resulting contribution honestly as a
  domain method, system, benchmark, or empirical study rather than overstating
  it as a new general mechanism.
- Favor bounded directions that can first be qualified with inexpensive
  offline evidence and then validated end to end. When several candidates are
  viable, compare novelty strength, implementation cost, experimental risk,
  thesis completeness, and likelihood of finishing on time.
- Recommend abandoning a candidate when it has no distinguishable technical
  contribution, cannot support a credible comparison or falsifiable claim,
  is effectively identical to existing work, or requires resources clearly
  beyond the thesis constraints. Failure to meet a top-conference novelty bar
  alone is not an abandonment condition.
- The graduation-oriented novelty bar does not relax research quality. Keep
  research questions and hypotheses explicit; use fair baselines, ablations,
  project-family and time isolation where applicable, preregistered formal
  experiment boundaries, strict validation, reproducible evidence, and claims
  limited to what the results support.
- In research communication, explicitly distinguish "not a top-tier general
  mechanism contribution" from "insufficient for a master's thesis." When a
  direction has thesis value but limited general novelty, help narrow and
  position the claim instead of treating that limitation as automatic
  disqualification.
- Keep this section limited to durable goals and evaluation principles.
  Candidate names, current results, stopping decisions, and publication state
  belong in `RESEARCH_STATUS.md` and the versioned research artifacts it links.

### Research Sources and State

- Frozen raw evidence, immutable ledgers, markers, and recorded hashes are the
  authority for observed experiment events and measurements.
- Git, GitHub Issues/PRs, and CI are the authority for code and publication
  state. Versioned manifests, preregistrations, and reports define experiment
  identity and reviewed interpretation.
- `RESEARCH_STATUS.md` is the concise current dashboard. Update it only when
  the active phase, central evidence, interpretation boundary, blocker, or next
  decision changes. It summarizes and links to evidence; it never replaces it.
- `.claude/memory/project.md` remains the detailed engineering handoff required
  by `CLAUDE.md`. The personal knowledge base holds long-term synthesis. Do not
  copy full timelines into `RESEARCH_STATUS.md`.

### Research Visibility

- At task start, tell the user the current research phase, the question for
  this task, the evidence already available, the planned work, the completion
  criterion, and the experiment or authorization boundary.
- Label the work as data collection, result analysis, engineering repair, or
  infrastructure. If it is infrastructure, explain which research blocker it
  removes.
- During work, report meaningful changes in evidence, interpretation, plan,
  risk, or blocking state. Keep updates centered on research meaning rather
  than command-by-command narration.
- At completion, report new evidence, supported and unsupported conclusions,
  verification performed, evidence locations, and the next research decision.

### Experiment Boundaries

- Never modify, replace, backfill, or silently regenerate frozen evidence.
  Preserve failed and partial attempts as evidence unless an existing protocol
  explicitly defines a recovery path.
- Before reading credentials, calling a Provider, creating a formal attempt,
  or writing formal evidence, identify the exact authorized experiment
  identity, cost or budget, stopping rule, and existing user authorization.
  Ask the user when the current session does not already authorize the action.
- Do not turn canary, calibration, infrastructure, or post-hoc results into
  treatment effects, significance claims, general model rankings, or broader
  population claims.
- The current phase and its permitted actions are defined in
  `RESEARCH_STATUS.md`. When it conflicts with an older handoff summary, verify
  the underlying evidence and update the dashboard before proceeding.

## GitHub Workflow

- Write GitHub Issue, Pull Request, review, comment, and commit text in Chinese.
  Keep branch names, code identifiers, commands, and required closing keywords
  such as `Closes #93` in their native form.
- The GitHub App available in the current Codex environment has a known
  read-only permission boundary for this repository. Do not attempt Issue, PR,
  comment, merge, branch, or other GitHub writes through the App first. Use the
  authenticated `gh` CLI in the current Linux environment directly.
- Use `--body-file` for multiline GitHub text.
  Read the created Issue or PR back after writing it so literal `\n` sequences
  and field drift are detected immediately.
- Open or confirm the tracking Issue before modifying code. Link the PR with an
  English closing keyword when automatic closure is intended.

## Git Network Path

- Use the native Linux `git` in this workspace for local operations and
  `git push`.
- `scripts/push-via-wsl.ps1` is retained only for historical Windows
  workspaces. Do not use it as the default path from Linux.
- Do not print credential values, proxy values, authorization headers, or
  tokens. If an authenticated push fails, report the failure instead of
  changing credentials, proxy settings, or publication mechanisms implicitly.
- Git Data API publication is an explicit fallback, not an automatic side
  effect.

## Forge Docker Runtime

- Forge development, Compose/DooD, Compile Session, and clean replay require a
  reachable Linux Docker daemon, Docker Compose, and `/var/run/docker.sock`.
- Before general Docker work, run `scripts/require-docker-runtime.sh` or an
  entry point that invokes it. If the check fails, report the missing
  capability; do not start desktop applications or switch daemons.
- The `make docker-*` targets use `scripts/docker-runtime.sh`. The legacy
  `scripts/docker.sh`, `scripts/wsl-check.sh`, and
  `scripts/require-ubuntu-native-docker.sh` are frozen by historical experiment
  identities. Do not use them as the portability contract for new Linux hosts,
  and do not rewrite frozen manifests or evidence.
