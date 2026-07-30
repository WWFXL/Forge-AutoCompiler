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
  authenticated Windows `gh` CLI directly.
- Use a PowerShell here-string or `--body-file` for multiline GitHub text.
  Read the created Issue or PR back after writing it so literal `\n` sequences
  and field drift are detected immediately.
- Open or confirm the tracking Issue before modifying code. Link the PR with an
  English closing keyword when automatic closure is intended.

## Git Network Path

- Local, non-network Git commands may use Windows Git. For pushes from this
  Windows workspace, use:

  ```powershell
  pwsh -NoProfile -File scripts/push-via-wsl.ps1
  ```

- The helper deliberately uses WSL Git, the WSL network/proxy environment, and
  the authenticated Windows `gh auth git-credential` helper. It must not print
  credential values, proxy values, authorization headers, or tokens.
- Do not first retry Windows `git push` when `github.com:443` is known to be
  unhealthy. The Windows path can time out while `api.github.com` and WSL Git
  remain healthy.
- If the WSL helper exhausts its bounded retries, report the failure. Git Data
  API publication is an explicit fallback, not an automatic side effect.
