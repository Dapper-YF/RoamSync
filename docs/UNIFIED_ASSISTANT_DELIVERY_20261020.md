# RoamSync 正式前端助手整合与体验修正

日期：2026-10-20。独立工作树：`E:/Study/RoamSync-unified-assistant-20261020`。
分支：`codex/unified-assistant-experience-20261020`。
实现提交：`27db70f`；图片收敛修正：`9540436`；共同基线：`1df46af`。

## 判定与集成边界

VERIFIED：目标 Discovery 前端上的同一浏览器、同一 Trip 完整真实链通过，真实搜索配图通过。
本轮有限范围为 GO / READY FOR INTEGRATION；含义是可以进行正式集成，不代表发布完成。
正式源仍为 `E:/Study/RoamSync`、HEAD `25a62cb`；未合并、未部署、未执行生产迁移。
正式源现有 README.md、web/nginx.conf 及未跟踪成果保留。两份已修改文件的 SHA256 与调查开始时一致。
集成预检：1856 个正式源未跟踪文件与本轮候选新增文件交集为零；两份本地已修改文件也无改动交集。
确切文件清单见 `docs/evidence/unified-assistant/changed-source-files.txt`。

主仓库尚未包含 1df46af 及其依赖。正式集成应保留本分支从该基线继承的历史，不能只取本轮两个提交。
迁移 0037 属于已有基线；本轮没有新表、迁移、Agent 工作流或 Android 修改。生产发布另行决定。

## 源码与页面关系

VERIFIED：3000 的 `roamsync-web` Compose 标签指向正式源；Web Dockerfile 构建
`src/main.tsx → DiscoveryApp`。原 3016 的 `vite.isolated.config.ts` 同样使用正式源，代理到
18004，并非另一套产品源码。3019 的 `vite.natural.config.ts` 代理到 18019；1df46af 在
DiscoveryApp 中把首页及抽屉接成 NaturalAssistant，这才引入了重复助手和固定双栏。

本轮继续使用 DiscoveryApp 的视觉框架，首页及 `/assistant` 复用原 TravelAssistant。
导航为 AI助手、我的安排、探索、收藏；`/arrangements` 兼容跳转 `/trips`，详情同理。
NaturalAssistant 原文件和测试保留，但没有面向用户的独立入口。地图、探索、收藏可以直接使用。
隔离预览为 3020 → API 18020；正式 3000 不变。

## 统一结果与会话

TravelAssistantProvider 是首页与抽屉共同的会话所有者，继续使用原 SSE、会话恢复、错误重试、
输入法处理、滚动、地点卡片和上下文工具。global/Trip 作用域隔离；采用创建建议后沿用同一会话。
迟到的旧作用域消息或安排读取不能覆盖新 Trip；明确进入自由对话后不会被当前路径强行重新绑定。

ArrangementExtras 只维护编辑表单，不另存一份正式安排；它复用既有安排 API。
JourneyPage 保留原旅程、活动及候选展示。页面写入后刷新 Provider；对话修改后刷新同一结果，
再使原旅程视图更新。改期采用仍是同一 Trip，必须显式重读新日期和新版本；已建立失败/通过回归。
简单编辑、排时间、路线只读、重要候选 Accept 仍使用原受控接口和版本保护。
旧版本错误提示刷新核对，不盲目重试；候选过期时前端禁用采用，后端仍最终裁决。

## 消息与展示规则

没有重建消息协议。原 SSE 事件继续使用；既有 `read_tools` 增加可选 `web_search`：
status/provider/queried_at、sources、images，以及“检索参考而非已核实事实”的内部语义。
images 只有原始 URL、检索描述、原图链接和主题。`pending_action` 的灵活安排字段补齐 Web 类型。

- 通用知识分类及“本轮未核验”的内部说明默认不渲染；不是把旧说明改名为 thinking。
- 仅显示系统实际产生的公开分析摘要，折叠为“思考摘要”；处理中有真实状态反馈。
  不展示模型私有推理，也不为普通回答捏造思考记录。真实参考资料保留轻量折叠入口。
- 缓冲原始 SSE 片段：优先在至少 24 字符且已有标点时刷新，96 字符上限，160ms 延迟上限，
  结束时 flush、重置时取消。保留原文，不插入换行伪装分句，不做逐字动画。
- 普通文本支持安全的段落及加粗，不执行模型 HTML 或模型自行编造的图片 URL。

## 真实检索与图片

实际调查发现普通 Companion 原先没有调用 Tavily；Planner 的搜索能力不能直接冒充本轮检索。
本轮复用原 search_tavily，在明确要求联网搜索时进行有界只读查询，并请求图片描述。
只在当前轮有真实来源、主题适合图片、图片描述/文件名对应主题且 URL 安全时返回，最多 3 张。
明确请求的菜品可使用标明“参考图”的照片；同一道菜的参考图只留一张，不冒称拍摄于目标城市。
场馆图片必须匹配完整场馆名称，不用同城其他场馆替代。正文未提到相应主题则不渲染。
图片放在回答第一段后，紧凑图卡、可看原图；加载失败直接隐藏。无占位图、生成图或跨轮随机配图。

