# RoamSync Web 真实性审计

> 本文是 2026-09-06 历史审计。2026-09-08 改动与当前验证边界见 [重构记录](WEB_REFACTOR_20260908.md)。

日期：2026-09-06  
结论：**暂停新增 Agent 功能，先返工 Web 数据真实性和产品边界。**

## 审计范围

检查了 Web 路由、页面组件、Repository 实现、测试、Docker Compose 配置，
并对当前正式 API（`http://127.0.0.1:8000`）进行了只读请求。

## 结论摘要

| 模块 | 当前判断 | 证据 | 严重程度 |
|---|---|---|---|
| 旅行列表、创建、编辑、删除、归档 | 有真实 API 与 PostgreSQL 写入路径 | `web/src/data/apiTripPlanningRepository.ts`；`backend/app/main.py`；正式 API 返回 4 个旅行 | 中 |
| 日计划、活动、预算、路线 | 有真实读写路径；路线依赖高德 | 同一 Repository 的 CRUD/route 方法；正式 API 返回 2 个日计划 | 中 |
| AI 规划 | 有真实任务/Worker 链路，但缺少 Web 端真实成功、失败、确认验收证据 | `AiPlannerPanel.tsx`；当前正式库 planning-runs 为空；E2E 未覆盖 AI | 高 |
| 旅中模式 | 是可选执行视图，不应成为开始规划的前置条件 | `TravelModePanel.tsx`；执行 API 独立于 planning API | 中 |
| 旅行总览、酒店、城际交通、天气 | 明确是静态产品预览，不是业务功能 | `TripBriefingDrawer.tsx` 使用 `tripPreviewData.ts`；按钮全部 disabled | 高 |
| 预约清单 | 复选框没有 Repository/API 写入 | `TripBriefingDrawer.tsx` 使用 `defaultChecked` | 高 |
| Mock Repository | 存在完整演示数据路径，可能让功能看起来可用 | `VITE_USE_MOCK_REPOSITORY` 分支；`mockTripPlanningRepository.ts` | 高 |

## 关键问题

### 1. “旅中模式”不应是规划前置条件

当前它只是 `GET /trips/{trip_id}/execution`、`/execution/start` 和 action API
组成的执行视图。用户可以直接创建和规划旅行，不需要先开启它。产品文案应改为
“可选的旅中记录”，并把动态重规划入口放在普通 AI 助手和执行事件中，而不是暗示
用户必须手动开启模式才能规划。

### 2. 旅行总览是静态预览

`web/src/components/TripBriefingDrawer.tsx` 直接调用
`web/src/data/tripPreviewData.ts`。杭州演示固定返回酒店、车次、天气、准备度和金额；
“接入供应商后可预订”“待接入票务”按钮是 disabled。清单 checkbox 没有保存回调，
刷新页面会丢失状态。这部分应明确标成“演示预览”，或暂时从正式产品入口移除。

### 3. AI 助手尚不能宣称已可用

`AiPlannerPanel.tsx` 确实调用真实 `createPlanningRun`、轮询状态、读取 revision，
但当前 Web E2E 没有覆盖创建 AI 任务、Worker 完成、候选方案展示、确认应用和失败恢复。
组件测试使用 `LocalTripPlanningRepository`，不能证明真实 API 链路。审计时正式数据库
的 planning-runs 为空，不能形成一次当前运行成功证据。因此应把 AI 标为“实验功能”，
直到完成真实浏览器验收。

### 4. Mock/正式数据边界必须显式化

此前 `App.tsx` 可根据 `VITE_USE_MOCK_REPOSITORY` 在 `LocalTripPlanningRepository` 和
`ApiTripPlanningRepository` 间切换。该生产分流已移除：正式应用现在固定使用
`ApiTripPlanningRepository`，Mock Repository 仅由测试通过依赖注入使用。Mock 会用
`localStorage` 保存活动和规划状态，不能作为生产数据源。

## 正式数据库与测试数据库

`compose.yaml` 中的 `roamsync-postgres` 是产品正式开发数据库，数据位于命名卷
`roamsync_postgres_data`。`compose.test.yaml` 中的 `postgres-test` 使用 tmpfs，
数据库名为 `roamsync_test`，只用于隔离自动化测试和迁移验证；它不会承载产品数据，
也不应被当作“真实数据服务”。

测试数据库的意义是避免测试重置、删除和失败事务污染正式开发数据，而不是替代正式库。
正式演示数据应通过正式库的幂等 seed 命令写入；测试数据则继续使用 test compose。

## 返工优先级

1. P0：移除或改名静态总览入口，禁止把固定酒店/车次/天气作为真实数据展示。
2. P0：为 AI 助手增加真实 API + Worker + 确认应用的 Playwright 验收；失败时显示机器错误码和可恢复状态。
3. P1：生产构建固定使用 API Repository，Mock 只能由显式测试开关启用，并在启动日志中打印数据源。
4. P1：把预约清单建成真实表和 CRUD API，或者暂时删除可交互 checkbox。
5. P1：将旅中模式改为可选的执行记录视图，不把它描述成规划启动步骤。
6. P2：正式 API 增加认证/授权后，再开放真实多用户数据；当前版本不能把 demo seed 当成用户隔离方案。

## 本次运行证据

- `docker compose -f compose.test.yaml ... pytest`：130 项后端测试通过。
- `pnpm exec vitest run`：27 项前端测试通过。
- `pnpm e2e`：8 项浏览器测试通过，但仅覆盖执行记录、活动编辑、地点搜索和动态重规划任务创建，未覆盖 AI Worker 完成与确认应用。
- 正式 API 健康检查：`GET /health/live` 返回 `{"status":"ok"}`。
- 正式 API 只读检查：旅行列表 4 条、演示旅行 2 个日计划、规划上下文 2 个日计划。

以上测试通过不等于 Web 全部功能真实可用；静态预览和未覆盖的 AI 链路必须按本报告返工。

## 返工进度（2026-09-06）

- 已移除 Web 端“旅行总览与预订预览”静态入口及其固定数据文件。
- 已移除 Web 端“旅中模式”入口和页面组件；执行状态 API 暂保留，待确认是否从后端一并下线。
- 规划工作台新增明确的“怎么开始”引导，并提供直接打开 AI 规划助手的入口。
- 正式 App 已固定使用 API Repository，不能通过环境变量切换到 Mock 数据。
- 真实 AI API + Worker + 确认应用链路仍未完成浏览器端验收，暂不标记为可用。
