# Companion 普通对话与回复展示修复

2026-09-30。实际代码目录：E:/Study/RoamSync。

## 问题与决定

VERIFIED：历史文化问答默认进入知识库 factual 分支，跳过模型生成；混合建议由
`_answer_text` 拼接断言、内部 knowledge 引用、推断、重复建议及资料缺口。
只有美食问题允许通用知识，七篇杭州语料因此变成普通对话的覆盖门槛。

普通稳定旅行对话改为 bounded CompanionDraft 通用知识回复；来源/出处/证据/
核实类请求保留 reviewed assertion 路径，实时信息与原始决策理由仍由服务端保护。
response_text 是完整最终答案，suggestions 单独保存，避免重复追加。
来源编号、分类、资料缺口留在结构化结果；前端默认折叠 Thinking 回答说明及来源。
不展示隐式模型推理。旧消息只清理展示，未改写持久化聊天记录。

无数据库迁移，无新增工具权限、图节点或行程修改权威。知识库测试使用明确来源请求；
新增普通对话案例验证不检索、建议不重复、两条结构化建议可保存和无 Planning handoff。

## 验证证据

- VERIFIED：隔离 compose.test / PostgreSQL 全套 587 passed，2 个既有 Starlette 弃用 warning，34.51 秒。
- VERIFIED：Web 123 passed；typecheck 与 Docker production build 通过。
- VERIFIED：api/web 重建并启动，均 healthy；http://127.0.0.1:3000/trips 返回 200。
- MEASURED：运行中 API 容器对真实 glm-5.3-flash 做两轮无数据库 smoke，
  `backend/evals/companion_conversation_smoke.py` 可复现；两次均 completed/stop。
  “西湖有哪些历史文化特色？”14.21 秒，519 completion / 997 prompt tokens。
  “我想在杭州找一些适合摄影的活动，请给我两个有文化特色的建议。”10.38 秒，
  387 completion / 1853 prompt tokens。第二条提供龙井村茶园采风与雷峰塔夕照拍摄，
  恰好两条 durable suggestions。两次均无 retrieval、knowledge evidence、内部编号、
  资料分区和 Planning handoff。未创建聊天 session、旅行或修改正式数据。

## 实际限制

通用知识标记 model_general_knowledge_unverified。本轮真实模型 smoke 验证完成输出、
无检索门槛、展示和建议数量，不构成历史事实准确率测量。
模型仍可能混淆历史关联与工程归属或使用过强的“唯一”“先河”措辞；
精确史实与来源核验是独立质量问题，不应因本轮展示改善而宣称解决。
Thinking 是公开回答依据与处理说明，不是隐藏 chain-of-thought。
