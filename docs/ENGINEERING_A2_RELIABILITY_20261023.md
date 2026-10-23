# RoamSync A2 工程可靠性与集成验收

2026-10-23。状态：工程测量冻结，产品 NO-GO，未部署。最终受测产品源码为
`85d0bd5915a7d7168bf606b7f520fbae0ad6f237`；后续仅接收报告/证据，不改变产品。
完整后端回归与构建文件核验通过，但实际创建未产候选；C一次封存测量严格可用2/20，
有效用例仍有1个关键无证据保证。四项统一门槛未全部通过，最终结论禁止发布。

## 版本与保全

正式目录 E:/Study/RoamSync，入口3000，正式HEAD仍为
`6b298caddb79125991bfc5183ddeefc09029f31c`。统一产品基线
`BASE_SHA=f116ada6d6d46db7aeb48c29c8d5b45da379be00`。
上一轮三线集成`6a65ece3acc3ea9a32087c11a2cbbe05173862dc`是本轮共同起点，未部署。
A2独立树 E:/Study/RoamSync-reliability-a2-20261022，分支codex/reliability-a2-20261022。

正式基线来源、3133文件清单/备份、运行源码224文件、364产品/配方文件LF汇总
`772a651705b23a8cb1e49d6382fdc269787a76432877dffd7231fe54434b7259`
及10月21日功能祖先证明见ENGINEERING_A_AUDIT_20261022.md。
历史219/222条manifest不完整的局限保留，不能改写为完整发布证明。
本轮无reset/clean、正式文件覆盖、数据库写入或迁移；README、Nginx、未跟踪成果、密钥与用户数据保留。
本轮首次再次只读核对原清单3133文件：无变化，ignored .env哈希相同；四个正式容器ID、镜像、启动时间相同且运行。
初次证据E:/Study/RoamSync-a2-evidence-20261022/official-preservation-20261023.json；Git内摘要为后续中断后的最新状态。
该次核验未连接数据库，不能冒称再次比较了全部表内容。
后续16:51左右出现运行环境中断：正式四容器均Exited255，测试PG也停止；B独立观察同现象。
A未执行停止或启动正式容器。中断后复核仍3133文件/ignored env相同、容器ID与镜像相同，running=false；
不能再宣称当前正式3000在线。启动测试容器的动作被自动审批策略拒绝，reason仅blocked by policy，未执行、不绕过。
因此后续公开浏览器连接拒绝/DB读取超时属基础设施无效，保留失败，不能当产品成败或跳过后宣称通过。

## 十大问题及归属

| 排名 | 严重度与根因 | 新旧归属 | 本轮状态 |
|---|---|---|---|
| 1 | P0 公网身份、Trip、会话所有权未统一强制隔离 | 既有单owner架构；近期独立打算沿用此边界 | 开放，公网发布前置；不冒改schema |
| 2 | P1 多组件重复解释同一意图，复合任务丢失，条件与授权原文不同步 | 既有路由/Planner债，10月21日语义/记忆扩展放大 | B交接修复已冻结；真实复合续接仍丢目标，尚未根治；旧5/20不是新验收 |
| 3 | P1 创建、候选路线、Graph研究持有数据库事务跨网络请求 | 既有写保护实现；新增研究扩大持锁窗口 | A已拆短事务、外部I/O、重锁双版本CAS |
| 4 | P1 Worker同host身份重复、旧执行覆盖新owner、checkpoint污染 | 既有租约/恢复债 | A已唯一claim、写fencing、独立checkpoint、条件心跳/清理及故障退避 |
| 5 | P1 澄清API无claim；领取后退出丢答案；重复体验操作擦除checkpoint元数据 | 无claim属既有债；指针覆盖为A新attempt设计暴露的集成缺口；旧第二轮文本格式是B新恢复路径暴露的兼容债 | 原子收据/claim、严格旧checkpoint迁移及typed409修复；A67、B84项重叠边界验证通过 |
| 6 | P1 测试/迁移可误用真实库、源码与回归/镜像缺绑定 | 长期债；新增未跟踪夹具曾破坏复现 | 上轮A门禁/随机tmpfs库/源码哈希/产物核验继续使用 |
| 7 | P1 初创研究/地点身份交接不完整；用户明确地址仍不能恢复已查真实POI | 既有研究前置设计；新窄桥严格等值不能消除规范名差异 | 最终公开链实测planner_requested_place_unresolved，0 Revision/Activity；不得放宽身份校验凑通过 |
| 8 | P1 条件存在session memory、requirements、context等多个投影 | 10月21日新增或放大，requirements更早 | 日期/预算/撤销改善；父亲步行要求、单次地址城市部分落personal范围，生命周期正确性仍开放 |
| 9 | P2 90秒预算内多次模型/检索、同步HTTP线程取消不彻底 | 既有网络/编排债 | 陈旧写入已被fencing阻断；在途传输取消/调用负载压测开放 |
| 10 | P2 大模块与特殊规则累积，观测不足以证明实际旅游质量 | 历史修补长期积累 | 不新增第二Planner；保留旧/新原文、调用轨迹、阶段耗时与持久状态；持续简化开放 |

