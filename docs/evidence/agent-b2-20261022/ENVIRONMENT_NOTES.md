# B2 execution caveats

- Initial `development-after-d5be594` attempt stopped before any dialogue because the new exclusively named test database did not exist. Created only that synthetic database, then reran the untouched full fixture; final JSON contains 16 actual turns.
- `address-evidence-red.xml` first failed on a test fixture missing city; `address-evidence-red-valid.xml` then reproduced the actual unwanted answer-generation bug with city present.
- `target-citation-recovery-final.xml` contains 107 passes/2 failures caused by an incomplete synthetic prepared marker (only draft). The subsequent test supplies the complete server marker contract; `target-citation-recovery-green.xml` passes 50 including both Graph recovery variants. No production guard was weakened.
- `authority-scoped-green.xml` and `b2-final-write-protection.xml` are invalid invocations naming a nonexistent test module. They are retained, never counted as checks. Correct module names appear in later runs.
- On 2026-10-23 all Docker containers were observed stopped unexpectedly. B test PostgreSQL State: exit255, OOMKilled=false, FinishedAt=2026-10-23T08:51:03.945719409Z. Write-protection and optional-compatibility runs waiting on that database were terminated; they produced no valid completion and are not counted. Only the B synthetic test container was restarted, then the shared write database suite was rerun serially. No official service was started or stopped by B.
- Live outputs before the fixed d5be594 run may have observed development worktree changes not fully represented by recorded HEAD. Treat them as intermediate diagnostics; final source-bound JSON uses committed d5be594. No raw output was overwritten to hide failure.
- All test credentials in these files are explicit synthetic credentials. No .env, secret value, private conversation, or hidden model reasoning is included.

- First source-fingerprint wrapper attempt failed before test execution because a relative Path was compared with an absolute cwd. No result artifact or quality claim was produced; corrected wrapper hashes repository-relative paths and records both before/after.

- A-runtime integration first attempt did not complete any test before another Docker stop (FinishedAt=2026-10-23T13:47:38.156009284Z, exit255/OOM=false). Verified its exact parent command, stopped only B wrapper/interpreter45192/50276, restarted synthetic15435 and obtained pg_isready accepting connections. A-runtime-integration-ready uses a new output path; the interrupted run is not a pass/failure measurement.
