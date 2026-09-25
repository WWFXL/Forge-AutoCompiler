# Repository Agent Instructions

Read and follow `CLAUDE.md` before changing this repository. Files below
`backend/` and `frontend/` may have additional local instructions.

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