严重度按本轮本地使用与未来公网边界区分。测试库门禁与构建绑定虽已修复，仍需最终候选重跑，不把历史通过作为现版本证明。

## 实施与成本排序

立即处理正确性：规划写前后事实一致、Worker失联/并发写保护、澄清恢复及集成出处。
稳定性改善：共享地图证据缓存采用独立短事务；缓存估算仍需显式允许，不能误充真实地图证据。
暂缓：全服务拆分、第二决策模型、新状态库；公网多租户隔离为独立P0工程，不能归为可忽略优化。

A主要提交：3a45fe2创建快照与双CAS；4e21b8c已准备意图跳过旧路由；
81cb57d候选路线网络外移；4aa8c65 Graph语义/网页/研究/初始POI/路线短事务；
4423e03 Worker租约与checkpoint；8dd7d23澄清claim/409、体验trigger合并及prepared envelope。
7c4b498将澄清输入与claim原子保存，覆盖领取后和规划中退出；B2809335恢复marker服务已接收为ce8000c，Graph/引用/授权d5be594接收为1ff2587，地点身份保守桥e5dd243接收为8872972。无新数据库迁移。细节见AGENT_ARCHITECTURE.md和原批准设计。

| 优先与任务 | 价值 | 风险/成本 | 决定 |
|---|---|---|---|
| 立即：规划短事务及双版本CAS | 解除网络耗时期间业务锁，拒绝过期事实落库 | 中/中高，涉及三条规划路径 | 已实施；同输入锁反例验证 |
| 立即：Worker唯一claim与写fencing | 防失联接管后的陈旧写和checkpoint串线 | 中高/中高，不能混跑旧Worker | 已实施；真实PG接管至Accept验证 |
| 立即：澄清收据与兼容恢复 | 防已提交答案丢失及重试反复追加 | 中/中；保持原授权与检查点绑定 | 已实施，无法安全迁移明确409 |
| 公网上线P0：身份与所有权隔离 | 阻止跨用户Trip/会话访问 | 高/高，独立schema/API迁移 | 开放，公网前必须完成 |
| 稳定性P1：已选POI可验证交接 | 解除真实创建阻塞，避免反复理解名称 | 中/中，B主责 | 下一阶段主线，禁止再堆地址正则 |
| 暂缓：服务拆分/新Agent/新状态库 | 当前无直接已证收益 | 高/高 | 不实施 |

根因边界：一个已验证operation与prepared draft在规划路径复用，不能声称全系统已经只解释一次。
Assistant/Companion/Research仍有信息需求/参数投影，session memory与requirements仍并存；地点桥
仍有约130行保守词法规则，模型建议也未完整绑定场所事实。应逐条迁移同一操作和证据结构，
不通过增加第二Planner、吞异常或放宽Validator/Accept修复。

架构细审沿用上一轮报告第3/4节的调用链与文件定位，并核对本轮边界：Assistant保存当前意图、
Companion读取事实、Research发现候选、Planning生成待审Revision、Execution保护已确认执行态。
新prepared路径跳过旧goal router，但旧客户端/未迁移入口仍有旧路由，不能删掉兼容层后宣称统一。
Execution冻结/当前/导航目标保护、客户端版本检查、Validator及Accept仍保留；本轮未绕过。
SSE仅在工作态轮询，已有keepalive/断开cancel；Worker新故障退避上限30秒，不盲目删除必要轮询。

