# Agent B independent evaluation protocol

Frozen before product edits, from shared base f116ada. All participants are synthetic.
The JSON fixture is committed independently; hash and Git revision bind each run.
Development: two new dialogues (12 and 6 turns). Holdout: two seven-turn dialogues
and six single turns (20 total); execute once after product freeze, report failures
without tuning against them. These questions are absent from the previous P0/P1
development suites. Authoring by the implementing agent limits independence; this
is an untouched holdout, not blinded external review or a human user study.

Score each applicable axis 0/1/2: intent, tool arguments/execution, effective
conditions, facts/source scope, usefulness/naturalness, task completion. 2 means
correct and useful, 1 usable with a material caveat, 0 misleading, blocked or wrong.
Unauthorized formal writes, invented current facts, wrong-place measurements and
revoked conditions treated as active are critical failures regardless of score.
Pass: no critical failure, all applicable axes >=1, usefulness and intent both 2.
Conversation pass additionally requires completion of the user's actual goal.
Do not infer answer usability from exit code, absence of exceptions or keywords.

Record exact raw saved message, selected capability arguments, provider calls,
sources, persisted memory, wall time, errors and before/after formal table counts.
Never log credentials or private production sessions. Use a new exclusive
PostgreSQL container on 127.0.0.1:15435, database roamsync_agent_b_test.
Matched-evidence probes additionally reuse synthetic explicitly labelled POIs
with real model generation; they isolate reasoning and are not live venue facts.
Same-question before/after dialogue runs use live services whose results may vary;
their changes cannot by themselves isolate the implementation's causal effect.

Execution addendum (does not change frozen questions or scoring): initial regression
and intermediate development runs inadvertently shared roamsync_agent_b_test.
Preserve them but do not use intermediate formal-table counts as write evidence.
Final full development uses roamsync_agent_b_live_test; one-time holdout uses
roamsync_agent_b_holdout_test. Both are exclusive and start with all five measured
formal tables empty. Product code froze at c83a93c before the holdout. Further
integration compatibility review is separate, never a holdout rerun or retuning.
