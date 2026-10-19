# RoamSync 自然旅行助手综合开发

开发分支：codex/natural-assistant-integration-20261019。
开发目录：E:/Study/RoamSync-natural-assistant-20261019。
正式源码E:/Study/RoamSync保持不变；不部署，不操作生产数据库。

## A — 已验证的共同基线

执行前正式HEAD仍为25a62cb，README.md/web/nginx.conf和原有未跟踪文件保留。
从评审分支1ce7e5d建立开发工作树，包含等价f06a847及评审补丁；没有再次应用7b67f68。
新建roamsync-natural-assistant-pg，仅loopback随机端口、tmpfs，无生产卷。
旧迁移在隔离库升级到0036；无Spike实验字段或双存储开关。

重新运行后端全量：1274 passed、1 skipped，包括32项真实PG写入保护/评审测试。
证据：evidence/natural-assistant/stage-a-full.xml。
复验脚本：backend/scripts/run-natural-assistant.ps1（PowerShell7）。
唯一skip仍为要求精确roamsync_test名称的收藏测试；本轮后续单独补验，不冒充通过。

## B — 路线与时间写入分离

失败证据stage-b-red.xml：刷新路线把17:00变14:40；保存路线的时长编辑把17:00变14:55。
新增GET /day-plans/{id}/route仅返回带当前版本、活动身份的路线事实，不写正式路线/时间。
原POST路由保留路径与响应体，默认刷新正式路线证据，不再隐式压紧时间；新增明确的
adjust_times=true授权向后修正冲突，保留已有间隔，固定活动/跨日/当天可用时间冲突422。
这是对已知错误时间副作用的有意修正，旧客户端如需调整时间必须显式授权或采用候选。

POST地图I/O及缓存写入完成后，才取Trip锁并复查捕获的版本；迟到响应409，不能覆盖
中途的手动修改。地图失败不写正式安排。既有新增/移动等事务中的地图调用暂未全面
移出锁，不能宣称所有外部I/O已消除。未引入两阶段工作流或新调度平台。

已保存路线排时同样保留间隔，仅有真实冲突且路线已知时向后修正；未知路线不补成零
耗时来移动活动。Trip/Activity版本与回滚由原共同写入保护承担。

原间接Activity版本回归保持断言，把时长45改180并先保存真实测试路线：新语义下
45分钟未触及11点活动，不应为了让旧测试变绿而继续挤掉间隔。180分钟实际冲突仍须
推进被间接修改的Activity版本并拒绝旧表单。没有删除安全断言。

专项最后一次40通过（32+8）；最终源码全量1282通过、1跳过，stage-b-release-full.xml。
阶段B门槛通过，允许继续阶段C。早先中间全量与专项证据保留，不替代最终结果。
正式混合精度结构、Planner与Web闭环不属于阶段B的完成声明。

## C — 有限混合精度（门槛通过）

0037新增Trip所属小型关系表trip_arrangement_items，未复制Spike实现、JSON存储或开关。
稳定UUID、已选/备选/留白/撤销、原始来源与最近决定来源、可选Place身份/日期提示、
留白起止及唯一Activity关联。关系表不维护已排程时间；Activity仍是唯一精确时间源。
未知地点允许仅保存用户给出的名称，不能冒充已核实POI。排程要求真实Trip所属Place
身份以及用户明确给出的日期、时间、时长，不调用旧add的默认开始时间和停留时长。
费用仍使用旧系统参考估计，不能称为实时实价；未知交通不伪造可行性保证。

新API：GET/POST/PUT arrangement-items和显式schedule。读取在短共享父锁内返回
同版本Trip、日期、活动与事项投影；写入使用预期Trip版本和父锁。固定/已发生活动
不能直接改回备选；进行中的旅行精确新增时间需走调整建议，未排程选择仍可编辑。
事项改回备选可原子解除普通Activity关联，清除过期邻接路线，保留来源和其他时间。
复制/已授权改期处理同一批事项，原旅行不受影响；日期缩短的越界留白不静默丢弃。

Validator/Accept新增身份、留白（含已知交通能否在留白之外完成）、关联遗漏检查；
采用候选在同一事务关联事项和Activity，重复采用不重复建活动。整个明确留空的日子
可以不填活动，但普通完整日程漏日仍失败。现有正式写入也调用留白检查，不能绕过。
已有Trip和老候选没有新事项时保留原语义。历史Draft仍不维护正式结果。

最终源码全量1299通过、1跳过（stage-c-release-full.xml）；专项57项通过，
另补旅行进行中拒绝直接新增精确时间的边界，C单模块18项通过（stage-c-final-edge.xml）。
新增受控转换/固定保护/复制改期测试。阶段C门槛通过，可进入D。
独立迁移库验证0036→0037→0036→0037，原Trip/日期保持，证据migration.json。
stage-c-cascade-red.xml的早期测试漏confirm=true，仅属测试调用错误；纠正后14项通过，
没有据此修改原FK策略或扩大删除架构。

## D — 有界对话及Planner接入

Planner与Companion上下文读取当前事项；selected/optional/cancelled/free_window保持不同
含义，未核实名称不授予POI身份。Planner继续使用原符号引用，服务器按已知Place或
唯一精确名称绑定arrangement:<UUID>，最终Validator检查，Accept时才关联Activity。
被撤销事项不得从旧对话恢复。未采用候选不会把备选变成已选。

保留AssistantSession原创建预览/确认：prefer_flexible启用有限CreationChoice，不创建
第二份长期方案。预览可展示未定事项、AI建议来源、固定预约及留白；用户采用后一个
事务保存Trip/事项/固定Activity；不自动启动Graph。用户原话、预约时间范围与POI身份
严格校验，模型不符时最多一次字段修复，仍不符则澄清。已定时间仅在Activity中。

少量明确修改（改备选、保留、取消）使用同一write_item，无PlanningRun；绑定Trip、
版本和当前message ID。无法唯一定位则澄清。固定/已发生活动不直接删除。'就按这份来'
必须带当前预览ID或被明确选择的Revision及授权，不能取最近一段文本作为候选。

确定性全量stage-d-release-full.xml：1309 passed、1 skipped。页面/对话交叉写、旧版本
拒绝、重复消息、轻量采用无Graph、不得虚构预约等回归通过。新增测试清理其自建预出行
会话，保留旧流式单轮断言；早期失败留下的67个NULL-Trip会话仅在专用测试库清理。

真实Provider使用本次隔离API18019和worker、独立live库；只读加载正式.env的Provider
配置到内存，不落密钥。原代理APIConnectionError/RemoteProtocolError；隔离进程直连
连接成功，未改生产配置。live-13636...首次保存通过，但偏好陈述回复不贴题；有界偏好
陈述接收修正后live-cd2974...链再次通过：真实咨询不创建旅行、多轮来源→建议→采用→
读取，南京博物院时间未知、玄武湖备选、周六15—16留白、周日总统府14—15固定活动。
预约是合成用户提供，地图核实的是地点身份，绝非实际订票。历史失败JSON保留。

真实Graph探针的环境准备/参数错误及一次实体澄清保留；“新增地点”触发网页研究但
未配置搜索Provider，出现planner_research_unavailable，未伪造资料；改测已有实际POI及
已保存路线上的局部时长调整。完整Graph/Accept结果待探针结束记录，不能把HTTP200
或awaiting_confirmation直接称为采用通过。

## E

待实际Web实施和浏览器验收；前面的工程通过不代表产品完整任务链已经完成。