90秒咨询预算的既有68份轨迹：总中位16.779s、最大54.030s，selection中位3.832s、answer11.446s、
companion15.323s、images2.751s；阶段嵌套且样本不同不可相加，不是无偏生产分布。
图片检索有16秒上界/一次尝试，模型选择、网页选择与最终回答仍可能重复消耗预算。
高德不可用或身份不明时不能用估算冒充；Tavily初创发现仍可能fail closed；模型无法形成合法提案
不落库；图片失败保留文本。此次改善事务占用和接管正确性，没有完成外部传输取消/负载性能认证。
consultation有allowlisted execution_summary，Run有progress/error_code，实际初创失败可追踪；
Worker日志仍偏异常类，跨API/Worker/SSE统一关联与阶段分布面板、消息JSON增长/归档仍开放。

安全边界：外部网页/工具输出只作为事实输入，不能授权操作，prepared envelope必须由服务端创建并
绑定原句/Trip/页面目标/版本；畸形或过期marker拒绝。提示注入对生成内容的影响没有被证明完全消除。
认证主要是本机/隔离模式的token/origin边界，Trip与会话查询缺统一owner作用域，不能当作多租户隔离。
测试夹具/迁移均显式测试DSN并拒绝正式库；公开验收仅synthetic owner新库，正式会话没有进入Git。

主要文件：planning_preparation.py、planning_run_repository.py、planning_graph.py、
planning_graph_runtime.py、planning_claim.py、agent_worker.py、planning_progress.py、
maps_service.py、candidate_route_service.py、candidate_decisions.py、destination_research.py、
initial_places_service.py、experience_replanning_service.py与对应事务/所有权反例。
代码清单以`git diff --name-only 6a65ece3..HEAD`为准，包含接收B/C的独立提交。

## 同输入对照与测试

原始日志/JUnit在Git外E:/Study/RoamSync-a2-evidence-20261022/，摘要在docs/evidence/reliability-a2-20261022/。
所有计数均为各套重叠测试，不可相加宣称新增覆盖。

| 对照 | 旧版实测 | 新版实测 | 可证明范围 |
|---|---|---|---|
| 模型等待锁 | 同输入3项55P03 | 创建套120通过 | NOWAIT取得Trip锁且无idle transaction；失败/取消无残留；Trip/偏好变化拒绝 |
| 路线等待锁 | 同输入4项55P03 | 路线套94通过 | 路线网络期间无Trip/Run锁，版本/取消复核与并发候选安全 |
| Graph外部阶段 | 语义/事实/研究/POI四处保留事务 | Graph套90通过 | 相同provider/Event探针验证事务边界 |
| Worker接管 | 七项旧身份/陈旧写反例失败 | Worker套81通过 | 旧实例暂停→新实例真实PGcheckpoint产候选→旧写拒绝→新候选Accept成功 |
| 复核缺口 | 丢指针、API无claim、prepared丢失 | 74通过 | 重复提交排斥、租约丢失和真实checkpoint恢复 |
| 澄清故障接管 | 领取后/规划中退出，两项丢答案 | 46通过 | 收据与claim同事务、接管保留答案、恢复计数；语义闭环另验 |
| 首次整合全量 | 基线1469+25 | ae52693主1592+专25 | source_unchanged=true；对应镜像354ed15f…，不含后续复核修复 |
| A修复及marker服务全量 | — | ce8000c主1633+专25通过 | combined-full-3，source_unchanged=true |
| B完整组集成全量 | — | 1ff2587主1693通过/1失败，专25通过 | combined-full-4，源码不变；既有flexible未知时间/optional被新授权guard拒绝，B修复中，不计通过 |
| 最终固定源码全量 | full-4实际1失败 | 85d0bd5主1713+专25全部通过、零跳过 | combined-full-5，源码不变；主阶段217.100s、专阶段36.373s；pytest199.396/21.375s |
| 旧澄清不可迁移 | legacy-runtime-red实际HTTP失败 | legacy-runtime-green 67通过 | 首次/重复typed409均保留原问题/答案，不能覆盖接管者租约；B另独立PG84通过 |
| Web | 本轮基线239 | 集成243，typecheck/build通过 | 生产构建31.93秒；不代替真实浏览器或产品质量 |

