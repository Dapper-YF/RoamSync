# Latest Handoff

## Snapshot

2026-10-22 第二轮A2准备，产品源码未改。共同起点6a65ece3acc3ea9a32087c11a2cbbe05173862dc是隔离候选，非正式部署。A2树E:/Study/RoamSync-reliability-a2-20261022，codex/reliability-a2-20261022。正式E:/Study/RoamSync、3000和正式数据库保持不动。

## Current Freeze / Rehearsal Status

设计待确认，未实施。B为主线，统一一次语义决策到服务端operation、条件投影、复合任务与创建闭环；A先持锁跨网络根因，再Worker失联恢复；C只验收真实安排/探索/聊天及交互断点。新统一门槛docs/QUALITY_GATE_V2_20261022.md，A可审查设计docs/PLANNING_RELIABILITY_A2_DESIGN_20261022.md。brainstorming技能显式要求行为改动前设计确认，已向用户提交一次确认，期间只做准备与验证。

## Prior milestone baseline (before shadow split)

第一轮统一BASE f116ada；整合6a65ece接收A9f89fe3/B831ec24/C207c9b7及旧记忆兼容f39960c/d6c587c。正式仍6b298ca。第一轮3项工程修复、239前端/1469+25后端通过；B旧保留题5/20、1关键无证据保证，整体NO-GO。既有完整报告docs/ENGINEERING_A_AUDIT_20261022.md。

## Prior verification

MEASURED：A2从共同起点构建新测试镜像，在全新随机项目/tmpfs库重跑主1469、专25，零失败/零跳过，source_unchanged=true。阶段188.234s/36.828s（含迁移与容器开销），不是咨询性能。证据docs/evidence/reliability-a2-20261022/baseline-tests.json；全日志/JUnit外置E:/Study/RoamSync-a2-evidence-20261022/baseline-tests，测试资源已自动回收。

VERIFIED代码追踪：create_planning_run锁Trip后可await模型；commit=False上层可能已有会话锁或未提交Trip，不能直接commit释放。save_plan_revision默认路线enrich跨锁，但正式Graph.persist显式enrich_routes=False，不误称全部Worker都会走该分支。TripPreferences.version独立，必须复核双版本。

A/B接口已对齐：B load_planning_intent_snapshot(session,trip_id,payload)返回脱ORM frozen快照；resolve_planning_intent_snapshot(snapshot,payload,*,semantic_provider=None,prepared_draft=None,default_planning_intent=None)无session解析；prepared_draft有值仅grounding/policy。A新增PreparedPlanningIntent绑定原文、Trip、selected IDs、Trip/偏好版本及draft，锁内复核，不把客户端resolution当授权。B先交helper提交，A尚未接入实现。

## Prior blockers (historical)

C在Git外只读封存新20题与预先规则，SHA256=8bb1a83faa83659cf6ceb95745e29934922629012c176061b986dba23bef7da2。题面不发A/B或共享Git，冻结后独占库评测，目标≥16/20且零关键保证；阶段目标非普遍可靠性证明，非独立人类盲评。C公开流程基线库roamsync_product_c2_baseline_test，3044/18044，保留题另库。

OPEN：重复解释、条件规范值/否定投影、复合任务/创建失败；规划短事务/Worker claim fencing/传输取消；公网owner隔离P0。完整真实咨询→检索→建议→创建→采用→修改→刷新→异常恢复、同输入旧新对照、最终统一浏览器/工程验收都必须完成后再评审部署。本轮没有部署授权。

## Interview framing

当前交付是已验证起点、具体根因、A/B接口和四项门槛，不是新的产品修复或质量通过。后续先按确认后的设计实施并保存失败反例，再验收。无Obsidian写入。
