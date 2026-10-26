# RoamSync 求职素材与证据清单

复核日期：2026-10-15（Asia/Shanghai）  
用途：给求职展示与后续 README 排版对话提供可追溯材料。本文不是发布批准。

## 源码版本与变更范围

- 唯一正式源码目录：`E:\Study\RoamSync`。
- 本地分支：`codex/roamsync-demo-release-20261007`；HEAD：`0b5010fe5a7b06dcec1ab7b159b5b337244247ae`。
- 本任务开始前工作树已不干净：38 个已跟踪文件有改动、113 个未跟踪路径。既有改动覆盖 Web、Android、后端、测试、项目文档及根目录文件；不应把它们描述成此次素材工作或 GitHub `main` 的内容。本任务没有修改业务源码、根目录 `README.md`、配置或数据卷。
- GitHub `main` 是用户单独整理的公开快照，与上述本地分支/工作树不是同一份发布物。`README.candidate.md` 仅是候选，不要把本地旧分支直接推到 `main`。
- 下表的“当前源码范围”均指上述 HEAD 加本任务开始前的既有未提交改动；历史截图单独标注原始捕获日期，不能当成本版本 UI 验收。

## 素材索引

| 项目 | 实际路径 | 当前源码版本 / 未提交改动范围 | 验证日期与方式 | 可公开性 / 限制 |
| --- | --- | --- | --- | --- |
| 中文 README 候选 | README.candidate.md | 以 HEAD 0b5010f 加既有 38 tracked / 113 untracked 的本地源码为事实；此文件为新候选稿 | 2026-10-15，静态逐项对照源码、测试与项目状态 | 内部候选；发布前须将能力和证据重新绑定到 GitHub main |
| 架构图源文件 | `docs/portfolio/architecture.mmd` | 同上；图仅覆盖当前正式 Planning 主链，不包括 V2 方案 | 2026-10-15，静态检查函数调用、API 与测试边界 | 可随 README 一起排版；属于当前本地源码设计说明 |
| 录屏步骤 | `docs/portfolio/RECORDING_SCRIPT.md` | 同上；没有调用线上模型或写入正式旅行 | 2026-10-15，静态检查输入顺序与现有澄清/审批测试 | 可公开；这是脚本，不是录屏结果 |
| 规划工作台截图 | `docs/portfolio/screenshots/planner-workspace-cover.png`；原始文件 `docs/assets/roamsync-planner.png` | 项目已有浅色封面；截图原始文件时间 2026-09-02 | 2026-10-15，静态检查图片与 README 引用；未重录 | 用户说明该封面已在 GitHub 使用，可沿用；画面是旧旅行工作台 |
| 候选确认前截图 | `docs/portfolio/screenshots/candidate-before-confirmation.png`；原始文件 `docs/evidence/assistant-ui-proposal.png` | 原始捕获 2026-09-09；比当前源码早，不绑定 HEAD | 2026-10-15，静态图像复核，原图 1440×1000 | 显示候选卡片/确认按钮；来源数据的合成属性没有独立清单证明，公开前需确认或重拍 |
| Companion 流式回复截图 | docs/portfolio/screenshots/assistant-streaming-20261015.png；原始文件 docs/evidence/streaming-release-20261015/streaming.png | 原始捕获 2026-10-15；Web 为当前已部署流式界面，聊天响应由隔离合成 HTTP 服务提供 | 2026-10-15，静态图像复核，原图 1366×900 | 无旅行行程或个人账号信息，可作为 Companion 界面截图；不是 Planning 闭环证据 |
| 完整 60–90 秒 MP4 | 尚无文件 | 当前源码范围如上 | 本轮未录制：现有 `roamsync` 服务连接正式持久数据；用户要求不部署且不得碰现有数据卷。测试 Compose 只有 API 测试任务，没有可供完整 UI 演示的隔离 Web/Worker 运行环境 | 不存在；不得用截图拼接或伪造补位 |
| 10–15 秒 GIF | 尚无文件 | 依赖真实 MP4 才能截取 | 本轮未生成 | 不存在；待完整录屏后从真实片段导出 |

截图都按原字节复制，未裁切、覆盖文字或伪造状态。文件名是便于排版的别名；原图和副本应按上表配对阅读。3 张 PNG 来自不同日期/流程，没有“确认后刷新”或合成失败保护截图。原有 docs/evidence/live-planning-progress.png 与 docs/evidence/live-route-constraint.png 含有具体旅行请求/日期，合成属性未证实，因此没有复制到作品集目录或标记为可公开素材。

## 当前源码的定向验证

验证环境：`compose.test.yaml`，Compose 项目名 `roamsync-portfolio-20261015`；其 PostgreSQL 使用容器内 `tmpfs`，不挂载或复用 `roamsync_postgres_data`。仅运行下面列出的 5 个测试，没有跑全量回归。命令结束后执行了 `docker compose ... down`（未使用 `-v`）；临时测试容器和网络已移除。

初始化迁移命令：

```powershell
docker compose -p roamsync-portfolio-20261015 -f compose.test.yaml run --build --rm api-test uv run --no-sync alembic upgrade head
```

五项测试命令及实际结果：