这些指标证明锁等待和故障写入根因改善，没有证据声称真实模型回答更快。
combined-full-2主1596+专25虽测试通过，但运行中源码变化，认证passed=false，原始失败保留。
1ff2587生产配方仅构建API镜像，network=none临时cat/hash核对230文件均匹配；源码LF manifest汇总
`aae9a306a9cb753266dfc74905ee569952786b8e8caa3e94cf17d0afcf1ca6a1`。
镜像`sha256:3ed39e9e91aa9a72bb12bd0bbe950be363b52c7ce907888cb96d9f3385aae0b1`。
初稿自写取证脚本错误归一化二进制导致17项误报，修正按构建规则后0不匹配；失败记录保留，不修改产品配方掩盖。
这不是API运行/正式部署证明，未启动镜像服务、迁移或连接数据库。
90秒咨询与完整规划deadline不同；不以合成provider等待或pytest耗时冒充实际延迟基准。
实际咨询仍可能有过度概括/重复研究和证据不一致，已保留公开浏览器原文，不以测试数掩盖。

最终85d0生产目标显式`docker build --target production`，API镜像
`sha256:7ffa553babf554178f93aa1b38e3ead1de317c9b686a7a641debbdfc84e6b9c3`，
230受管文件全部匹配；源码LF manifest汇总
`584d075f687036f77023f9450ee8d600efcfe9cd4262e03539698a8dbe243a68`。
Web镜像`sha256:9683055cce65ce6e9a5d3a9152f95a57f85d1149e028d238dc4d78aa23708052`，
143输入/3产物匹配；Web源码未变化，243测试/type/build对应同一输入。
测试镜像为90734457734c…，包含app/tests/配方逐文件清单摘要
`c79ae375d4aa3ac01a8523275cc25712aef48596110fe9d49d898a1bfb33a4bb`。
`candidate-build-only-85d0bd5.json`明确scope=build_artifacts_only、running=false；
补充`candidate-all-build-only-85d0bd5.json`也核验Worker使用同一最终API镜像，三者全部匹配。
这些停止的network=none取证容器从未启动应用、迁移或连接数据库，不能冒充运行证明。
曾漏传target构建了test阶段，未用于产物认证；随后显式production重建。旧1ff API对新源码的核验
按预期报漂移，原失败保留。未替换正式tag、容器或部署。

## 复现、备份与回滚边界

在独立树运行`python scripts/run-isolated-tests.py --output <不存在的输出目录>`：随机Compose项目、
无端口/tmpfs测试PG，不读取正式.env，结束只清理本次资源，run.json绑定SHA/逐文件散列。
镜像用显式production target构建，停止的取证容器只配合
`python scripts/verify-release.py --api <取证API> --web <取证Web> --no-worker --allow-stopped --output <新JSON>`；
不能把该命令通过当作Worker运行或生产ready。

上一轮`scripts/verify-backup.py --dump <私有dump> --expected <私有指纹> --output <新JSON>`已在
独立network=none/tmpfs PG实测32表全部一致，23.032s；备份、内容与会话不进Git。
本轮未再次连接正式数据库制作新备份，因正式PG当前停止，也未冒称拿到了新内容指纹。
本轮无新增migration，但仍需下一次发布前重新备份/恢复校验、固定镜像与schema版本、
停旧Worker后启新Worker并统一冒烟。回滚应切回经过验证的整套兼容镜像，不能混跑租约协议；
已产生新用户写入后，不能盲目恢复旧dump覆盖。数据库恢复/迁移回退必须单独评审。
部署未执行；这里只交付可重复检查与下一次发布需要的条件，不授权自动发布。

最终444个受测文件再次逐字节核对，全部一致，Git产品diff(backend/web/scripts/compose.test.yaml)
对85d0为空；证据final-evidence-validation.json、final-tested-source-manifest.json。
完整提交/文件变化清单在final-change-inventory.json。B最终证据47c11c7按9文件allowlist导入，
保留A共享架构/交接；另接独立review3fd381c。无.env、密钥、dump或私人会话纳入提交。
窄密钥模式扫描无命中，仅作补充检查，不冒称完整隐私审计。

## 接收与统一门槛

B helper/operation/条件/来源/日期/预算提交已接收至133c680（A ae52693），
C路线连续性c912d965、空白日预览351cfd04已接收；B2809335/e5dd243/d5be594已接收。
B optional兼容96ac7d5接收为7f90547，A93项回归通过；原既有测试不改、未知时间与optional保留，不启动Graph。
旧第二轮checkpoint严格迁移523bbd7接收为442d33c，A85d0bd5完成typed409/恢复中断，已过工程测量门。
原A复核子代理遇用量上限未完成此提交复核，未伪称已批准；B另安排Astra独立只读复核并批准窄修，
再以真实PG84项验证。该窄审查不是产品发布批准。
冲突逐块审查，不整分支覆盖A事务或C产品改动。

