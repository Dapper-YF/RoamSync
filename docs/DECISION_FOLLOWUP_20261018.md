# C 决策质量续做（2026-10-18）

## 已实现的增量

提交 `3af06eb`、`67ecdf7`。未修改生产运行环境、数据库结构、Planner允许地点/日期域、正式确认或版本权限。

- 候选比较 v2 增加同日、同固定活动、有新鲜 Provider 步行腿的成对取舍。明确额外步行与兴趣类别、用户指定、时间空档、费用估算等竞争维度；不修改原排序，不强制所有用户选择最短腿。
- 最终 deterministic review 持久化实际选择、更长腿代价和输入支持的竞争收益。正式方案摘要显示差异，兴趣收益不被当作“整体最优”的证明，路线腿不等于全天步行。
- 缺失实际消费不再输入零；新增事实/能力契约，区分剩余活动估算、已记录消费和未知实际消费，以及未实现的自动营业/预约核验。
- Planner复用既有一次输出修复窗口，对已知“未知预算却断言合规”“承诺未来自动核验”矛盾请求改正。Graph在最终路线校验后再次检查，不因Ledger shadow模式放行；失败不创建可确认Revision。
- 正式摘要按实际复核结果显示预算not_evaluable及未知运营事实，不承诺后续自动核验。模型活动理由仍保留；此有限检查不是自由文本真实性的完整保证。

## 独立反例复核后的修复

原实现的短语检查确有作用域错误。已修复并加回归：

- “实际消费未知但预算合规”“总费用不会超过预算”在实际消费未知时不再放行。
- “系统不会自动核验营业状态，请自行确认”及“预算合规与否尚待核验”不再误报。
- 未知曝光不能因零天气惩罚获得天气收益；双方曝光/时段均有依据才比较，taxonomy收益仍标明仅类型提示，不是避雨保证。
- 未知建议时长不能因零惩罚被宣称更适合已知空档。

## 运行结果和限制

VERIFIED：最终代码在独立测试Postgres的新数据库 `decision_followup_test` 上，Linux 65项专项通过，包括新Graph反例：即使Ledger shadow，不实自动核验承诺也在一次纠正后失败、无Revision、正式Trip保持。Windows直接Graph先因Psycopg与Proactor不兼容失败，随后在Linux复验；未把该Windows失败算通过。

MEASURED：直接Planner的三组新鲜AMap/GLM对照（独立复核前的中间实现）：

| 用户条件 | 实际选择 | 服务器可比较的证据 |
| --- | --- | --- |
| 仅少走路、无类别偏好 | 中国丝绸博物馆 | 到同一雷峰塔活动28分钟步行 |
| 少走路且喜欢景观摄影 | 西湖 | 同向54分钟，多26分钟；模型明确解释景观摄影收益与代价 |
| 明确景观比少走路重要 | 西湖 | 同样额外步行，被用户优先级允许 |

没有据这三次宣布一般最优：比较只覆盖一条有向腿。第一组模型顶层explanation为空但活动reason完整，另两组顶层说明因活动停留数字触发既有 `decision_explanation_unverified`（shadow）；真实理由与边界均在原始证据保留，未改成全通过的质量结论。

MEASURED：预算补测已有消费/撤销两组完成，未知消费首次连接失败后单独补测完成；未知消费仍为 `not_evaluable`，没有“预算合规”或自动核验营业的承诺。费用为受控输入，非核实票价。首轮因Docker专用代理地址在Windows直跑不通，三次连接失败也保留；仅进程内改用同一代理的本机地址重跑，未改部署配置。

MEASURED：最终 `67ecdf7` 运行代码已通过真实模型→Graph→Validator→明确Accept→正式回读，原始记录为 `graph-live-configured-v4.json`：

- 新建专用 Trip `36cfd221-9e3a-40c4-8880-6ec3f43f41b8`，GLM-5.3-flash实际调用共6289 tokens。
- 同日到14点雷峰塔固定活动的真实AMap腿：西湖53分钟，丝博28分钟；这次与直接对照54分钟相差1分钟，未沿用旧值。
- 无类别偏好且希望少走路，实际选中国丝绸博物馆09:00、停留120分钟；服务器记录短25分钟且没有更长腿补偿收益，模型没有凭排序结果直接取得最优证明。
- 500元有效日预算因目标日实际消费未知仍为 `not_evaluable`。最终正式摘要明确不能据估算认定总预算合规；模型解释检查无冲突。130元只是剩余活动输入估算，不是实价或全部旅行费用。
- 候选通过既有Validator；明确Accept使正式version 3→4，保留雷峰塔14:00/60分钟锁定，回读两活动及2028米/28分钟AMap步行路线（`is_estimated=false`）。

