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

## 第二批：已保存日程的通用地点照片补查

用户指出第四阶段adopted60-after-refresh截图无图。根因不是AI无法提供照片：
HandbookPhoto已有组件，但仅取11地点/4城市的审核图库，苏州不在库中，直接返回空白。
修改前新增组件回归photos-before为1失败/2通过，缺少已确认苏州地点的照片补查。

最小实现保留审核图库优先和原exact canonical/provider/坐标检查；新增只读
GET /api/v1/places/{canonical_id}/reference-images?provider_place_id=...。
服务端先核对稳定UUID与高德ID，再实时读取高德详情，只以provider确认的名称和城市查Tavily；
原始图片title+description必须同时包含完整地点名和城市，随后复用安全URL/图片投影。
不接受客户端地点名、任意图片URL或模型编造URL，不接入Planner/Accept，不写任何数据库。
没有扩建每个城市的专用景点名单。无图/失败保留原日程；未绑定地点、午餐留白不猜图。

搜索照片和已审核媒体分开：usage_basis=search_reference，卡片显示“地点参考照片”、
来源链接与未逐图现场核验说明；不声称逐图核验、当前景象或已取得转载许可。
图库请求6秒、参考图请求22秒有界；服务端总20秒、单次搜索不重试、并发4、
相同目标合并请求，成功缓存10分钟、失败30秒、上限128项。切换目标时旧结果不覆盖新卡片。

Astra Medium发现并修复三项问题：聊天菜品fallback可能误配门店、无效详情绕过负缓存、
图库请求卡住会阻塞补查。最终静态复核无剩余阻断契约发现，不是产品GO。
对应门店拒绝、空详情缓存、英文description配中文title和前端旧请求隔离均有回归。
review指出的前端provider mismatch测试已改为相同城市，避免城市检查遮蔽目标检查。

真实验证：E:/Study/RoamSync-stage5-evidence-20261025/runtime-photos。
从第四阶段真实浏览器保存态adopted60-after-refresh.json逐行复制11表到全新
roamsync_a2_public_stage5_photos_20261025_test（15435），API18105/Web3105。
这是照片显示回归；没有预置新候选，也不冒称新模型生成或完整黄金路径通过。
浏览器实际显示拙政园（苏州市政府图片URL）及狮子林（Tripadvisor图片URL），
刷新后仍显示，来源链接可见；正式10表及包含会话的11表都不变。
照片请求不调用大模型，真实工具为AMap+Tavily；API返回和原始图检索记录已保存。

保留失败：真实provider1两地无可用图（过滤只查中文description漏掉中文title）；
修复后provider2拙政园有图、狮子林该次仍unavailable。之后真实浏览器两地有图，
不删除或把前两次改记成功，也不把外部图片可用性宣传为保证。测试脚本首次误用未安装的
pytest-asyncio标记，after1八项测试调度失败；改用项目现有asyncio.run方式后通过。
最终后端照片/地点/保存候选定向107项通过，Web构建（含类型检查）通过。
Web默认并行全量272通过/1导航测试5000ms超时；单独复核该导航与照片7项通过，
默认并行失败原样保留。限制maxWorkers=2的全量273项/49文件通过；不修改导航断言或
扩大5000ms超时，不将工程复跑当成独立产品评分。本批不宣称完整冻结后端重验或新独立成绩。

## 继续目标

下一批为保存安排的统一位置引用与逐操作目标绑定，处理“第一天第一项增加15分钟”，
保留原句、稳定ID/版本、增量语义与其他项目，复用原grounding/Revision/Validator/Accept。
不得写进UI selected_activity_id混淆来源，也不得把多个操作目标扁平化后套同一增量。
随后仍需完整多子目标回答、跨城市候选交接、日期语法、真实浏览器全链和新的独立验收。
