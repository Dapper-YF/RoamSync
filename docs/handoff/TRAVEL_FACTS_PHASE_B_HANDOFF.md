# RoamSync Handoff — Travel Facts Phase B (isolated)

## Snapshot

2026-09-29。VERIFIED：独立 `backend/app/travel_facts` 已完成 contracts、deterministic resolution、Provider boundary 和 canonical execution read-through。未接 Companion/Planning。branch `codex/travel-facts-phase-b`；worktree `E:/Study/RoamSync-travel-facts`。

合并只 cherry-pick 本分支最终 implementation HEAD（提交号以交付消息/`git log -1` 为准）；**不要合并整分支，不要带入 parent snapshot `1679be4d874b300c3ad1b484032eea1cbbfe5ac0`**。snapshot 用于捕获主工作区原有未提交后端基线，不是 Phase B 开发提交。最终提交只新增本模块、tests/evals、专门报告/handoff。

## Current Freeze / Rehearsal Status

本轮不改变全局 Freeze、演练 Gate、Companion 开发状态或 Deployment。没有启动/重置真实 Demo。

VERIFIED：typed Fact/Evidence/Requirement/ResolvedFact，逐类型显式 freshness 和 authority，fresh/stale/future/expired/gap/conflict、全部来源/排除记录，bounded in-memory 外部缓存。无生产 TTL 默认；fixture 数值不是 SLA。Tavily 只为 search evidence candidate；外部文本没有工具权限。

VERIFIED：AMap POI identity/location/native category、Route distance/duration；Open-Meteo hourly forecast；Execution actual timestamps/status、Navigation position/ETA/remaining distance。AMap duration 和 navigation ETA 为 prediction。current weather、external route ETA、官方 notice collector、TravelEvent 聚合未实现。官方临时闭馆用合成 fixtures 验证 policy。

VERIFIED：canonical SQL read-through，自建 REPEATABLE READ/READ ONLY session，版本/所属关系 guards；默认排除 simulation，opt-in simulation 仍不能作为 live reality；不缓存/双写执行事实，不刷新旧导航 observation 时间。真实 PostgreSQL 测试比较所有 public 表读取前后完整内容并捕获 SELECT/SET-only SQL。

## Latest shadow-mode evidence

本轮没有 live/shadow Provider 调用或 Agent 回答质量测量。MEASURED 28/28 deterministic fact benchmark；freshness/provenance/resolution/conflict 各 28/28，unavailable honesty 16/16。合成 fixture，非盲测。

## Prior milestone baseline (before shadow split)

MEASURED 本轮私有 snapshot 修改前完整后端：405 passed、0 failed、2 warnings，46.07s；不从其他任务报告抄计数。独立 Compose project `roamsync-travel-facts-test`，frozen uv.lock + PostgreSQL 17。

## Prior verification

MEASURED 最终完整后端：492 passed、0 failed、2 existing Starlette deprecation warnings，51.42s；新增 87 passed，本轮新增失败 0、原基线失败 0。Python 3.11.16 / pytest 8.4.2 / Pydantic 2.13.5。证据：`backend/evals/travel_facts/{baseline,verification,results}.json`，包含 cases、分子分母、源码 hashes。

未跑 Web/Android，因为无这些目录改动。本机 Python 的真实 gateway 导入曾因缺依赖失败；最终 frozen Docker 保留并通过该测试，没有弱化断言。

## Prior blockers (historical)

原 Decision Ledger、Demo 演练和其他任务 blockers 保持；本轮不负责关闭。已知风险：AMap private seam、获取时间不等于实测/模型发布时间、minute precision、有界进程内 history、blocking Provider thread 超时后可能继续至其网络 timeout。payload hash 无法恢复原始 JSON。Caller 业务授权仍需由外层负责。

## Interview framing

可展示“需求 → typed fact + provenance + temporal/policy resolution”，缺证据不猜、冲突不抹掉、执行事实只有 canonical owner。下一步在 Companion 合并树重跑后端；先给一个只读 InformationNeed 配置 product freshness 与 gap/conflict UX，再逐步接入。全局 PROJECT_STATE/LATEST_HANDOFF 留给主工作区整合维护，遵守本轮显式并行隔离要求。没有 Obsidian 写入。
