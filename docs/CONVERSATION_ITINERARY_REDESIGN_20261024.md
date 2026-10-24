# AI 对话与“我的安排”重设计交付 — 2026-10-24

**结论：核心实现已提交，工程回归通过；产品验收 NO-GO，不部署。** 本轮没有修改、迁移或清理正式数据库，没有启动正式容器，没有 Obsidian 写入。工程通过、局部真实成功与全新会话质量分别记录。

## 版本、环境与源码身份

- 新开发 `BASE_SHA=89b81e8d6cf5561f2bbab1a9ac437aa9dde88fb9`，分支 `codex/conversation-itinerary-redesign-20261023`，隔离树 `E:/Study/RoamSync-reliability-a2-20261022`。这是受测产品提交，后续交付提交仅文档/公开证据；不是已发布版本。
- 正式目录 `E:/Study/RoamSync` 的 HEAD 仍为 `6b298caddb79125991bfc5183ddeefc09029f31c`；正式五个容器仍 exited。保留 README、Nginx、未跟踪文件、环境和用户数据；本轮不声称正式3000在线。旧部署镜像与新候选源码不相同，也未尝试替换。
- 历史统一基线 `f116ada6d6d46db7aeb48c29c8d5b45da379be00` 和未部署整合 `6a65ece3` 只作祖先证据；原始10月21日固化过程见 `ENGINEERING_A_AUDIT_20261022.md`，A2根因修复见 `ENGINEERING_A2_RELIABILITY_20261023.md`。
- 最终测试 `full-committed-4/run.json` 直接记录 HEAD=89b81e8、passed=true、source_unchanged_during_run=true；Git blob 与测试原始源码612个文件逐文件核对无真实差异，见外部 `committed-git-source-equivalence.json`。Windows CRLF与Git LF差异单列，真实差异不得当换行忽略。
- 后端原始源码清单聚合 SHA256：`b8e54e0da15d2c50d6d43a2f464383da8467479f08753231eeff1c627394929c`；LF聚合：`385f447fe60d37ba3d5c9cde88f4be375f94b64ecf00674f5e97f22c55080d26`。
- Web源码清单聚合：`a6dcb9f43e35f9c81668442bee859abe2f5dad1bae1a5b331df9a5f8fecbdbe8`。聚合算法为路径→SHA256映射排序后紧凑JSON的SHA256，完整映射在外部 `source-freeze-committed.json`；仓库精简摘要见 `evidence/conversation-itinerary-20261024/ENGINEERING_SUMMARY.json`。
- 最终隔离测试镜像：`sha256:cdd9a5c7fed3d1053b947050477b4347cb2e174c802f1ade8b6958eef528ba8b`。这是测试镜像，不是正式部署镜像。

外部证据根目录：`E:/Study/RoamSync-conversation-redesign-evidence-20261023/`。日志、合成会话快照与浏览器profile保留在外部；不把真实私有会话、环境密钥或数据库备份加入Git。产品提交只使用显式文件清单，未使用git add -A。

## 已实施的根因改造

1. **同源候选而非创建元数据。** 扩展现有 Draft/PreparedPlan 为严格v2；每项有稳定ref、类型、时长及来源，午餐/休息/留白有独立窗口。真实地点/路线在事务外准备，模型不能凭UUID授权。服务端从同一PreparedPlan派生简短图文摘要，完整时间轴放在“我的安排”。旧元数据卡明确尚无可核对日程。
2. **同一候选修改与明确采用。** generate/modify/adopt/discard使用同一typed command，局部修改由服务端合并未触及项；有效条件、主题、版本和展示hash绑定。自然保存与按钮保存走同一采用门；问题、假设、转述、撤回、只覆盖半个复合要求均不能提升为保存权限。复用原来源和极性函数，避免在下游重新解释广义intent。
3. **原子创建。** v2持久化独立执行模式，授权确认不创建壳Trip；外部证据刷新后，在一个事务内完成正式对象物化、原Validator、原Accept、窗口等价检查、草稿消费及会话收据。错误整体回滚，重复请求和并发恢复不重复创建。旧checkpoint模式保留；旧编辑/采用端点拒绝v2，不能协议降级。
4. **严格保留事实和限制。** 半点不能当整点；模型分配时间不能冒充用户固定时段；延长景点后分配午餐窗口可移动但保留一小时，用户明确固定窗口冲突则阻断。未核实硬条件、重复provider身份、未知地点、不可保存的optional身份/时间、每日覆盖及预算口径均诚实阻断，不删除字段换取ready。
5. **逐站真实照片。** canonical+provider+坐标关联，API正式Activity输出既有PlaceRef。审核宽窄巷子B001C7YCM4和CC0街景原片/变体，补齐图库；13张既有原片来源/作者/许可及26变体哈希复核。未采用用户参考图充当真实场所图片。完整材料见 `evidence/conversation-itinerary-20261024/MEDIA_AUDIT.md`。

