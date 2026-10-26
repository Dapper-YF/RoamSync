# RoamSync Handoff — Tourism Knowledge Phase A (isolated)

## Snapshot

Date: 2026-09-29。独立 Tourism Knowledge Contract / Retrieval Foundation 已实现；不接 Router/Companion/Planner。Branch codex/tourism-knowledge-phase-a；worktree E:/Study/RoamSync-tourism-knowledge；baseline snapshot 0fab288（来源为原 main 5572849 及当前未提交后端）。

## Current Freeze / Rehearsal Status

此任务不更改 Demo Freeze 状态或其他会话的 milestone。只新增独立模块、fixtures、tests、benchmark、报告；未修改现有文件。全局 PROJECT_STATE/LATEST_HANDOFF 不覆盖，避免并行冲突。

## Latest shadow-mode evidence

不涉及 Decision Ledger/shadow。VERIFIED：当前无 embedding/vector/RAG；PostgreSQL 测试镜像缺 vector，默认 simple FTS 不对连续中文分词。新增 BM25 + metadata filters + optional semantic/cosine + RRF。Source 与 document metadata 全保留；fixture 默认排除，半稳定知识有强制 expiry。

## Prior milestone baseline (before shadow split)

原 Agent milestone 保持；参见全局 handoff。本轮 guard 永远返回 knowledge-not-live-verified 标记；营业/天气/ETA 等需要 live verification，18点推荐解释需要 planning context。

## Prior verification

VERIFIED：Linux 模块 82 passed；完整 PostgreSQL regression 484 passed / 2 failed / 2 warnings（49.59s）；排除新增模块的 baseline 402 passed / 相同 2 failed / 2 warnings（49.76s）。无新增失败，不能宣称全绿。两处是旧 Assistant 改期确认、拒绝候选后 Router context 测试。MEASURED：28 fixture cases，每模式 27 条，Recall/category/filter/source/boundary 均 100%，仅人工 fixture。证据见工程报告、results.json、verification.json；Fake embedding 仅测接口，非生产能力。

## Prior blockers (historical)

仍无真实 corpus/persistent adapter/provider。中文 quality、source review 与 canonical place identity 待定。仅 cherry-pick 本轮实现提交，禁止 merge 全部 snapshot。

## Interview framing

这是独立检索工具基础，支持未来 Companion 的 stable contract；不是新增 Agent 或 Planner prompt。下一步 Router 合并后做 Companion Tool adapter，强制知识/事实/决策边界。