独占公开浏览器库roamsync_a2_public_a20261023_test，PG15433测试服务内新库；
API18047/Web3047均loopback。环境只从正式env只读加载Provider配置到内存，不复制密钥进Git。
已从空库迁移/checkpoint初始化；Edge/Playwright（Browser插件缺席）记录1440/390/320截图、DOM、请求、SSE、异常。
初始页面与公开咨询/检索前两轮已执行；它们测的是冻结前版本，不能充当最终完整链通过。
后续补充交通只回泛化确认，创建轮显示回答未完成，API记录tool_failure；失败保留，不伪称创建成功。
取证局限：首轮/第三轮response.body为浏览器读取失败，只有第二轮SSE完整；不得称全部SSE齐全。
脚本已补独立fetch clone流收集与完成等待、console资源位置；后续运行再验证。截图地图占位不当作ready证明。
独立C审查定位跨子任务source_id=poi_1碰撞造成错源及回答矛盾，已交B；A不并行扩改Agent模块。
1ff2587同输入第二轮浏览器已验证真实字段[1]/[2]及来源汇总，无兄弟地点否认，但逛法/同天判断仍不完整；
首轮仍有无来源体验/耗时泛化。新版首、第二轮fetch clone均done，原SSE分别10140/25802字符。
B固定源码公开行动链同样失败（initial_candidate_not_ready，0Revision/0Activity），未用合成候选替代；
这组公开题结果不是密封20题，不能作为未见评估分数。
环境恢复采用不同安全路径：B确认15435已运行synthetic PG可承载独占新库。A仅创建全新
roamsync_a2_public_final20261023_test，完成迁移/checkpoint初始化，准备18048/3048从空库重放。
不启动被拒绝容器、不读写B库或正式库；原基础设施失败记录不覆盖。后续C保留题也必须另独占库。
正式容器ID/镜像未变，但后续环境中断已停止；本轮未恢复或部署正式服务。

最终公开重放使用15435新库、API18048/Web3048，产品85d0固定，配置指纹
`3cc0d7971519c1add80330b01b514ec5950a47fb9d5e9be65a4f159a3e39e398`；
glm-5.3-flash/high，timeout90s、retry0、max_output_tokens20000、max_candidates40。
浏览器运行API/Worker是Windows虚拟环境转发的Python3.14，工程镜像测试/生产配方是Linux Python3.11；
两者源码/Provider配置绑定已核对，但不是操作系统/依赖运行时完全等价证明。生产配方只构建未启动。
首次加载因测试PG刚恢复超时，未发送任何题，按基础设施无效保留。之后同一公开输入真实执行：
咨询→两处地址与独立[1]/[2]→“步行即可”续接丢目标→创建提案→点击确认→Run失败。
确认前五类正式表均0；确认后Trip1/Day1/Run1，Revision/Activity/Route/Arrangement仍0，
error_code=planner_requested_place_unresolved。没有实际候选可Accept，后续修改/503/409全链未执行，
不能拿合成候选成功替代。刷新根路径回自由聊，访问Trip页可见保留的空日和真实失败原因；
“采用并保存这份安排”实际只确认创建并开始规划，文案存在误导。
最终8份浏览器记录含1无效、4完整send SSE、确认/刷新/Trip页，1440/390/320无横溢出、无pageerror；
已人工查看320截图，真实失败可见。原文、网络与截图在
E:/Study/RoamSync-a2-public-final-evidence-20261023/，Git摘要public-final-browser-summary.json含逐文件哈希。
这说明故障可观察、无未审查活动入库，不能说明旅行协助可用。
取证后按精确PID+启动时间+父子进程关系关闭A本次API/Worker/Web，18048/3048均无监听；
未停止共享15435 PG、B/C进程或删除测试数据。停止的镜像取证容器和外置记录保留。

B公开开发16题在d5与最终整合源码分别重复测量，基本可用均7/16（旧版2/16）；
最终采样仍2轮关键无证据15分钟保证（d5采样1轮），没有稳定安全改善，不挑较好采样。
最终公开16耗时均值11.095s/中位5.385s；旧公开样本均值16.961s/中位12.663s，
不同采样/负载不受控，不外推模型整体提速。B完整报告另见AGENT_QUALITY_B2_DELIVERY_20261023.md。
最终只读复核另发现内部引用未完全同步：公开raw的顶层source_id为task_2_poi_1，
decision_support.reference_source_id仍为poi_1。可见正文编号修复不代表所有内部引用一致。
同一raw还显示父亲步行要求及单次扬州地址查询城市部分标为personal；跨旅行实际后果未测，
不能将条件记住等同于生命周期范围正确。这两项保持OPEN，不修改冻结源码或挑样本掩盖。

