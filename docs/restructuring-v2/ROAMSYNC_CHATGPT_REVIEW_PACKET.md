# RoamSync V2：第三轮修订候选评审包与文档索引

日期：2026-10-15。已收到并逐项回应ChatGPT第二轮反馈；方向原则接受，候选方案尚未最终冻结，未获业务实施授权。本文件替代旧第一轮转交摘要，便于继续评审，不建立另一套规范。

## 本轮主要修正（可直接转发）

1. R01：Instant只服务持续应用内GPS，external只RouteQuote+本地HandoffReceipt；不能称GPS active或自动到达。新增starting/suspended、设备互斥、终态幂等、断网StopIntent/重启恢复协议，正式Navigation FK与Recovery保留。
2. R02：Draft day_index/可空dates，复用模型client、refs、明确要求编译与小步提取的纯规则；Formal/Draft adapters分开，不复制Graph/Validator、不造假日期/Trip。reviewable必须有ValidationCoverage。
3. R03：撤回“两承诺必须两点击”和未验证全链原子的推断。用户可以一次明确“创建并采用当前显示方案”；默认P1持久operation多事务恢复，P2预备后短SQL原子备选。方案/事实条件实质变化重审，原授权不批准后台新方案。
4. R04：physical/browse/discussion/read context/action request分开；owner/唯一目标/权限/授权/正式版本由服务端Resolver生成。最小读、并发selection版本、Topic预算隔离；询问南京地点是否加入苏州只读Trip不构成加入授权。
5. R05：unknown/评分/估算误报提前G0；EvidenceField将存在状态/性质/时效/读取方式分开。内部预算估算保留但不当实际价；住宿POI不等指定日期房型库存，无报价接口就不生成假Quote。
6. R06：309文件canonical manifest复检零漂移，15树补双向hash/hunk差异和选定patch。优先facts/timezone、跨日/元要求、Brief来源贯通；整合后新共同基线仍未形成。首期可信单owner，公开与跨设备另门禁。

## 新证据与未通过事项

- VERIFIED：当前Graph多节点独立session/commit；save_plan_revision内部commit、Accept内部commit，approval为interrupt，checkpoint另存。现接口不能直接组成“建Trip+规划+Accept”现成原子事务。
- MEASURED：现测试镜像network=none，无DB/模型/Provider调用，formal candidate无date校验失败、build_planner_input无date TypeError，codec往返true。这是兼容负向证据，不是Draft成功。
- VERIFIED（缓存范围）：SDK11.2.100 JAR含walk/drive/startGPS/start/stop符号；缓存合并Manifest只有INTERNET/receiver权限。没有运行实际GPS，不能把符号存在当导航验收。
- 最近完整实测仍为第一轮同源码快照：backend1002/2warnings、Web132/typecheck/build、Android35。本轮没重复全测、没修改业务代码/Schema/配置/正式数据，没集成/合并/部署。
- GPS真机、Draft成功复用、promotion guard/cancel与SQL恢复、legacy scope/FK迁移、实时Provider许可/库存仍待验证。

## 正式化推荐的具体取舍

P1：先Draft域预备真实日期方案/来源/路线→用户可一次组合授权→T1明确建Trip→T2同语义formal pending→T3授权/版本guard后原Accept→对账。可能出现可见“已建Trip、未采用”，同operation恢复、不自动删；内容变化needs_review。

P2：所有外部I/O先结束，再在短SQL事务内物化Trip/候选/接受；需拆当前内部commit/语义解析、完整formal回归。最终状态更整洁但改核心更多，因此暂备选。请重点核查P1是否在保持用户控制前提下足够好，而非要求用户点击次数等于事务数。

## 新路线与启动顺序

共同基础G0：审查集成基线、unknown/timezone修复、可信owner/Place/Context/Nav/Draft/错误幂等契约、早期GPS/Draft spike。

并行主线：
- A：杭州集中区域探索/真实详情/收藏/地图→餐饮住宿候选/真实路线/external→真机GPS Instant。
- B：最小Read/Action Resolver与stable Session→跨页多Topic、结构化Place推荐/动作、降级。
- C：Brief贯通与公共核→无Trip Draft/Run→P1正式化/旅程/旧历史。
- 显式偏好/纠错及Evidence跨线渐进，Q质量每个检查点持续，不等最后才看Provider/模型/真机。

共享Schema、Graph/Accept、assistant/contracts、AndroidRuntime、两端全局壳各有单owner；角色待最终分配。契约冻结前不派多线实现；依赖未就绪用versioned synthetic fixtures，真实入口关闭。当前没有新共同基线commit，也没创建开发工作区。

## 少数真正待负责人批准的事项

- P01：推荐P1；是否接受失败后保留可见“已创建、未采用”Trip及恢复入口。
- P02：按Web external/Android GPS分别验收；酒店首期POI与核实入口，库存另门禁。
- P03：分类型留存具体期限/删除恢复期；默认不全量行为或连续轨迹采集。
- P04：批准候选契约及首批G0小修+GPS/Draft spike，并指定owner；后续迁移/清理/发布不自动授权。

技术问题由V-NAV/V-DRAFT/V-PROMOTE/V-SESSION/V-FACTS/V-BASELINE等证据解决；不需要产品负责人替工程猜实现。

## 当前完整文档（唯一一组）

1. [第二轮逐项回应](ROAMSYNC_REVIEW_ROUND2_RESPONSE.md)：接受/修正/保留异议、D01–D18去向、已做与待做证据。
2. [核心ADR](ROAMSYNC_ARCHITECTURE_DECISIONS.md)：候选决策、备选、理由与验证条件。
3. [修订领域架构](ROAMSYNC_DOMAIN_ARCHITECTURE_V2.md)：状态机、函数依赖、两种promotion、Read/Action、字段/API和数据流。
4. [并行纵切路线图](ROAMSYNC_DEVELOPMENT_ROADMAP_V2.md)：G0+A/B/C+P+Q、DAG、用户成果、owner和14项硬门禁。
5. [实施准备](ROAMSYNC_IMPLEMENTATION_READINESS.md)：可排首批、阻塞任务、具体V-*断言/改动面、差分与证据索引。
6. [真正未决项](ROAMSYNC_OPEN_DECISIONS.md)：P01–P04与技术门禁，已接受原则不重开。
7. [产品定义/12场景](ROAMSYNC_PRODUCT_2_0_DEFINITION.md)：已同步external最小性、三种正式化行为和一次组合确认。
8. [数据生命周期/迁移](ROAMSYNC_DATA_LIFECYCLE_MIGRATION.md)：已同步P1恢复、scope先于SET NULL、实验/旧数据安全。
9. [第一轮现状审计](ROAMSYNC_CURRENT_STATE_AUDIT.md)：保留原事实和原实测范围，附第二轮补充入口。
10. [本轮证据目录](evidence/round2/)：snapshot、函数依赖、15树双向差分、选定只读patch、SDK静态、日期兼容探针。

请第三轮重点审查：最小公共核是否可执行、P1授权与提交恢复是否完整、scope/FK迁移是否仍有旧客户端漏洞、Instant设备槽/取消是否足够，以及是否可以批准首批受控实现。不要把本文当作已实现/测试通过/最终批准。当前等待最终批准。
