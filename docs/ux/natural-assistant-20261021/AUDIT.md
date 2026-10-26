# 自然助手与旅行安排交互审计

日期：2026-10-21（Asia/Shanghai）。审计对象：正式目录 `E:/Study/RoamSync` 的当前工作区，包括未提交代码；不以历史副本或 HEAD 代替当前文件。源码快照见 `evidence/source-snapshot.json`。

## 结论

现有系统已经具备自由咨询、选择性检索、来源绑定的会话条件、可留白的创建预览、PlanningRun/Revision/Validator/Accept、地点讨论背景和独立地点路线页。没有依据重写整套 Agent 或取消现有状态边界。

主要问题集中在入口和能力之间的衔接：手动排程成为突出入口；新预览的“继续讨论”实际上拒绝预览；日程页选中的日期没有传到助手；未创建 Trip 的明确地点打算没有独立持久化路径。修正这些问题需要少量前端联动和受限的事项保存能力，单纯隐藏表单不足以完成目标。

## 证据范围与限制

- VERIFIED：下表标为代码证据的分支、类型、接口和界面文案，逐项读取当前文件确认。
- MEASURED：通过内置浏览器打开 `http://localhost:3000/trips`，列表显示“草稿服务暂不可用，请重试。请求失败（HTTP 502）”；主机 HTTP 页面返回 200。页面外壳可访问，数据链路不可用。没有重启、部署或修改正式服务。
- INFERRED：由调用关系推断的体验后果；未用真实模型断言任意句式一定失败。
- HYPOTHESIS：新交互能否降低认知负担，需要原型走查和后续真实使用验证。自动测试不能替代用户验证。
- 用户截图用于定位原有信息层级；截图中的具体旅行记录未被当作当前数据库事实。所有原型内容是合成样例。
- 当前工作区有大量既有修改。本轮只增加此目录的审计/契约/原型/验证产物，并更新交接文档，不改运行时业务文件。

## 发现与代码依据

| ID | 发现 | 可复核依据 | 用户后果及判断 |
| --- | --- | --- | --- |
| A01 | 日程信息被重复编辑区域和管理控件稀释 | `web/src/journeys/JourneyPage.tsx` 同时渲染 EffectiveRequirements、ArrangementExtras、执行卡、已确认日程、调整表单；`product/ArrangementExtras.tsx` 再逐日列出修改、路线按钮 | VERIFIED 结构，INFERRED 负担：用户需要区分两套相似入口。应合并为一天一个主视图，要求管理按需展开 |
| A02 | 地点卡“安排具体时间”展开零起点表单 | ArrangementExtras 的 setScheduling 清空日期/钟点/时长；scheduleChoice 要求日期、时间、时长及地点身份 | VERIFIED。明确知道时间的用户可继续直接编辑；默认应提供“请 AI 建议怎么安排”，让 AI 承担时间组合与核实 |
| A03 | AI 已能主动生成候选；不能笼统归因为缺 Agent | `assistant_capabilities.py` 的 create/modify 映射 planning；`assistant_service.py` create_planning_run；JourneyPage.propose 直接提交选定范围 | VERIFIED 能力存在。INFERRED 主要入口没有突出能力；真实建议质量仍未在本轮测量 |
| A04 | 无 Trip 的明确地点打算缺独立保存能力 | `TripArrangementItem.trip_id` 必填；`assistant_memory.MemoryUpdate.field` 只有城市/日期/天数/偏好/要求等，无独立事项；`prepare_action` 需要起止日期，confirm_action 创建 Trip；apply_arrangement_message 对无 Trip 的“先聊”明确不保存安排 | VERIFIED 限制。模型可能记在对话里，但不能据此声称已成为可独立检索、撤销的保存事项。需要独立持久化记录并关联来源会话，详见最小工程计划 |
| A05 | 已有 Trip 的自然编辑范围很窄 | `assistant_arrangement.choice_command` 使用完整匹配，主要修改已有事项；apply_arrangement_message 要求唯一匹配；自然新增并不是通用路径 | VERIFIED。不能把“保留某地点”的支持当作任意自然打算均可新增；需要语义提取复用和服务校验，而非再堆句式 |
| A06 | 日期/活动背景在页面→助手途中丢失 | `journeys/journeyApi.ts` 的 JourneyAssistantContext 无 selected day/activity；JourneyPage 顶部只传 tripId/city/prompt；TravelAssistant.send 未传顶层 selected_day_id/selected_activity_id，后端消息接口和 PlanningRun 已支持这些参数 | VERIFIED。用户选第二天说“这天下午轻松点”没有可靠的界面锚点。复用现有消息参数，添加可见范围即可 |
| A07 | 已经存在“正在讨论某地点”，并非所有上下文都脱节 | `productAssistantContext.ts` 传 canonical UUID、discussing_place_id(s)、只读 Trip、topic；TravelAssistant.openAssistant 替换读取背景；地点页明确发起助手 | VERIFIED。保留既有机制。缺少跨地图点击的明确讨论切换、完整的范围展示与歧义处理；不能声称需要新万能 Context |
| A08 | 旅行背景对用户可见度不一致 | TravelAssistant 头部只对 place 显示具体地点；只有 tripId 时使用“一起探索下一段旅程”；路由 effect 进入 Trip 设置背景，离开仅清 routeTripSeen，不自动清 context | VERIFIED 代码；INFERRED：从旅行回到首页可能继续沿用旧 Trip 但头部不明确。应显示作用范围及“退出这趟旅行” |
| A09 | “继续讨论”会清除待采用预览 | `AssistantDecisions.tsx` preview 第二按钮调用 decidePreview(false)；`assistant_service.confirm_action` not accept 分支清 pending_action 并记“已取消这次操作” | VERIFIED 语义不一致。继续讨论应保留建议 ID/版本；“放弃这份建议”才调用拒绝接口 |
| A10 | 出发就绪文案与可执行内容不匹配 | JourneyPage 根据 execution.not_started 显示“准备好了，就开始今天的旅行”，按钮在当日没有活动时 disabled；日期阶段由 tripPhase 判断 | VERIFIED。未排活动时应说“这天还没排具体活动”，不把未来旅行或空日程表达成已准备妥当 |
| A11 | 刷新恢复和写保护已经有基础 | TravelAssistant 保存 session ID、topic 与上下文；服务端持久化 messages、pending_action、run；Accept 检查版本、保护锁定与发生过的活动 | VERIFIED。原型应复用相同行为边界，不能把 localStorage 演示当作服务端恢复已完成 |
| A12 | 附近推荐与直接路线无需先创建 Trip | DiscoveryApp 的地点页、Route 页面；productAssistantContext.read_trip_id 可空；route_request 由真实地点 ID 构成 | VERIFIED 入口存在；本轮因 API 502 未测实际查询。附近推荐不应推断 GPS；真实导航仍按已提供能力表达 |

