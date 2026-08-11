# Forge C/C++ formal v4 lifecycle runtime amendment

## Status

This document records the Issue #105 implementation candidate. It does not
authorize a provider canary, physical-attempt ledger, model request, or batch.

## Frozen implementation

- Implementation baseline: `3ac49b92eedecf4932a829e75465dd7ddd16b97e`.
- One active physical attempt owns one monotonic clock and one append-only
  budget state.
- Provider requests and Compiler invocations claim their limits atomically
  before the external action starts.
- Submit and clean replay check the same work deadline before creating new
  work.
- The runner cancels an active asynchronous agent stream when the 1,680-second
  work deadline expires.
- Finalization, container cleanup, and orphan reconciliation remain mandatory
  after the work deadline and after the 1,800-second total wall clock.
- The final ledger records the bounded checkpoint state and any overrun without
  persisting prompts, credentials, provider bodies, host paths, or raw logs.

## Preserved research boundaries

The v4 limits remain 1,800 seconds total wall clock, 120 seconds cleanup
reserve, two Compiler invocations, and 48 model requests. The 30 exact-commit
C/C++ cases, 180-slot schedule, model profiles, Compose/DooD topology, Compile
Session, clean replay, artifact oracle, and analysis plan remain unchanged.

The seven formal-v3 observations remain a separate descriptive protocol
stratum. A v4 primary estimate may use only complete project blocks collected
under one later authorized v4 identity.

## Remaining authorization

Before any collection, the experiment owner must separately confirm complete
project blocks, slot count, recorded-token ceiling, evidence directory, and
network observation. The authorized child must retain the runtime component
hashes from this candidate and continue to forbid retry, fallback,
replacement, and backfill.
