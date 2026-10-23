# RoamSync 对话候选与正式行程重设计

2026-10-23。状态：审计及设计稿，待设计复核/用户确认，未实施、未部署。

## 目标、来源与隔离

用户提供的粘贴需求和P1/P2/P3是本轮产品要求。P1是完整时间轴的参考，P2是图文对话的参考，P3是已复现的错误确认流程；参考图不是已经实现或已核验的候选证据。

正式源码E:/Study/RoamSync HEAD=6b298caddb79125991bfc5183ddeefc09029f31c，只读审计。正式未提交README/Nginx/脚本、未跟踪成果、env与数据全部保留。
复用已隔离的E:/Study/RoamSync-reliability-a2-20261022，新分支codex/conversation-itinerary-redesign-20261023，起点8dbf685050d14a1b12ac86a78f3e81506c2bc595。
此起点来自正式固化基线f116ada及上一轮A/B/C整合，产品受测85d0；它未部署、产品NO-GO，不能称为正式新版。继承A2短事务、claim、条件/操作修复，避免从旧正式HEAD丢失这些工程成果。

## 已核对的现状

| 现象 | 实际机制及证据 | 设计约束 |
|---|---|---|
| P3只有日期和创建说明，却显示采用按钮 | web/src/product/AssistantDecisions.tsx将session.pending_action直接包装为旅游建议；backend/app/assistant_service.py confirm_action先create_trip再create_planning_run | 元数据不是行程候选，不能改个按钮名继续调用原创建流程 |
| 聊天候选可能形成长结构清单 | AssistantDecisions将PlanRevision活动/路线逐项展开；NaturalAssistant也保留旧渲染分支 | 聊天保留顺序、时间、变化和重要约束；完整时间轴留正式页/按需预览 |
| P1不是完整实装的直接证据 | 用户P1是目标布局参考；当前HandbookJourney确有完整时间轴、逐活动HandbookPhoto插槽 | 不误报当前聊天已有完全相同P1 |
| 草稿/采用已有可复用基础 | drafts保存owner/version/相对天；draft_promotion保存PreparedPlan、hash、有效期、幂等、事实等价复核和Validator/Accept | 扩展这条路径，不新建第二套Planner、草稿库或写权限 |
| 现有草稿不能无损表达用户要求 | DraftItem只有name/note/place_id；promotion preparation统一duration_minutes、统一交通，空日阻塞 | 必须补逐项时长、留白/午餐、可选、整天留白及结构化窗口，不能保留原文就说满足 |
| 保存失败可能出现空壳Trip | promotion的T1提交Trip、T2才Validator、再刷新事实并Accept | 新对话保存要求原子正式落库；旧操作恢复保持原协议并如实展示中间态 |
| 两页图片尚非统一媒体身份 | 聊天assistant_images可用Tavily主题配图；HandbookPhoto先名称/坐标近邻选择；图库project_images本身有精确POI守卫 | 候选与正式站点仅共享精确POI授权媒体，不用主题搜索照片替代站点实景 |
| 成都图库只覆盖一个POI | reviewed_images.json人民公园B001C7X8QA、Suicasmo/CC0两张；没有宽窄巷子条目 | 不能把两张公园图说成两个地点覆盖；缺图正常降级 |
| 展示不全部受哈希保护 | preparation.semantic_values排除name/note，图片不在evidence hash | 新展示投影要绑定文本、活动ref和媒体身份，旧hash不能冒称覆盖新摘要 |

## 方案比较与选择

1. 只改按钮/把时间轴挪页：成本低，但仍在无候选时创建正式Trip，拒绝。
2. 另起聊天Planner和自由JSON日程：可快速做漂亮界面，但制造第二意图/条件/写入路径，拒绝。
3. **扩展现有Draft→PreparedPlan→正式Validator/Accept，建立两个展示投影**：工程量较大，但可以持续修改同一候选，保留身份、版本及安全边界，采用此方案。

## 交互与视觉

保持当前RoamSync暖白底、深绿文字、绿按钮及顶部导航，不重做品牌。聊天消息使用开放段落；景点媒体桌面并排最多两列、手机单列，图片约16:10，复用PlacePhotos来源/许可披露与失败处理。

用户提出足够明确的规划请求后，直接显示“正在查地点和路线，准备一份未保存的安排”。不再弹日期/城市元数据的采用卡。
结果依次是：简短总安排说明；按真实候选顺序的景点图文（名称、地址、起止/停留、事实或建议的区别）；真实路段时间/距离的简洁说明；午餐/留白与尚未核验的重要信息；小型操作区“保存到我的安排”“继续调整”。仅ready候选有保存操作。
聊天不默认展开长时间轴。可提供“查看完整候选”只读展开层/抽屉，不跳正式Trip，也不创建壳对象。
讨论不自动保存。时间微调只解释差异，不重发相同照片；新增/替换地点才显示相关新媒体。明确保存后显示服务端实际结果，成功时给“查看我的安排”。

