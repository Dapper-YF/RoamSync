# RoamSync project instructions

## Web ChatGPT and local Codex handoff

This repository uses a compact handoff protocol for decisions made in Web
ChatGPT and implementation performed in local Codex.

- Read `docs/handoff/PROJECT_STATE.md` and `docs/handoff/LATEST_HANDOFF.md`
  before planning non-trivial work.
- Treat repository code, tests, migrations, actual runtime output, and the
  current worktree as facts. Treat plans and handoffs as context, not proof.
- After each important completed work round, overwrite
  `docs/handoff/LATEST_HANDOFF.md` using its fixed headings. Keep it concise,
  decision-oriented, and under 3,000 Chinese characters where practical.
- Update `docs/handoff/PROJECT_STATE.md` only for meaningful changes to
  architecture, primary modules, technology choices, core models, or major
  capabilities.
- Record durable design decisions, experiments, and regressions in their own
  ADR, experiment, or bad-case artifacts. Do not turn handoff files into a
  chronological log.
- Never claim metrics, provider behavior, or implementation status without
  directly recorded evidence. Use VERIFIED, MEASURED, INFERRED, and HYPOTHESIS.
- Do not copy secrets, raw private trip data, full chat histories, source code,
  or full test logs into a handoff.

## Existing contract

Read `docs/AGENT_ARCHITECTURE.md` before changing planning schemas, graph
states/nodes, tool permissions, failure codes, or candidate acceptance rules.
It is the Agent v1 contract and defines its required change-control evidence.