## 对四个用户问题的处置

1. **维护表单**：保留直接编辑作为次级展开；默认呈现已有选择、当天内容和 AI 可承担的动作。整页不再常驻“要求管理＋事项管理＋已确认日程＋调整表单”四套工作区。
2. **缺乏主动安排**：已有明确安排请求就进入现有候选流程，不再问“是否开始规划”；只补真正阻塞的参数。无明确请求的知识问答不创建安排。
3. **打算难以保存**：将“记下一个明确打算”与“采用具体日程”分开。未归属旅行的打算独立保存并关联来源会话，出现在统一“我的安排”的轻量事项区；现阶段该服务能力仍需增加。
4. **上下文脱节**：明确展示地点/日期/旅行的作用范围；只有“讨论这里”“调整这一天”等用户动作切换目标；浏览不提供写权限。沿用现有 ContextEnvelope、消息 selected 参数和版本保护。

## 用户路径对照

| 路径 | 当前 | 目标契约 |
| --- | --- | --- |
| 问成都喝茶文化 | 咨询能力已存在 | 正常回答；不产生计划、标签确认或保存事项 |
| 明天下午去人民公园，时间不定 | 可能停留在会话或进入起止日期创建预览 | 日期按表达时刻锚定；保存一条打算；明确“已记下”，可撤销；不移动其他活动 |
| 让 AI 排第二天，下午留白 | 页面有局部候选能力，助手未完整带所选日期 | 显示第二天背景；生成候选，保留留白/预约；采用前展示影响 |
| 在建议上继续讨论 | 预览按钮实际拒绝 | 保留预览并聚焦输入；明确放弃才拒绝 |
| 地图点地点后问“这里” | 地点入口已有背景，地图浏览与讨论策略未统一 | 地图面板显式“讨论这里”；旧背景在输入上可见并可移除；歧义写入必须澄清 |
| 候选后别处修改，再采用 | 正式 Accept 有版本保护 | 展示过期差异，保留输入，重新生成；不自动覆盖或静默重试 |

## 完成边界

本轮完成交互审计、目标契约、脱离业务 API 的操作原型、原型状态测试及最小工程清单。没有发布新产品行为；生产真实模型、地图、天气、持久化与导航验收仍待隔离服务可用后执行。