“我的安排”列表只把实际已采用的正式行程作为成功安排；日程页保留日期标签和完整时间轴，每个主要地点有对应照片、起止、地址、简述，连接线旁显示交通方式/距离/分钟/来源。午餐与休息是窗口，不伪造餐厅或景点照片。整天留白保留，不自动塞活动。
已存日程的“和AI商量”携带Trip/day/activity/版本，后续仍走PlanRevision；聊天给改动摘要，采用后两页刷新同一正式状态。
生成失败、修改失败、保存失败、过期、409分别给准确恢复动作，不统一误写“安排有新修改”，不隐藏错误而声称完成。

## 同一候选与约束契约

复用DraftRepository CAS和既有schema表。扩展DraftPlan：稳定item_ref、活动/meal/rest/free_window/optional/blank_day类型、逐项duration与来源、明确固定窗口；地点保留canonical place_id及provider_place_id。日期和每日窗口属于草稿结构化条件，不从示例默认10点/18点。
只有已核实真实地点的visit映射CandidateActivity。meal/rest/free_window映射既有ArrangementItem的free_window及明确日期/起止；optional映射optional，不挤入日程；blank_day映射整天留白，不伪造午餐POI。用户明确餐厅才创建真实food活动。窗口与事项既进入prepared/presentation hash，也进入物化、snapshot_for及verify_formal_binding等价核验，不能仅比较activities/routes。
增加版本化日程约束载荷，保存开始日期、每日可用窗口、交通方式、预算口径、明确步行作用域与要求记录。每个硬条件投影为satisfied/violated/unverified并附来源。用户要求的硬条件不能表达或验证时，具体澄清/阻塞保存；非承诺性未知开放/库存资料清楚披露，不编造证明。
保留既有相对天范围1—14和正式候选100活动上限；新字段使用有默认值的版本化契约，历史草稿不可在读取时静默改写。现promotion真实路线只支持walk/driving，其他交通需求必须具体说明能力缺口，不能悄悄改成步行或伪称公交已核实。
活动时长是用户指定或规划分配，路线时长是地图估计，实际出发地未知不能虚构首段。不能用公园间步行满足声称内部/全天步行限制已满足。

沿既有一次CapabilityDecision交接操作与当前候选引用，生成/修改由现有草稿能力承担，不再在下游模型重判“用户到底要创建什么”。城市分类前25条不是身份权威：根据用户已选/已查真实POI解析精确引用，歧义只询问歧义项，保留其余结果。模型不得生成可赋权的ID、hash或版本。
生成器接收服务端签发的结构化输入：原授权来源、目标item_ref、允许修改字段/天、既有精确POI引用、有效条件及当前候选。自然语言仅为内容生成材料，不得重定目标或拓宽范围。单点修改未授权的item_ref及其内容由服务器从旧候选原样合并，不接受模型全量重写；已确认POI不再按名称重新搜索覆盖。

会话持久化候选阶段、draft_id/version、prepared_id/hash、presentation_hash、promotion_id及原始来源引用。用户未关联正式Trip时不设置trip_id冒充草稿。自然语言“就这样保存”由同一语义决策识别，并绑定当前实际展示的候选；引用含糊则问具体对象，否定/引用他人句子不能授权。
修改成功更新同一个draft版本，旧PreparedPlan/展示/保存入口全部失效；失败保留旧候选并明确新要求未生效。撤销、取消、新话题不继承旧采用授权。刷新、丢响应和重试恢复同一对象和幂等操作，不重新创建旅行。

## 同源展示与采用

PreparedPlan是唯一可采用数据源。服务端从它生成CandidatePresentation：活动ref顺序、时间/停留、路段、留白、约束结论、POI媒体及许可版本。聊天摘要使用这份投影，不让模型另写一份具有独立安排或承诺的文案。
新hash格式必须版本化，覆盖标题、展示名称、note、约束、活动/路线/窗口、媒体POI/来源/许可和正文投影；保留历史hash验证规则，新入口只能消费支持完整展示绑定的版本。
哈希依赖单向：先冻结PreparedPlan核心及prepared_hash，再生成引用prepared_id/hash/version的展示投影，计算presentation_hash，最后保存服务端发布绑定；PreparedPlan不反向包含presentation_hash。许可撤回/展示投影变更使旧展示授权失效，准备新投影后重新确认；单纯图片加载失败只做视觉降级，不能换成另一地点照片。
Draft、PreparedPlan、Operation分别持久化schema/protocol版本，使用显式版本解码器；无版本历史数据按固定旧版解码，不用extra=ignore丢弃新字段。旧客户端修改新版本对象拒绝，不能把新字段读丢后整体覆盖；新字段默认值仅用于真正历史对象。历史hash可按原规则验证，但不能升级成新候选采用凭据。
采用请求携带当前draft/version、prepared_id/hash、presentation_hash和幂等request_id；服务端复核owner、当前会话/话题、候选未改/未过期、事实等价。旧客户端缺新采用契约时明确拒绝/提示更新，不把旧metadata确认解释为新候选授权。