检索片段仍是不可信参考材料，不进入 KnowledgeEvidence，不充当营业、票价、预约的已核实事实，
不能授权修改安排。没有新增媒体仓库、下载代理或图片社区；原图链接不代表版权许可证明。

## 验证与证据

MEASURED，证据位于 `docs/evidence/unified-assistant/`：
原始浏览器 JSON、早期诊断记录、ESLint 完整输出及失败图片测试 XML 按原文件名封存在
`raw-records.zip`，未改写其内容；最终测试 XML、摘要和精选截图可直接读取。

| 检查 | 结果 |
| --- | --- |
| Web 全量 | 206 passed，web-final.json |
| TypeScript / Vite build | 通过，27db70f；图片后续修正不改 Web |
| Windows PostgreSQL 后端全量 | 1349 passed、1 skipped，windows-final.xml |
| Linux PostgreSQL 后端全量 | 1349 passed、1 skipped，linux-final.xml |
| 收藏并发独立库补验 | 1 passed，favorites-postgresql.xml |
| 搜索/SSE/幂等专项 | 21 passed，search-stream-final.xml |
| 同 Trip 改期回归 | 修复前 1 failed；修复后 6 passed，same-trip-preview-{red,green}.json |
| 图片同类去重后续修正 | 失败先行，Windows/Linux 各 14 passed，image-reference-* |
| 全仓 ESLint | 41 errors、27 warnings，错误均在本轮未修改文件；没有冒称全仓 lint 通过 |
| 修改的产品实现文件 ESLint | 0 errors，既有 hooks / Fast Refresh warnings 保留 |

两平台全量在 27db70f 完成；9540436 只收紧图片投影，另有专项与真实配图复验。
独立 Astra Medium 只读 review 找出的作用域竞态、页面/对话失效通知、改期缓存问题均已修复；
review 没有替代实际测试。此前诊断运行失败记录保留，最终结果以本节及 machine-summary.json 为准。

真实浏览器闭环：`web-live-2026-10-20T02-24-52-232Z.json`。
自然咨询不建 Trip → 多轮建议 → 明确采用 → 原旅程页与对话交替修改 → 明确排程 →
路线只读且前后安排相同 → 晚出发冲突 → 实际模型/Graph/高德路线/Validator → 用户 Accept →
同 Trip 回读、刷新及 390px 手机视口恢复；浏览器 pageerror 为零。
外部调用不是 Mock，用户预约及旅行数据是隔离库中的合成测试案例。

真实展示探针记录通用回答与联网美食回答：内部说明出现次数为零；DOM 以多个文本块更新；
实际搜索图片在浏览器完成加载，截图经人工视觉检查。最新文件及真实图片数量见 machine-summary.json。
先前出现过外部图片拒绝加载、搜索代理主机别名不适配及模型连接失败；未将这些运行记为成功。
Windows 本地进程仅在内存中调整隔离运行的代理地址，没有改正式 .env。

## 未扩大实施的边界

日期未定安排、跨城市、完整 Markdown、自动每轮配图、图片语义视觉模型复核、版权授权管理、
新长期画像和导航系统不属于本轮。图片检索描述仍可能错误，无法提供视觉真实性保证。
`max_walking_minutes` 最终硬约束缺陷仍独立 P1；不承诺全面兑现硬步行上限。
现有模型/网络请求的部分持锁路径未做系统重构，也未完成公网多用户或负载验收。
本轮真实地图证据针对 AMap REST 路线；未单独全面验收探索地图 SDK 的所有交互。
外部 Provider 延迟/失败、图片防盗链仍可能影响真实体验，错误必须诚实显示。
旧客户端不带版本时的兼容保护边界沿用已有实现；最新 Web 的修改携带版本。

## 复验入口

隔离 PostgreSQL：现有临时容器 `roamsync-natural-assistant-pg`，本任务 DB
`roamsync_unified_live_test`，没有复用生产数据卷。API/Worker 使用
`backend/scripts/unified_assistant_runtime.py` 的明确工作树与库名保护。
Web 使用 `vite.unified.config.ts`，保留原入口；浏览器地图 key 通过子进程环境沿用 Compose 的
AMAP_WEB_KEY → VITE_AMAP_WEB_KEY 映射，不写入源码。探针在 web 目录运行：
`node e2e/unified-assistant-live.mjs`、`node e2e/assistant-experience-live.mjs`。
复验会在隔离库产生合成旅行，不应把 URL 改为生产服务执行。
