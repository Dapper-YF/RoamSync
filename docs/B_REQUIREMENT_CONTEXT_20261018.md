# B：验收背景与有效旅行要求分离

## 本轮新增修复

VERIFIED：`capture_explicit_requirements(force=True)` 原来把要求栏每个未匹配
typed atom 的分句直接登记成 `user_requirement`。证据中的“此次验收未实际到访”
因此获得有效要求身份，随后按日期进入 Planner。普通聊天入口也只在整条消息上
判断一次是否有要求，无法隔离同一句中的背景与要求。

`4c9bbe2` / `7c045d4` 将完整的用途/到访经历陈述与未来旅行指令分开：

- 新捕获不为完整验收用途、未到访陈述创建有效要求；原消息仍保留。
- 既有记录不删除、不批量重写；只有有效要求投影排除这类通用背景。
- 真正的指令优先，保留“不要自动确认到访”、夜间限制、婴儿推车、哮喘约束。
  “未去过的地方优先”“没去过故想去”也保留。
- 分句检查，混合疑问不再吞掉另一独立的明确要求。
- 继续保护各日范围与局部撤销；引用已撤销数值不重新启用它。

这是两个完整言语行为形式的有限识别，不是全面自然语言分类器；未知表达沿用
原有捕获行为。没有改变公有 schema、权限、Graph 或 Accept 授权规则。

## 定向回归

MEASURED：背景/复杂请求/有效要求/时长边界65项通过（其中本轮新增26项），
既有意图、产品意图与意图数据集109项也通过。使用现有测试 Docker 镜像、canonical app/tests 只读挂载和专用测试
数据库。宿主 Python 缺少 psycopg，初次 collection 失败未计入通过结果。

```
tests/test_requirement_context_boundary.py
tests/test_complex_requirement_intents.py
tests/test_effective_requirements.py
tests/test_duration_intent_boundary.py
tests/test_planning_intents.py
tests/test_product_intent_regressions.py
tests/test_intent_eval_dataset.py
```

## 实际模型验收

脚本：`backend/evals/requirement_context_live.py`。只允许隔离开关与指定隔离数据库，
创建全新标记 Trip；背景注入只作用于该新 Trip，模拟既有历史污染。不读取或修改
其他旅行，不证明真实预约、开放或到访。

MEASURED：新建隔离 Trip `24fc503a-41fa-4f13-92a2-5ead814bdd9d`，
Run `7530c4b3-d200-47cc-a5a5-54f9fe5f06ed` 使用真实 GLM 5.3 flash 进入
Graph/Validator 并明确 Accept，版本3→4，第二天河坊街60→45分钟。
实际 `revision.before_snapshot.effective_requirements_by_date` 不含原文背景和
第二天已撤销步行要求；背景原记录仍保存。第一、三天的地点身份、时间、时长、费用、
状态和锁定等业务字段保持；第一天 activity version1→2、两天 updated_at 被既有
Accept 保存策略触碰，不能宣称完整 JSON 不变。

`docs/evidence/b-context-20261018/live-final.json` 保留最初过严 JSON 全等断言的失败；
`live-reconciled.json` 是同一次已接受旅行的补读，没有重复 Accept。此前首查两次
Provider 未配置503、eval漏填edit字段422和误用PATCH405也原样保留；均非模型成功。

初次补读中“把它改成45分钟”没有误写正式数据，但出现“45分钟”地点澄清，暴露
新的时长/换地点分类反例。原 `live-reconciled.json` 的passed只代表当时列出的保护与
投影检查，不能代表澄清质量通过。

新增修复 `a2da7b0`：替换语法右侧是完整数值+时间单位时，解释为活动属性修改，
左侧仍须绑定活动；“45分钟咖啡馆”等真实名称仍走地点身份核实。没有增加schema，
没有绕过候选与明确确认。重启后同一已Accept Trip的只读
`live-reconciled-fixed.json` 实际证明：

- 未绑定“它”时只询问活动/日期，不再把45分钟当地点。
- 提供明确UI活动和日期身份时，不再澄清，目标精确绑定原第二天活动，仍走
  `plan_preview` 并要求用户确认。
- 正式版本仍为4，未再Accept；所有上述背景与日程语义补读仍通过。

时长反例修复后的额外验证是实际resolver解析，并未为其重复新开模型候选并Accept。
实际GLM/Graph/Validator/Accept的证明属于本轮先完成的复杂长句与背景投影场景。

## 剩余范围

任意多轮语言引用并没有因此全部解决。已选择的活动可提供明确身份；未绑定的
“它”需要澄清，不能猜选历史活动。有限表达之外的背景、复合歧义和跨轮实体引用
仍需持续真实对话反例，不能以本轮数量替代这些质量结论。