新对话保存复用promotion的物化/正式Validator/Accept，先在事务外刷新地点/路线，再在一个短事务中按下述统一锁序复核、创建Trip/偏好/地点/窗口、保存Revision、正式校验与Accept、消费授权并写回会话引用；任一步失败正式对象整体回滚。需要抽取不自行commit或开启事务的数据库单元供复用，不能直接串联各自开启事务的_t1/_t2/_apply，禁止复制第二套验证/采用逻辑。
Operation创建时由服务端持久化不可变execution_mode（legacy_checkpoint或atomic_candidate_v2）和protocol_version，恢复按存量模式分派；不能靠客户端字段、是否已有Trip或当前部署代码推断。授权/幂等记录可先在独立表持久化，但不创建正式Trip。
锁序遵循现promotion guard：operation→Trip→Revision→Run→Draft；新生成的正式行仅在本事务可见。会话在外部I/O前仅短读快照、关闭事务，最终持久化引用时排在上述业务锁之后并复核会话signature，不持Session锁进入网络或promotion。
确认同时核对持久化话题epoch及候选发布绑定。取消/新话题先提交则保存拒绝，保存先提交则取消不能伪称撤销正式行程；前端阶段不是权威。事务失败要核对所有本操作正式写入，包括Trip/Day/Activity/Route/Arrangement、PlaceCandidate/SourceRecord/偏好/Revision/Run及授权消费/会话引用，而不只五表计数。
历史checkpoint式promotion继续按既有协议恢复，不静默迁移半完成操作、不隐藏已创建Trip；其UI明确“已创建旅行但日程尚未采用”，同一operation恢复，不重建Trip。新对话不会创建这种中间态。
未采用前不在正式表插入临时Trip，即使打算回滚也不能拿它代替草稿校验。准备阶段做可验证条件预检；最终正式Validator仍在用户授权后原子单元内重跑。初始采用与既有行程修订都保留原Validator/版本/Accept及Execution保护。

## 实景媒体

聊天站点与正式活动都读取同一精确canonical/provider POI对应的reviewed_images媒体。名称/城市/坐标只作附加守卫。通过正式PlaceCandidate canonical_place tag或明确DTO字段保留身份，不根据同名公园猜图。
复用现有480/960本地变体、缓存、lazy loading、来源/作者/许可/裁剪说明和onError隐藏。普通改时间复用媒体，不重复网络配图。
补宽窄巷子前必须审核原始Commons文件、作者/许可/来源、真实内容与POI关联，并保存原始/变体哈希；源许可或身份不合格则不加入图库。用户P2中的照片没有可验证授权元数据，不能直接作为产品资产。
若没有合适来源，页面保持无图而非破图/错图，并交付待接入清单；不会用AI生成照片或Tavily搜索结果冒充真实站点图片已完成。

## 验收与NO-GO

先保留反例：无候选不能采用/无正式写；同候选改时不丢午餐/两站/窗口；过期/旧hash/错owner/旧客户端拒绝；并发修改保存不采用旧候选；保存任一步失败正式五表不增；丢响应只采用一次；图片错POI不显示。
React测试核对阶段与摘要/媒体，数据库测试验证真实事务/版本/Validator/Accept。工程全量用已有随机tmpfs测试入口，不能读正式DSN。
真实隔离验收从新库进行，真实模型、两个真实POI、真实地图路线、逐站照片→候选→同对象修改→明确保存→正式日程→再修改。每段保存请求、SSE、候选hash/正式映射、活动数、时间、来源、路线、要求与1440/390/320截图。合成原型不替代这条链。
路线、身份、硬条件或保存未跑通则NO-GO；部分图片缺失单列，不把漂亮页面当完成。上一轮保留题已用，本轮不重采样凑质量分。
正式3000/8000/15432不启停、不写库、不迁移、不部署。仍有公网owner P0，不因本轮对话改善宣称可公网发布。

## Astra Medium初审

只读审查已完成：以上方案已吸收创建提案≠候选、统一时长不足、promotion中间态、hash展示缺口、POI/媒体精确身份六项意见。该审查不是实现或产品批准。最终设计复核结论另存；当前没有产品源码修改或新端到端通过证据。
七项最终条件补入后，Astra Medium再次只读核对确认无新的阻塞矛盾：设计已补齐本轮条件，可在用户确认后进入实施；非产品GO。
