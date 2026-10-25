# RoamSync 收尾第五阶段（进行中）

当前产品结论仍NO-GO。沿用隔离工作树，分支codex/product-closeout-stage5-20261025，
起点为第四阶段证据提交6318c2d。正式HEAD仍ea3ba83，原六项tracked修改保留；未操作正式库或部署。
第四阶段唯一独立成绩4/20、完整0/5不变，已用题只作回归，不用开发重试刷新分数。

## 第一批：已经展示的修改候选不再被普通聊天隐藏

修改前真实失败：苏州pending60已在页面展示，选择器也收到了trip.displayed_revision；
但模型把追问归为direct，CompanionContextReader按itinerary need跳过已捕获候选，回答称看不到候选。
根因位于回答上下文交接，不是Revision不存在或需要新建Planner。

最小实现：CompanionContext独立携带来源已校验的displayed_revision，Reader从当前只读快照
复制它，不依赖聊天标签。无Trip/无有效快照时清空来路同名字段，不猜latest pending；
原trip/run/hash/version/status/完整review检查继续有效。正式值和候选前后值分开，读取不构成采用。
回执区分captured context与实际交给回答模型，不能据此宣称子目标完成。

修改文件：companion_contracts.py、companion_context.py、companion_provider.py、
assistant_capabilities.py、saved_trip_reads.py及test_stage5_saved_context.py；架构契约已更新。

修改前复现：context-before2在同一PG fixture执行提交6318c2d原Reader，候选字段丢失而失败。
首轮before/after因Windows asyncio策略导致fixture错误，保留；after4有两个测试stub漏填
information_need，保留为测试错误。最终context-after5共51项通过，包含真实PG、错误hash、
跨Trip、不可变复制、旧版本及读取通道回归，并区分快照取得与实际传递。Astra Medium限定复核通过。

真实模型验证使用第四阶段浏览器真实生成的苏州pending60对象，11表逐行复制到全新隔离库；
没有构造候选或修改原事实，这是历史真实对象回放，不是新黄金生成。原始模型请求/可见输出、
工具与前后10表状态见外部E:/Study/RoamSync-stage5-evidence-20261025：

- displayed-review-real-after/after2：回放脚本漏用了既有本地代理映射，选择阶段APIConnectionError，未进入回答，状态不变；均保留。
- displayed-review-real-after3：修正为与既有成功runtime相同的代理映射；真实选择器选择pending_changes，回答准确75→60、未采用，状态不变。
- displayed-review-real-after4-recorded-selection：重放原先失败的真实direct选择输出，回答provider仍实时调用，准确说明拙政园75→60、其他项目不变、待明确采用；状态不变。

最后一项的selector是记录回放，不能称全新真实selector成功；它专门验证原失败分支的修复。
两项成功回放的app hash在执行前后一致。各文件source_commit表示当时HEAD，实际未提交源码
由app_sha256绑定；产品提交后的相同hash记录另行保存，不把基线HEAD误称为修后代码。

## 继续目标

下一批为保存安排的统一位置引用与逐操作目标绑定，处理“第一天第一项增加15分钟”，
保留原句、稳定ID/版本、增量语义与其他项目，复用原grounding/Revision/Validator/Accept。
不得写进UI selected_activity_id混淆来源，也不得把多个操作目标扁平化后套同一增量。
随后仍需完整多子目标回答、跨城市候选交接、日期语法、真实浏览器全链和新的独立验收。
