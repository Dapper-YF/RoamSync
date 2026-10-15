# AI 结构化输出修复（2026-09-28）

## 问题与证据

VERIFIED：历史运行 `7b2465ec-2f54-4fc0-a6d3-a7149cfbe77a` 在候选解析阶段以
`planner_invalid_output` 结束，第 1 项地点不在允许候选集合；旧记录未保留错误 ID，
无法区分当时是编造还是复制错误。此前第二轮失败还包括 JSON 语法错误。
历史失败记录及 Stage 0 artifacts 保留，不以切换模型声称旧问题已经解决。

VERIFIED：此前 GLM 适配按“有 content”判断完成，未检查 `finish_reason`；截断的
JSON 可能被误分类为完整响应。此前一次格式修正仅提供错误说明，未提供上一版输出。

## 实现

- 当前模型保持 `glm-5.3-flash`，本次没有切换型号。
- GLM Planner 的结构化输入与 Schema 使用本次请求专用短引用，后端精确映射回 UUID。
  这是 wire-format 适配；正式数据、API、checkpoint schema 无需迁移。
- 未提供的引用、越权地点、错误日期继续被拒绝，不做名称匹配、猜测 ID 或绕过 Validator。
- 单次格式修正携带上次可见输出及错误反馈；仍最多一次，JSON 语法不靠字符串拼补。
- `length`、`content_filter` 和空 choices 归为 incomplete，不把非空内容当完成。
- GLM 使用 `stream=true` / `tool_stream=true`，累积可见 content、最终 usage 和
  finish_reason；未收到 `stop` 的流也归为 incomplete。thinking 不读取、不存储。
- 模型读取超时配置为 180 秒。真实非流式完整请求在 60 秒和 180 秒配置下均
  超时；单纯增加等待并不足以证明问题解决，因此补上流式接收。
- 原 Goals、Memory、Activity Semantics、路线校验、用户 Accept/Reject 边界保持。

## 验证

VERIFIED：针对性测试 34 项通过；隔离 Linux/PostgreSQL 最终全量回归
`368 passed, 2 warnings`（47.08s），包括未知/受保护引用拒绝、一次修正边界、短引用
往返、Memory/Schema/复合引用一致性及截断响应判断。

MEASURED：容器内 GLM JSON smoke 7.26 秒完成，JSON 可解析，281 tokens。
流式 smoke 首块 2.21 秒、完整返回 6.72 秒，207 chunks，291 tokens，finish_reason=stop。

## 真实运行与最终部署

四次均使用同一原始需求，不重置正式行程、不自动 Accept。模型始终为
`glm-5.3-flash`，没有换成 FlashX 或旗舰型号。

| Run | 配置 | 实际结果 |
| --- | --- | --- |
| `472bb000-22c2-4605-81d2-5f766b3957f8` | 非流式 / max / 60 秒 | planner_timeout |
| `1844c2c6-11d2-4e43-978e-82e571ab7b8a` | 非流式 / max / 180 秒 | planner_timeout |
| `1c856d37-da54-4c3c-b5a5-733c994627f3` | 流式 / max / 180 秒 | 旧异常映射记录为 planner_invalid_output；未保存底层类型，无法断言是 JSON 错误还是传输异常 |
| `e2a4137e-cc22-4861-abf2-8143e8ec370a` | 流式 / high / 180 秒 | awaiting_confirmation，真实 pending Revision |

最终生产 api 与 agent-worker 已部署流式适配、Planner reasoning_effort=high、
timeout=180 秒。全上下文 max 未完成，high 成功；单次成功不足以证明稳定性 3/3。
新增异常分类：HTTP 超时→planner_timeout，传输异常→planner_unavailable，
其他 Provider API 异常（含 SSE error）→planner_provider_error，避免误报坏 JSON。
日志只记录异常类型及 cause 类型，不保存原始 payload、密钥或 hidden reasoning。

成功 Revision：`a5e96be3-572d-4c75-b1ed-08419043c5bf`，Validator valid。
5 项活动全部保留，最终结束 17:45，真实路线步行 174→61 分钟；硬目标
18:00 前结束与存储偏好的 80 分钟步行上限满足。轻松节奏等软目标仅记录
observations / not_evaluable，不伪装为数学 PASS。Provider 返回累计 11,190 tokens。
路线校验按查询到的时长调整两项活动时间；正式行程未应用。

上次 too_rushed 反馈已检索并进入 Planner，来源仍是同一行程的真实拒绝。
Decision Ledger 仍 invalid（evidence/provenance 缺失及 route evidence mismatch），
现有 shadow 模式允许合法候选生成，但前端隐藏未经核验理由。

真实浏览器已打开 Demo Trip → 旅程总管，核对到目标卡、17:45、61 分钟、
174→61、保留 5/5、“调整原因暂未通过核验”及“暂不采用 / 确认并应用”。
没有点击确认或拒绝。本次请求经生产 planning API 提交，前端做持久化结果展示
验证，不声称本次由聊天输入框完成提交。

独立证据：`backend/evals/results/travel_decision_demo/glm_reference_fix_20260928.json`。
既有 Stage 0 与 20260927 artifacts 未覆盖。

## 范围与限制

修复针对结构化候选引用、格式修正上下文和响应完整性；没有证据证明所有 Agent
语义质量、Provider 稳定性或 Decision Ledger 问题已解决。Stage 0 与 Stage 2.2
现有 Exit Gate 不因这次修复自动关闭。
