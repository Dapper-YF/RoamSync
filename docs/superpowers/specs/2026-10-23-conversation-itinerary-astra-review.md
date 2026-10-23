# Astra Medium 对话/行程重设计复核

2026-10-23。审查模型gpt-6-astra，reasoning=medium，独立只读子代理conversation_design_review。用户明确要求本次设计复核。未运行数据库/浏览器、未读私有题面、未启停正式服务，不能当作实现验收。

审查对象：正式6b298ca与整合8dbf685相关源码，以及2026-10-23-conversation-itinerary-design.md完整设计。

## 初审定位

- 元数据创建提案被包装为可采用行程；真正规划在Trip创建后才开始。
- 既有Draft/PreparedPlan/promotion值得复用，但统一停留时长不足以表示午餐、逐站时长和窗口。
- checkpoint式promotion存在Trip已创建但日程未采用中间态，不能仅用按钮变化消除。
- 现hash不覆盖全部标题/说明/照片，必须增加同源展示绑定。
- Handbook已有逐站照片插槽，但身份不应只依赖名称/近邻；成都只有一个POI的两张CC0图。

## 最终设计审查结论（条件性）

架构方向可条件性批准，补入以下3项P0和4项P1后可进入实施；不构成产品GO：

1. P0：Operation持久化protocol_version/execution_mode；新atomic与旧checkpoint按服务端记录分派。抽取不提交数据库单元，按operation→trip→revision→run→draft锁序复用现守卫。正式写入、授权消费和会话绑定同事务。
2. P0：meal/rest/free/optional/blank_day映射现ArrangementItem，不伪造POI；窗口参加冲突和物化前后等价校验，不只activities/routes。
3. P0：Draft/PreparedPlan/Operation显式schema版本解码，历史缺省有固定规则；旧客户端不能覆盖新字段或绕过新采用协议，保留旧checkpoint恢复例外。
4. P1：生成器消费服务器结构化目标/范围/POI，单点修改服务器保留未授权部分，不让自然语言重新定义权限。
5. P1：哈希依赖为PreparedPlan→Presentation→发布绑定，避免循环。许可撤回使旧展示失效；图片加载失败仅视觉降级。
6. P1：保存事务复核持久化话题/候选绑定，取消与保存按提交顺序仲裁，不靠前端状态。
7. P1：回滚验收覆盖所有本操作正式写入及消费/会话，不以五表不变掩盖其他残留。

## 设计处理记录

七项均已写入主设计对应章节；将“锁Draft/操作”替换为明确统一锁序。保留旧协议恢复、原Validator/Accept和Execution保护，新请求不降级旧协议。
当前仅文档修订，产品未实施；新原子采用、字段/窗口契约、模型/媒体整合与真实端到端仍需开发和验证。设计方向的批准不能被写成产品质量通过。

## 修订后核对

Astra Medium再次只读核对两份文档：七项条件均已准确入文，未发现新阻塞矛盾。结论为“设计已补齐本轮条件，可在用户确认后进入实施；非产品GO”。未运行环境或修改文件。
