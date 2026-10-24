# Probe environment limits

The first `probe_generation_scope.py` attempt exited before `main()` or any app
generation function ran. Its network deny guard blocked Windows asyncio's own
internal wakeup socketpair while creating the event loop:

```
socket._fallback_socketpair -> csock.connect((addr, port))
RuntimeError: Read-only synthetic probe disallows network/DB
RuntimeWarning: coroutine 'main' was never awaited
```

This is a harness failure, not a product rejection. The revised harness creates
the interpreter's local event loop before installing the application network
guard. All provider values remain explicit synthetic objects. No API/model/map
service or database request is permitted during the probe. Count this attempt
as invalid; it produced no product result to retry or replace.

Two initial exploratory inline probes established the pre-fix question and
partial-command behavior before per-file hashes were captured. Their tool
outputs were sent to A, which acknowledged reproduction. Do not represent those
exploratory outputs as a fixed-source baseline. Subsequent JSON probes bind
their actual active-source bytes before and after, and retain corrected controls
alongside remaining failures. A's worktree is uncommitted and may change between
captures; each capture is a separate version, never a population score.

One later shell call ran the completed boundary probe and then tried to read
`backend/app/conversation_candidate/commands.py` from B's old checkout instead of
A's active checkout. The probe wrote its JSON and reported unchanged source and
zero connection attempts; only the subsequent Get-Content failed with path not
found. The source read was corrected to A's absolute workdir. This is not a
product/test failure and is not included as a quality score.

The first post-commit source comparison deliberately checked all15 related files
against BASE89b81e8 and asserted full equality. It exited1 because preparation.py
had changed after the synthetic preparation probe. This is an actual source
identity difference, not an invalid runtime or newline-only match. Preserve the
all_match=false JSON. A separate bounded receipt verifies the four requested
authority files only; it does not relabel the15-file comparison as successful.