| 证据项 | 源码/测试路径 | 测试命令 | 实测结果 | 适用限制 |
| --- | --- | --- | --- | --- |
| 非法候选无法应用 | `backend/app/plan_revision_service.py`；`backend/tests/test_planning_runs.py` | `pytest -q tests/test_planning_runs.py::test_accept_revision_rejects_insufficient_travel_time` | 通过；接受接口返回 422，包含 `route_travel_time_conflict` | 验证后端已有候选的路线时间拒绝；不是模型生成质量或 UI 演示 |
| Checkpoint 恢复 | `backend/app/planning_graph.py`；`backend/tests/test_planning_graph.py` | `pytest -q tests/test_planning_graph.py::test_postgres_checkpoint_recovers_through_decision_api` | 通过；PostgreSQL checkpoint 暂停在审批点，再由新 Saver 连接通过决策 API 恢复并接受 | 证明跨 Saver 连接恢复，不等于完整 API/Worker 进程重启演练 |
| 时间余量计算 | `backend/app/navigation/delay_impact.py`；`backend/tests/test_delay_impact.py` | `pytest -q tests/test_delay_impact.py::test_delay_uses_schedule_slack_before_creating_a_macro_replan_signal` | 通过；断言两个下游点的 slack 均为 330 分钟，产生延迟观测但不触发宏观重规划 | 这是固定输入的确定性计算；不证明实时 GPS、实际地图路况或现场延误 |
| 过期候选拒绝 | `backend/app/plan_revision_service.py`；`backend/tests/test_planning_runs.py` | `pytest -q tests/test_planning_runs.py::test_accept_revision_rejects_a_stale_formal_trip` | 通过；正式 Trip 版本先变化后，旧 Revision 接受返回 409 | 验证单个后端并发版本栅栏；未覆盖多进程压力测试 |
| 重复采用幂等 | `backend/app/plan_revision_service.py`；`backend/tests/test_planning_runs.py` | `pytest -q tests/test_planning_runs.py::test_accept_revision_applies_once_and_invalidates_stale_routes` | 通过；同一 Revision 接受两次均成功，Trip 版本只增加一次 | 使用隔离测试库与合成种子；不是正式数据库或真实地图服务验收 |

完整定向调用（输出 `..... [100%]`，退出码 0）：

```powershell
docker compose -p roamsync-portfolio-20261015 -f compose.test.yaml run --rm api-test uv run --no-sync pytest -q tests/test_planning_runs.py::test_accept_revision_rejects_insufficient_travel_time tests/test_planning_graph.py::test_postgres_checkpoint_recovers_through_decision_api tests/test_delay_impact.py::test_delay_uses_schedule_slack_before_creating_a_macro_replan_signal tests/test_planning_runs.py::test_accept_revision_rejects_a_stale_formal_trip tests/test_planning_runs.py::test_accept_revision_applies_once_and_invalidates_stale_routes
```

结果：5 项通过，0 项失败（2026-10-15）。没有调用真实 Planner/地图服务；没有全量测试结果或成功率可供声称。

## 全新使用者启动检查

静态检查文件：`.env.example`、`web/.env.example`、`compose.yaml`、`backend/Dockerfile`、`README.md`。根目录 Compose 由 PostgreSQL、API、Agent Worker、Web 和 checkpoint 初始化任务组成；Docker Desktop / Docker Compose 即可本地运行，不要求 GPU。前端源码开发另需 Node.js 与 pnpm；Android 开发另需 Android Studio/JDK 17。

首次本地体验的步骤：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 填写需要使用的服务密钥；不要提交 .env
docker compose up -d --build
docker compose ps
```

Web：`http://127.0.0.1:3000/trips`；API：`http://127.0.0.1:8000/docs`。首次运行会由镜像入口执行数据库迁移，checkpoint 初始化任务由 Compose 管理。

| 配置 | 是否必须 | 不配置时的实际范围 |
| --- | --- | --- |
| `POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD` | 本机 Compose 数据库需要非空值；示例含本地默认值 | 仅本地开发默认值；共享/公开部署前必须换强口令 |
| `PLANNER_API_KEY` | 真实模型规划与模型助手需要 | 页面、手工行程管理和确定性接口仍可用；不会有可依赖的模型候选 |
| `AMAP_REST_KEY` | 实时高德 POI/路线请求需要 | 已保存资料可查看/编辑；新地点与实时路线不能保证可用。`ALLOW_MAP_ESTIMATES=false` 时不会静默用估算路线替代 |
| `AMAP_WEB_KEY`、`AMAP_SECURITY_CODE`；Web 本地开发对应 `VITE_AMAP_WEB_KEY`、`VITE_AMAP_SECURITY_CODE` | 高德浏览器地图需要 | 手工列表/时间线仍可体验，地图底图会显示配置缺失状态 |
| `ROAMSYNC_TAVILY_API_KEY` | 目的地网页检索可选 | 不影响本地行程编辑；检索需要服务密钥及网络 |
| Open-Meteo | 不需 API Key | 天气请求仍需外网；网络或服务失败会返回不可用状态 |

> 全新使用者不要把当前开发目录已有 Docker 项目/数据卷当成空白演示库。`app.seed_demo --reset` 会写入其目标数据库，只能在明确隔离的全新数据库上使用。本轮没有运行该命令。

## 历史验收与演示缺口

`docs/agent/ROAMSYNC_DEMO_ACCEPTANCE_20261007.md` 记录的 2026-10-08 干净源码真实 Provider 闭环状态为 **NOT READY**：当次候选生成失败，因此未完成该轮接受、拒绝、执行与恢复链。文档另有更早 dirty-tree 隔离演练成功记录；那是历史证据，不是当前 HEAD 的完整演示证明。`docs/agent/STREAMING_RELEASE_20261015.md` 的浏览器检查针对合成 SSE 服务，不是旅行规划闭环。

当前缺少：绑定当前源码的完整录屏、接受前后及刷新截图、独立合成数据来源证明、可公开的演示账号/环境。延误影响与局部调整没有在本轮另行录屏。照做脚本见 `RECORDING_SCRIPT.md`。
