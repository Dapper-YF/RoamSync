# RoamSync V2：真正剩余的决策与验证门禁

日期：2026-10-15。第二轮修订后版本。18项旧议题的处理已归入[逐项回应](ROAMSYNC_REVIEW_ROUND2_RESPONSE.md)和[ADR](ROAMSYNC_ARCHITECTURE_DECISIONS.md)，本文件只保留未决条件，不重新开放已接受的产品原则。

## 1. 产品负责人只需确认的少数事项

| ID | 待确认事项 | 明确推荐 | 备选/影响 | 何时必须确认 |
|---|---|---|---|---|
| P01 正式化失败语义 | 是否接受一次“创建并采用”后，后台失败可能留下可见“已创建、方案未采用”的Trip | **批准P1可恢复协调**；同operation重试、可取消/归档、不自动删；方案实质变化必须重审 | 若要求最终全有或全无，先验证P2短SQL原子方案，核心改动/回归成本更高 | C3实施前；推荐先做P1 spike |
| P02 阶段交付边界 | 确认Web路线+external与Androidwalk/drive受控GPS分阶段验收；酒店首期POI与核实入口 | **按该边界推进**；GPS未过不得宣称独立应用内导航完成；库存未接不得宣称有房/保证价 | 如首期必须实时报价，则商务授权/Provider成为关键路径，不能用模型补齐 | G0任务范围批准时 |
| P03 数据留存与行为启用 | 精确位置、终止命令、草稿、聊天、证据、正式历史/缓存的期限与用户删除恢复期 | **按类型最小留存，期限另定；先显式偏好，不默认连续轨迹/全量行为学习** | 统一永久保留或统一短TTL均不推荐；前者隐私风险，后者破坏恢复/审计 | 启用相关持久采集/删除产品前；不阻塞无行为采集的A1原型 |
| P04 最终实施启动 | 批准候选契约与首批G0任务并指定共享owner | **先批准G0小修+GPS/Draft spike+契约，再按检查点放开三条纵切** | 当前仍只文档；本轮没有自动进入业务编码 | 任何业务修改、多线工作区启动前 |

探索默认/杭州集中区域/预算可空/create_only不默认LLM/受控单用户/旧Trip保留/模块化单体已原则接受，不再作为待选。具体杭州测试区域由真实覆盖样本冻结，不需要再次争论是否先做全中国。

## 2. 技术问题由证据解决，不让负责人替工程猜实现

| ID | 尚缺证据 | 当前推荐/停止扩展条件 | 下一项验证与owner |
|---|---|---|---|
| T01 GPS可行性 | Key/签名/动态权限、walk/drive、回调隔离、StopIntent/进程死亡 | Instant仅持续受控导航；external不持久active；失败保留A1/A2但不放开A3 | V-NAV，ANDROID-NAV+NAV-A |
| T02 Draft公共核 | 无日期真实生成、最小规则提取等价、独立作业恢复取消 | relative day+adapter；禁止假日期/Trip与规则复制；formal差分解释不了则缩小提取 | V-DRAFT，FORMAL-C |
| T03 正式化授权/SQL | save/accept内部commit、mapping提交窗口、cancel/apply线性化、内容hash/证据新鲜度 | P1默认但guard必须验证；P2仅备选，不宣称当前全链原子 | V-PROMOTE，FORMAL-C+SCHEMA |
| T04 legacy Session迁移 | scope检索先行、SET NULL后行、旧客户端/删除/回滚 | 新global与legacy显式scope；不能只改FK；unknown owner不公开 | V-SESSION，CONTEXT-B+SCHEMA |
| T05 Provider与字段 | 图片/评论许可、实际配额/缓存、餐饮动态事实覆盖、酒店报价准入 | 保留unknown/estimate；未授权字段不提供；HotelQuote保持unavailable | DATA-A+QUALITY，真实授权与有界样本 |
| T06 集成新基线 | 指定小块合入后的正式回归/最新Companion保留/共同manifest | 现B-audit可复现，新B-integrated尚无；不得整包覆盖或继承旧测试数 | V-BASELINE，INTEGRATION+FORMAL |

这些不要求全部验证完才能写任何基础页面；各项只阻断相关路径，依赖DAG见路线图。

## 3. 关闭条件与批准记录

建议最终批准记录：本组文档hash/版本、P01/P02处理、P03后续政策owner、首批任务/owner与隔离基线、技术门禁未通过时的停留范围。没有新证据不升级VERIFIED/MEASURED结论。

代码事实、候选架构、未执行spike与产品批准在文档中已分开。GPS/草稿/正式化成功路径尚未验证；18项原则共识不是全部实现授权。本轮暂停在第三轮修订候选，等待最终批准。
