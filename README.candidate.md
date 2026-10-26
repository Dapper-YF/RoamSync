# RoamSync

> 面向个人旅行规划的 Agent 原型：让用户提出约束，系统形成可复核的行程候选；只有经过规则校验并由用户确认后，候选才会进入正式旅行。

![RoamSync 规划工作台](docs/assets/roamsync-planner.png)

**求职展示素材：**完整 60–90 秒录屏尚待补拍；现有截图与代码测试的来源、日期和限制见 [`docs/portfolio/MATERIALS.md`](docs/portfolio/MATERIALS.md)。

## 三项核心设计

1. **先确定请求边界。** 确定性路由区分旅行咨询、规划请求和执行意图；含糊或缺少关键信息的规划请求先澄清。普通问答不会因为模型选择了某个工具就自动变成正式行程修改。
2. **用可恢复的工作流生成候选。** LangGraph 串联上下文读取、研究/地点与路线资料补充、候选生成和校验；PostgreSQL 持久化 PlanningRun 与图 Checkpoint。候选等待用户决定时不会直接改写正式日程。
3. **让正式写入经过一次明确审批。** 候选以 PlanRevision 单独保存。后端会验证地点、日期、时间、路线、预算、执行保护和旅行版本；接受时再校验一次并在事务中更新正式活动、路线和 Trip 版本。过期 Revision 被拒绝；重复接受不会重复应用。

## 当前实现

- React Web 行程工作台与 Kotlin/Jetpack Compose Android 客户端，连接 FastAPI 与 PostgreSQL。
- 旅行、日计划、活动、路线、预算、执行记录、PlanningRun、PlanRevision 和审计事件使用结构化数据持久化。
- `rules-v1` 规划意图解析保留日期/活动引用；无法唯一确定的实体会进入澄清，而不是猜一个正式对象。
- Agent Worker 执行可恢复图流程；候选路线可由地图服务补充；默认路线估算关闭，服务失败时明确报错。只有显式启用 ALLOW_MAP_ESTIMATES=true 才会提供并标明估算路线。
- Assistant、候选 Revision 与正式行程分别有权限边界。用户可以拒绝候选；拒绝不会把候选写成正式行程。
- 当前本地源码上于 2026-10-15 在隔离 PostgreSQL 中通过 5 项定向边界测试。测试命令、结果和适用限制见 [证据清单](docs/portfolio/MATERIALS.md#当前源码的定向验证)。

## 代码导航

| 关注点 | 文件 |
| --- | --- |
| 意图目标路由 | [`backend/app/travel_goal_router.py`](backend/app/travel_goal_router.py) |
| 确定性规划实体解析 | [`backend/app/planning_intent_service.py`](backend/app/planning_intent_service.py) |
| LangGraph 规划节点 | [`backend/app/planning_graph.py`](backend/app/planning_graph.py) |
| Worker 与 Checkpoint 启动 | [`backend/app/agent_worker.py`](backend/app/agent_worker.py)、[`backend/app/init_checkpoints.py`](backend/app/init_checkpoints.py) |
| 候选校验、版本栅栏与正式接受 | [`backend/app/plan_revision_service.py`](backend/app/plan_revision_service.py) |
| 规划对话界面 | [`web/src/components/AiPlannerPanel.tsx`](web/src/components/AiPlannerPanel.tsx) |
| 验证边界 | [`backend/tests/test_planning_runs.py`](backend/tests/test_planning_runs.py)、[`backend/tests/test_planning_graph.py`](backend/tests/test_planning_graph.py)、[`backend/tests/test_delay_impact.py`](backend/tests/test_delay_impact.py) |
| 架构图 | [`docs/portfolio/architecture.mmd`](docs/portfolio/architecture.mmd) |

## 本地启动

需要 Docker Desktop 和 Docker Compose；不需要 GPU。首次启动：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 为模型规划配置 PLANNER_API_KEY；按需配置地图密钥
docker compose up -d --build
docker compose ps
```

打开 <http://127.0.0.1:3000/trips>。模型规划需要 `PLANNER_API_KEY`；高德地点/路线需要 `AMAP_REST_KEY`；浏览器地图需要 `AMAP_WEB_KEY` 与 `AMAP_SECURITY_CODE`。Tavily 搜索为可选服务，Open-Meteo 天气不需 API Key 但需要网络。没有第三方密钥时仍可启动并体验手工行程管理；模型候选、实时路线或地图底图会受相应配置限制。变量和边界见 [.env.example](.env.example) 及 [启动与证据说明](docs/portfolio/MATERIALS.md#全新使用者启动检查)。

> 此启动步骤适用于全新本机安装。Compose 使用持久数据卷 roamsync_postgres_data；若本机已有 RoamSync 容器/数据卷，请先准备隔离演示环境，不要混用或重置现有数据。

## 明确的边界

- 尚未实现真实酒店/票务预订、支付或外部交易。
- 不应把 GPS 自动判断、持续自动感知或完整无人值守重规划说成当前能力。
- `docs/restructuring-v2/` 中的方案和路线图不是已经实现的功能。
- 当前候选稿按本地源码工作树撰写。GitHub `main` 是另一份公开快照；发布前需把源码、证据和截图重新绑定到准备发布的确切快照。
- 历史真实 Provider 完整演练在 2026-10-08 曾因候选生成失败而标记 NOT READY；早期隔离演练结果不能替代当前版本验收。见 [`ROAMSYNC_DEMO_ACCEPTANCE_20261007.md`](docs/agent/ROAMSYNC_DEMO_ACCEPTANCE_20261007.md)。

## 求职演示素材

- [架构图源文件](docs/portfolio/architecture.mmd)
- [素材、截图及验证结果](docs/portfolio/MATERIALS.md)
- [合成数据录屏脚本](docs/portfolio/RECORDING_SCRIPT.md)

录屏当前尚未生成。截图分别来自工作台、历史候选待确认和 Companion 流式回复场景；它们不是同一条 Planning 闭环。接受后刷新与合成失败保护截图尚待补录。素材的来源和公开性限制见 [证据清单](docs/portfolio/MATERIALS.md)。