主要文件：`backend/app/conversation_candidate/{commands,service,binding,presentation}.py`；`drafts/{contracts,timing}.py`；`draft_promotion/{contracts,preparation,atomic,service,materialize,guard}.py`；assistant capability/turn/routes与正式Activity DTO；Web `ConversationCandidate`、TravelAssistant、AssistantDecisions、HandbookJourney/HandbookPhotos、arrangementApi与既有repository映射。精确48文件变更可用 `git show --stat 89b81e8` 查看，没有新的数据库迁移。

## 十大工程问题与优先顺序

|顺序/级别|问题、来源|状态与处理顺序|
|---|---|---|
|1 P0（公网前）|用户身份、Trip与会话所有权隔离不足；已有技术债|仍开放。局部候选owner检查不代表系统租户隔离，公网前必须完整认证/归属矩阵验收。|
|2 P1|同意图多次路由/条件投影造成子任务丢失；旧架构，七项升级后更突出|v2候选操作局部统一；咨询/已有Trip读取仍不统一。B主线继续。|
|3 P1|真实模型输出不符合严格候选schema，导致正式创建前失败；新协议适配暴露|最后新会话返回顶层candidate_patches，extra_forbidden。不能extra=ignore或删字段隐藏失败。|
|4 P1|复合咨询漏答玩法、同日可行性；已有Agent质量债|真实地址正确仍不能算完成。需要可校验的任务覆盖和证据交接，不继续堆关键词。|
|5 P1|规划持锁跨网络/陈旧Worker写；已有可靠性债|A2已完成快照、事务外I/O、双CAS、claim/fencing/租约接管；最终回归覆盖。HTTP取消和全链恢复仍需持续验收。|
|6 P1|先创建壳Trip再失败、候选和正式状态不一致；旧流程与新交互冲突|本轮v2原子采用修复；旧协议显式保留，禁止旧新Worker混跑。|
|7 P1|疑问/假设保存、漏复合patch、否定地点变visit；本轮实现引入并独立审查发现|已修复，B公开红绿与正向控制保留。只证明所列边界，不声称任意语言全覆盖。|
|8 P1|高德/模型TLS和网络故障；外部依赖可靠性风险|真实SSLEOF/APIConnectionError与地图503均发生，失败保守且无正式写入；未实现全面熔断/全局预算优化，不声称稳定可用。|
|9 P2|已有行程读范围在发送、语义读取、Companion100/10活动投影间丢失；已有债|选中日/活动、历史决策理由覆盖不足仍开放，B已从新BASE隔离开发。|
|10 P2|展示图片身份、采用hash、旧新端点兼容和测试/源码身份漂移风险；新v2及历史基础设施交叉|本轮严格身份/hash/版本、原子门和最终源码核对已加强；浏览器绘制证据也须实际观察，不只naturalWidth。公网与长期观测不在此宣称解决。|

排序兼顾价值/风险/成本：1—4为发布门；5—7为本轮最高价值且可隔离回归的修复；8—9下一阶段中等成本稳定性/能力工作；大规模Agent重写、换框架、多层Planner及新功能暂缓。身份隔离若准备公网则优先于全部功能。

## 测试与前后对照（MEASURED）

|验证|最终结果|适用边界|
|---|---|---|
|精确89b81e8后端完整套件|主1792 + 专38，失败/跳过0|一次性tmpfs PG、无主机端口/生产卷；包括真实PG回滚、并发幂等及旧协议|
|主/专pytest时长|182.71s / 33.61s|wrapper为200.761s / 49.594s；不是业务时延|
|Web|47文件265测试；typecheck/build均exit0|同一Web源码冻结；已有React act警告未隐瞒|
|生产前端构建|1646模块11.96s；JS455.88KB gzip143.65KB|构建验证，不代表已部署|
|同源/授权/部分变更反例|B保留红绿及正向控制|禁止网络与DB合成探针；不是实际模型或真实SQL|
|真实已保存行程|候选→采用→F5与三个宽度|真实模型/AMap与独立合成库；不替代新鲜会话全链|

源码最终仅测试EOF空行清理后再次完整跑 `full-committed-4`，避免把清理前 `full-final-3` 冒称精确提交。早期source drift/失败/无效运行全部保留；不把重叠定向测试相加。

同输入改进可追溯：旧创建失败记录 `real-browser/candidate-real-{1,2}` 和 `candidate-sameinput-after-*`；在 `after-8` 首次得到两真实地点、午餐和路线的候选。原自然采用失败 `adopt-real-1` 对照 `adopt-real-2`，修复重复broad-intent拦截后走原Validator/Accept成功。B记录保存问题、跨句假设/转述/撤回、漏一半patch、否定/备选地点的红绿，见其独立报告。早期成功后的安全门继续变化，**不能将早期自然采用成功直接绑定成最终源码新会话通过**；最终SQL性质由精确提交回归证明。