准备是API而非Web UI，没有手机操作，不能当Web→Android→Web完成。上述首次完整链是无类别兴趣的少走路情景；随后补充了下述有竞争目标的完整链。

保留的失败：初两次首个地点搜索因配置缺失失败，root恢复原环境文件注入后已解决；随后测试脚本漏DraftEdit必填字段、使用PATCH而非PUT、未设置临时脚本PYTHONPATH先后失败。均未隐去；创建的专用隔离Draft/Trip保留，无历史数据清理。它们不算产品Graph失败或成功。最后修复脚本、使用新专用Trip通过上述完整链，应用代码未为通过测例更改。

## 景观收益与步行代价的第二条完整链

MEASURED：先在新Trip `e3023632-9638-47c7-86e3-426fcb65d110` 实际运行“仍希望少走路，但有依据的景观摄影体验更重要”。GLM选择西湖53分钟腿而非丝博28分钟腿，Validator/Accept通过；却暴露**产品复核错误**：真实AMap西湖category是`sight`，旧兴趣匹配只比较category与`nature`，因而服务器摘要误称长腿没有补偿收益。已有精确审核的湖泊、山丘、堤岸、岛屿景观组件没有进入该取舍复核。该结果不能算质量通过，原Accepted记录和理由完整保留在 `graph-landscape-priority.json`，没有重写或重复Accept。

`bb19660` 修复该实际反例：复用已有精确身份审核的景观组件与当前nature/photography要求或保存偏好；保留assertion、来源、审核时间和偏好来源，不改真实Provider分类和排序，不由景点名加分。未知/低置信类型、未来审核/过期证据、已撤销且有typed历史的旧偏好不能提供收益。中文说明明确不保证摄影效果、天气或开放。最终67项Linux专项通过。

MEASURED：修复重启后，以相同条件新建 Trip `4f1d0e4e-9cdf-4a6a-881c-f4cc40d94eef`，不预先强制选西湖。GLM-5.3-flash7415tokens→完整Graph→Validator→明确Accept→正式回读成功：

- 实际选择西湖09:00/120分钟；到同一14点雷峰塔固定活动，53分钟腿比博物馆28分钟多25分钟。
- 最终review为`competing_objectives`，记录`matches_reviewed_landscape_interest`、nature/photography偏好来源及 `west_lake.landscape_components`/UNESCO来源；正式摘要说明实际代价和输入支持的收益，不再误称无收益。
- 有效500元日预算仍`not_evaluable`，目标日实际消费null；解释矛盾检查为空，未把估算升格成预算合规。天气此次是实际Open-Meteo有覆盖的城市代表坐标预报，仍非现场天气或开放证明。
- 正式version3→4，14点/60分钟锁定活动保持；最终AMap Route2.0步行3963米/53分钟、`is_estimated=false`。
- 原始证据 `graph-landscape-priority-fixed.json` 带本次API五个模块SHA；紧凑摘要 `graph-landscape-summary.json`。这是第二种用户优先级的完整链，不是全天最优或一般性质量保证。

## 文件和复现

- `backend/evals/decision_followup.py`：三个真实步行权衡对照，无DB写。
- `backend/evals/budget_followup.py --scenario unknown_spending`：受控费用/未知消费真实模型，可单独复跑。
- `backend/evals/decision_followup_graph.py`：仅允许隔离18004/roamsync_v2_integration，在新labelled Trip通过真实草稿/正式化API准备，真实Graph/Validator/明确Accept并回读。该准备是API，不是Web UI，也不是手机执行。
- `docs/evidence/decision-followup-20261018/`：保留直接模型结果、连接失败及完整链尝试。

专项测试：`pytest tests/test_decision_followup.py tests/test_decision_followup_graph.py tests/test_planning_graph.py tests/test_planning_explanation.py tests/test_candidate_decisions.py tests/test_openai_planner.py`。Graph测试须先迁移专用测试库，不得指向正式或隔离产品数据。

## 尚未解决

完整跨地点/全天多目标优化、无已知收益却仍选长腿时的通用质量修正、任意自由文本事实/承诺检验、实价和预约/运营事实、天气Provider可用性，均未因这轮有限改进而完成。后续不能以输出格式、测试数量或合入正式目录代替质量验收。