工程通过后允许C一次封存测量。初次初始化期间A接收B的docs-only证据移动HEAD，
C精确SHA门拒绝ready，未读取/调用任何题；保留失败库，改用精确85d0独立树与新库，
避免文档提交影响测量。题目没有被重采样或用于开发。

## C一次独立测量与最终决定

C公开报告提交a4532b266c36de13e90820c1588d76ab85dde19d，完整公开说明见
PRODUCT_ACCEPTANCE_C2_MEASUREMENT_20261023.md。A仅导入报告/聚合/严格评分附录，
核验summary SHA256=77ccbe40079d6cbe5f20f8a263ccd64fd65d0bd689519cfbb5455bd35d91f448；
公开manifest-v2 SHA256=1340340482318a04963d39ab301555a0a0f5a8f268a9c0395c413ea8e9624648。
私有题面、必要观察、回答、带题截图和数据库行未读取/导入；c2-import-verification.json记录边界。

| 一次测量结果 | 数量与边界 |
|---|---|
| 原预设基本观察全部满足 | 3/20，其中1例另有critical；不改原评分 |
| 严格可用：全部观察且零critical | 2/20；有效样本中2/19，未达到16/20 |
| 产品失败 | 16；泛化澄清、复合目标遗漏、文字表不形成候选、已有行程读取失败、选中修改ValueError |
| 取证无效 | 1；地图frame触发浏览器初始化脚本重新设置话题ID，多轮上下文不能归因产品；未重跑 |
| 有效用例critical | 1；无配料来源却断言多种食品符合明确忌口 |
| 无效用例另观察保证 | 1；不混入有效critical数量，不计通过 |

固定85d0独立树前后clean、实际摘要54e4593da42c8defcc6103b8f228edb9df84c07e551524da09a50a5d42b019c0；
与A字节摘要仅6文件EOL不同，全部受跟踪产品文件归一换行等价；配置3cc…前后相同。
20独立会话、23/23原文轮次及完整SSE；2026-10-23 22:07:08—22:17:02（北京时间）。
每轮中位9.737s、最大56.297s，不与不同题集旧5/20直接计算提升或下降。
C为不同开发线代理出题/评分，不是外部人类盲测；题集现已使用，后续不得再称未见集。
五组合成已有日程用于修改测试，时间/锁定/留白为夹具，真实地点来自高德；不是AI初创成功。
五类正式表逐轮均无变化，Run/Revision0，因此只证明此样本无未授权写入，不能证明新版
Validator/Accept/503/409已完整验收。1440及3例390/320无横溢出/pageerror，不能代替业务可用。
C补充收尾报告355534f：22:34:35核验API/Worker/Web已退出，18046/3046无监听，
退出原因未确定，C没有执行stop；15435不动。164份原证据逐个hash无缺失/改变，
固定树和测试库保留。资源收据c2-resource-closeout.json另存，不覆盖测量manifest或分数。

最终取舍：本轮A三项工程根因已实施、B/C已整合并完成测量；不继续对这套保留题调参修补。
下一轮B优先修复已核实POI/现有日程到同一operation的交接、复合任务完成与硬条件事实门；
A用公开反例诊断修改工具失败及并发/版本边界，C校正生成/采用状态文案并验实际流程。
若计划公网，统一身份/Trip/会话所有权P0必须排在发布前。任何新代码都需重新冻结、回归及新题评估。

| 门槛 | 状态 |
|---|---|
| C封存未见20题，≥16且零关键无证据保证 | 失败：严格2/20，有效critical1；无效1未重跑 |
| 最终真实完整咨询→检索→创建→采用→修改→刷新→503/409恢复 | 未通过；最终真实创建0候选，不能到采用/修改 |
| 相同输入前后原文、状态、耗时对照 | 工程反例和最终公开原文/状态具备；完整产品链仍失败 |
| 最终统一源码回归/产物及浏览器 | 工程1713+25/Web243/类型/构建/文件绑定通过；浏览器真实产品链未通过 |

具备继续接收B/C并审查集成的基础，不具备发布条件。未经统一验收，不部署任何单分支；正式数据库不修改、不清理。
