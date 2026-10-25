# 保存态修改来源独立复核

日期：2026-10-25。对象：隔离树中的 assistant_operation.normalize_modification_evidence、validate_decision 调用点及 test_stage4_saved_source_contract.py。仅写本外部报告，未修改产品或读取封存题。

## 发现与复验

初版新增 normalizer 在缺少顶层 authorization_quote 时，会用单个 typed operation 的当前 literal raw_text 补齐重复来源字段。approved_draft 对 replan_trip 不进行逐目标肯定动作验证，导致正向动作可以借给保留对象。

独立反例：“请把人民公园改为60分钟，宽窄巷子保持不变”，typed replan_trip 的 activity_mentions 错指宽窄巷子。实际 normalizer 返回已补授权，而实际 affirmative_entity_source 对宽窄巷子返回 False。初次复现使用真实 SemanticIntentDraft 与 assistant_operation，并从实际 capabilities 源码提取三个纯策略函数到内存，未访问数据库或 provider。

主代理新增至少一个显式目标及逐目标 affirmative_entity_source 校验。随后使用 `E:/Study/RoamSync/backend/.venv/Scripts/python.exe` 导入实际完整 validate_decision，确认上述保留对象反例不再返回 modify；此项关闭。

第二项发现：仅排除 primary_intent=unsupported 不等于排除了 unsupported operation。完整 validate_decision 实跑：“请调整人民公园”，primary_intent=replan_trip、唯一 operation=unsupported、activity_mentions=[人民公园]、缺 authorization_quote，仍返回 intent=modify、非空授权、unsupported operation。主代理已限定五种修改 primary_intent，并要求唯一 operation 与 primary_intent 相同；unsupported/query/general/search 不再补齐授权，此项关闭。

## 最终复验

使用官方 venv 直接调用测试文件的纯函数，独立完成 11 个断言实例：1 个合法修改来源恢复、4 个非授权来源、2 个保留对象借目标、4 个非修改 typed operation，全部通过。无数据库/provider调用。

曾尝试 pytest 常规入口，收集前被项目数据库安全守卫拒绝（未显式设置 APP_ENV=test）；未绕过守卫执行数据库测试。上述直接调用仅适用于这些不使用 fixture 的纯函数断言，不冒称 pytest 完整运行。

最终结论：本轮发现的两个来源/操作恢复缺口均已关闭，未发现新的补丁级实质阻断；仍须进行真实修改预览及明确采用链路、完整回归和单次封存验收。

## 安全与适用边界

- 审查中的实跑只涉及决策与来源校验，没有执行正式写入，不能将路由恢复缺口描述为已发生未经授权数据库变更。
- adopt 不在 SemanticIntentOperation 枚举中；未发现该 normalizer 直接调用采用或正式写服务。
- 当前补齐仅面向单一、唯一出现的当前 literal 来源和显式目标；不支持全局无目标命令的补齐，不拼接分离来源，不生成目标 ID。
- 仍须保留之后的目标 grounding、权限、版本和候选采用校验；来源表示修复不能代替这些契约。
- 本复核未运行真实模型、浏览器、封存题或完整产品测试，不代表最终 GO。
