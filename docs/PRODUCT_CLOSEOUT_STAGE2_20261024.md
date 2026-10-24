# RoamSync 产品收尾第二阶段

状态：开发与真实验收进行中，尚未达到 GO 门槛。所有操作限隔离源码和独立测试库。

## 基线与证据边界

本轮开始核实正式 `E:/Study/RoamSync` HEAD 为 `ea3ba833e6a77122c08c1c9327c18a346e3c48ef`，不是假定未变；正式工作区已有 tracked/untracked 修改，全部保留。首轮隔离树 HEAD 为 `71e07c2357f631bb9a57c56527c5d9f90d6fbedf`，其父产品提交 `de728640accbb6816af3a74930720f43cb10ce54` 在正式基线上追加窄协议修复与文本事实保护，71e07c2追加证据。

本轮分支 `codex/product-closeout-stage2-20261024`，工作树 `E:/Study/RoamSync-product-closeout-stage2-20261024`，外部原始证据 `E:/Study/RoamSync-stage2-evidence-20261024`。正式数据库和部署未改。上轮20题仅作为回归，不再称为独立未见题。

## 批次1：连续只读任务与有效条件

提交 `e4d9023`。修改 `assistant_capabilities.py`、`read_references.py`、`saved_trip_reads.py`、`assistant_memory.py`、`assistant_research.py`、`companion_provider.py`、`place_content/provider.py`、`place_content/reviewed_aliases.json`；新增对应回归测试。

失败根因在选择/投影阶段：地点序号混入建议解析；单项查询覆盖比较顺序；任务自由搜索词和身份参数混用；任务拆分丢共同日期范围；完整比较检查误用网页标题匹配，拒绝已核实别名；保存活动读取遗漏 position、总天数与序号；同行要求没有主体边界；walking_effort固定回复跳过用户实际推断问题。

最小实现采用持久地点卡的有序身份集合，单项读取保留比较顺序；逐任务限定地点来源，服务器只读展开引用；具名POI查询不用重复自由搜索词；继承当前明确日期范围；保存态从同一有界快照读取序号、总天数和保存值；分析问题保留原分析路径。同行条件附带原话主体，完整退出同行才可移除该主体的旧条件，拒绝操作不产生撤销记录。退出地点不等于退出同行。推断问题返回常规模型链及明确资料范围，不再返回固定规划建议。

别名仅纳入已审阅的 provider ID、名称、城市、坐标绑定，不采用模糊名称匹配。公开官方出处随 JSON 保存；这些出处只证明别名身份，不作为当天营业或场所步行证据。

## 批次2：普通聊天修改先候选

提交 `29d0544`。删除 `assistant_arrangement.simple_duration_edit` 及其直接写入调用，保留显式页面表单/安排选择编辑和现有候选 Accept。时长聊天请求继续进入既有 Planner → PlanRevision → Validator → Accept，不新建写入机制。数据库测试改为要求建立 PlanningRun、正式活动及版本不变、重复消息不重复建立；异常注入在交接链验证回滚。

## 批次3：候选协议和交接

提交 `a522a84`。生成协议仍 extra=forbid，强调仅合法结构；不加入吞掉 candidate_command_note 或未知操作字段的恢复。已有纯只读恢复保持原有窄范围。候选修改区分只选择候选工作副本的说明与额外活动变更；未知目标/数量仍是未完成操作。采用支持“采用这份候选并保存”语序，仍要求当前完整肯定授权。地点匹配使用单向真实名称/受审别名，避免反向后缀扩大身份。没有路线或有 blocker 时，摘要必须如实展示，不能一律声称已取得地图估计。

## 已保存开发失败与验证

`batch1/first.xml`：96项通过；`third.xml`：129项通过；`fourth.xml`：64项通过，集合有重叠，不能相加。`second.xml`因测试文件名输入错误零测试，不计通过。Astra复核发现的序号漂移、取消地点误删同行要求和共享Session并发点均已加入修复/回归。

`batch1/real-r1.json`、`real-r2.json`、`chengdu-c1.json`、`chengdu-c2.json`、`chengdu-c3.json`均为开发诊断，保留失败，不当冻结验收。c1/c2真实模型输出合法候选，但同名人民公园和宽窄巷子景区/步行街使身份未唯一绑定；候选不可采用。c3模型额外发明“周边漫步”visit，被来源校验拒绝。修复不以擅选同名地点或删除限制换取成功。

原始JSON包含完整用户消息、可见模型全文、工具参数/返回、每轮八张正式表状态摘要、pending_action和耗时；不采集模型隐藏推理或API密钥。开发轮若源哈希变化则不计冻结测量。最终全量数据库测试、冻结新题、完整黄金路径及剩余阻断将在完成后追加，当前不宣称通过。