没有业务全局性能对照。某次咨询7.609s、失败创建11.534s只是单次观察，不据此宣称90秒预算或整体延迟改善。A2锁释放前后证据证明并发正确性，不能替代性能分位数。原有备份独立恢复验证仍是历史证据，本轮未重新dump生产库；未来发布仍须重验备份恢复、迁移预检和兼容Worker切换，不能覆盖恢复新用户数据。

## 真实浏览器与产品质量

真实测试采用独立库 `roamsync_a2_public_redesign_20261024_test`、API18058/Web3058、共享测试PG15435；不连接生产15432。运行器Python3.14，Docker测试Python3.11；真实配置模型/地图服务，密钥仅进程内读取，未落入报告。浏览器为Edge Playwright；mock页面测试单列。

开发链实际完成：
- 创建前Trip/Day/Activity/Route/Run/Revision/Arrangement全0，Draft/Prepared存在；没有元数据阶段假保存。
- 成都11月9日10—18、两站步行、一小时午餐的候选含实际AMap1133m/16min。
- “人民公园多留半小时，宽窄巷子可以少逛一点”在同Draft增加版本，park120→150、street180→150，午餐60分钟保留并移为12:30—13:30。
- 明确采用成功后Trip1/Day1/Activity2/Route1/Run1/Revision1/Arrangement1。
- 最终源码已有Trip真实修改“宽窄巷子14:30开始，其余和午餐保持”，Worker给待采用PlanRevision；点击实际“采用11-09的调整”，F5后14:30—17:00、午餐12:30—13:30、park10—12:30。路线重算1121m/15min；正式Trip仍1，Run/Revision各2，未额外创建Trip。
- `real-responsive-painted` 1440/390/320无横溢出或pageerror，两站照片实际绘制。原 `real-responsive` 只测naturalWidth，全页截图屏幕外照片空白；保留原记录，补取证时逐站滚动、等待decode/两帧后截图，未修改产品CSS掩盖问题。
- `saved-trip-real-1` 是新浏览器根路径不恢复原sessionStorage，不是F5丢失Trip；实际Trip规范路径刷新保存成立。新标签会话恢复体验仍有边界。

**新鲜连续验收仍失败**：`fresh-chain`、`final-2`、`final-4`、`final-5`为4次有效失败；`final-3`是runner异常无效测量，不能作产品成功/失败。前两次暴露模型虚构每日边界/地点名称交接；第四次真实providerTLS/503；最后一次仍漏复合咨询且严格schema拒绝candidate_patches。均保留，不能只挑成功会话。

四门槛结论：新的未见20题16/20 **未测达标**；全新连续链 **失败**；公开同输入反例/对照 **已保留但范围有限**；统一工程回归及局部真实界面 **通过，不能补足前两门**。旧5/20、A2的2/20不改写成新成绩，也不读取私有保留题继续针对性调参。整体NO-GO。

## 独立审查、交接与开放工作

Astra Medium完成设计七边界与早期代码问题复核；最终全量Astra因用量限制未完成，不宣称最终独立架构批准。B独立候选窄审查报告从622f01e按显式路径接收，未覆盖A handoff。其最终4关键授权文件与89b81e8等价；15文件核对14相等，**preparation.py真实不同**，all_match=false原记录保留。B旧合成prepare结果不能绑定最终准备层；A精确最终全回归是另一份证据。详见 `AGENT_B3_CANDIDATE_BOUNDARY_REVIEW_20261024.md` 和其freeze-source-equivalence文件。

B已获BASE并在独立树继续读取范围/覆盖根因，不与A文档收尾交叉改代码；C收到基线、NO-GO和不重复已用保留题的边界。具备接收B/C提交并复核的工程条件，**不具备发布条件**。未来集成需要新SHA、源/像一致性、完整工程回归、新鲜连续对话、独立保留题和真实故障恢复重新统一验收。

开放限制包括公网身份隔离、复合读任务/严格模型JSON、provider故障可用性、已保存标量时长修改仍走replan语义、硬事实验证、HTTP取消与统一观测、支持范围外预算/optional/每日时间覆盖。不能为提高通过数删字段、放宽授权/Validator/版本/Accept，也不继续扩展大型新功能。

## 截图索引

以下均为外部保留文件，真实截图与模拟图明确分开：
- 候选：`real-browser/candidate-sameinput-after-8.png`；修改：`modify-real-1.png`；采用：`adopt-real-2.png`。
- 已保存真实修改与刷新：`real-browser/saved-revision-accepted-final-1-refreshed.png`。
- 最终桌面/手机真实时间轴：`real-responsive-painted/saved-1440.png`、`saved-390.png`、`saved-320.png`。
- 新鲜失败：各 `fresh-chain*` 目录。模拟UI：`C:/Users/Dapper/AppData/Local/Temp/roamsync-candidate-ui-20261024/`，不得称真实模型通过。

收尾运行核对：18058/3058已无监听，本次API/Web/Worker进程均已退出；共享测试PG15435仍运行并保留数据。未重启正式3000；重新预览须用隔离启动器，不把历史截图当当前在线页面。
