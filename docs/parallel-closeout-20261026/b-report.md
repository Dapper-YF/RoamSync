# B：复合只读回答、预算计算与有限上下文恢复

状态：**代码已整合，正式源码上的公开真实模型回归已补齐；整体仍为 HOLD / NO-GO，待完整产品验收**。

产品提交：`30142f8348ffd5afd626b6b81404833e87a6b253`，基于共同 WIP `8e53fd68d91720f1cf1674a97483e67f9bff8bf3`。该提交没有新增业务表、路由或公开写入口；规划仍走 Planner → Revision → Validator → Accept。

## 修改内容

- 预算上下文只有完整子句符合预算声明语法时才从费用覆盖中排除。`另付超预算10元服务费` 现在作为待计算费用，缺少该金额时澄清；完整的预算声明仍可与合计任务并存。
- 预算余量任务的 `source_quote` 只有在原文中的完整金额、角色及费用覆盖都能通过服务器计算时，才绑定到本轮完整问题。省略号、缺失费用和重复金额仍不能得到已计算结果。
- 单一解释任务可在严格条件下恢复被模型截短的推断上下文，并保留 `walking_effort` 等子任务焦点。复合 peer、路线、写任务及否定/假设问题不从父句取得新能力。
- 开放时间恢复只处理唯一、完整的开放时间子任务；普通地址查询仍保持 POI 能力。

## 验证

- 定向回归：48 项通过，0 失败、0 跳过，7.574 秒。使用新建的隔离测试库 `127.0.0.1:15435/roamsync_s6_integration_b_20261026_test`，Windows SelectorEventLoopPolicy；未调用真实模型或地图服务。完整 JUnit 在 `docs/evidence/parallel-closeout-20261026/b/coordinator-targeted.xml`。
- B 分工早先运行的 `targeted-after-estimates.xml`：176 项通过，0 失败、0 跳过，12.928 秒。该回归启用了 `ALLOW_MAP_ESTIMATES` 供旧地图估算 fixture 使用，不算真实高德验收；第一次未启用时因测试环境缺少高德 Key 产生的失败日志也予以保留。
- 整合后的 A/B/C 定向集：167 项通过，0 失败，13.37 秒。它覆盖候选来源、预算与只读任务、保存时长边界及快照 fixture，见 `docs/evidence/parallel-closeout-20261026/integration/targeted-merged.xml`。
- `public1.json`、`public2.json` 是共同基点 `8e53fd6` 上的真实 GLM 基线轨迹，六个 case 各一轮/多轮；它们不是 B 修复后的成功证据。原始输出保留在 B 证据目录。

## 正式源码补充验证（2026-10-26）

B 原任务因额度限制中断后，由整合对话在 `E:/Study/RoamSync/backend` 补跑公开六轮，实际模块路径与解释器均记录。新建专属空白库 `roamsync_s6_b_official_merge_20261026_test`，真实 GLM `glm-5.3-flash` 与高德/搜索工具；完整输出、工具轨迹、逐轮八表状态及源码 hash 位于 `docs/evidence/parallel-closeout-20261026/integration/official-public-b1.json`。

六轮均无异常：105元/余15元且不保证最终账单；额外10元服务费未被遗漏为83元（当前安全澄清）；直接否定完全不用走路并给核实办法；个园/何园按原顺序比较，第二个绑定何园地址，何园开放资料明确当前适用性缺口，同时独立返回个园→何园步行约2.1公里/29分钟。源码前后 hash 相同，八张正式业务表均维持空白且 hash 不变。

正式目录完整后端回归为2183通过、0失败、0跳过；使用新独占主测试库与独占 promotion 测试库。该公开开发回归不替代浏览器完整采用链、跨城市新对象安全实验及封存独立评分，不构成整体产品 GO。

未读取封存新题；未部署；未操作正式数据库或 Obsidian。
