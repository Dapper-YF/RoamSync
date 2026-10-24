# B3：新对话候选的独立窄边界复核

2026-10-24，Asia/Shanghai。A在重设计活跃树请求B复核后执行。**所列反例已被最终源码阻断；没有剩余已复现P0/P1限于本报告范围，不是系统或发布批准。** B没有改A产品源码、访问C私有题、调用模型/地图/数据库或执行任何正式采用。A实施修复，B独立提供反例和复核。

## 受审对象与身份

树为`E:/Study/RoamSync-reliability-a2-20261022`，分支`codex/conversation-itinerary-redesign-20261023`。审查时HEAD设计计划`3ce210e`不能代表当时未提交产品源码；每份JSON单独记录关键文件运行前后SHA256，所有有效最终探针均`source_unchanged=true`。不要将该活跃树旧HEAD称为受测产品基线。后续A冻结提交的限定核对见末段。

本次读：`conversation_candidate/{commands,binding,service,presentation}.py`、`draft_promotion/atomic.py`、`assistant_capabilities.validate_decision`、`assistant_turn`的V2分派及相应旧来源/极性/准备接口。最终关键字节SHA256：

| 文件（backend/app下） | SHA256 |
|---|---|
| conversation_candidate/commands.py | 01d31e610b5bbbfb0af34934200d8c9b7d16766cfd658cee8e4bda05a495e642 |
| conversation_candidate/service.py | beb01e1cc82492190bc43961d7ec9ac08c9b5f85a3bb87a56447e552f5df8c13 |
| conversation_candidate/binding.py | 3e806fda135175b38babe986781ec0493b1333f8029d873bacfe70eee1a05b1e |
| conversation_candidate/presentation.py | 6e8d9057c81088ca5ac30a92fea761331511086961ac7f1116433038e0710b24 |
| draft_promotion/atomic.py | 40bc46c194204707c3bac48014e901d1eef6c1b0f0f74d08ceaf81ef0d5d725e |
| assistant_capabilities.py | 461de59bfc0c2cab5b2b2b986bd5d298280c5cd1632509d05ff6c65f53beb7d6 |
| assistant_turn.py | 2f4e3f9151fae5945b21b64e1566bf6c6cc13d4bb3cb526479e73befdbfcba6e |
| flexible_creation.py | 12a2047503565335d9e7ecea727669cc8bce424d5a50efed98407bf0f5bb56ab |

全部相关哈希见JSON；字节身份可能受Git换行归一影响，A冻结后需再核对等价。下面行号对应最终读到的该组字节，而非未来HEAD。

## 新发现、修复与复核

### P1：typed command通过局部动词门后，把咨询提升为采用

初始`commands.validate_command`只排除若干疑问表达。注入adopt/source_quote=`保存`时，“保存后还能修改吗？”、“这份安排可以保存了吗？”、“我保存了吗？”、“保存会创建几个正式对象？”都通过。`assistant_capabilities:141–155`因此将原本`intent=direct`改成`modify`；`assistant_turn:153–181`在存在V2候选、没有正式Trip时可继续`decide_candidate`。

这证明服务端的错误命令后备防线缺口，**不证明真实模型必然生成该命令，更不表示执行了正式写入**。最早4句为探索性inline运行，尚无完整字节快照，A确认复现；不把它们包装成固定基线。

A先增加完整保存子句的正向门后，原4句被拒，但新固定字节探针又保留3个绕过：“假设我确认了，帮我保存当前候选。”“朋友会说，帮我保存当前候选。”“帮我保存当前候选。算了，我再想想。”见`boundary-after-positive-gate.json`。仅一个子句为肯定不能忽略其他子句的假设、转述或撤回。

最终`commands:41–77`复用`current_user_evidence_reason(message, quote)`作为所有命令共同来源门；adopt/discard要求整轮消息由独立肯定决定和有限确认语组成。`boundary-final-with-positive-controls.json`内8个非授权adopt全部拒绝；“采用并保存这份安排”“帮我保存”两个正例仍通过，dispatch保留真实adopt。不是继续追加疑问词，亦未退回依赖重复broad intent的授权。

### P1：复合变更漏一半，条件hash没有补救

“人民公园改成120分钟，宽窄巷子改成30分钟”只注入park的patch，初始`apply_patches`接受为`[120,90]`。两个活动的完整当轮要求并未都覆盖。另一初始输入“人民公园改成120分钟，然后保存当前候选”若只有adopt，也能把旧计划当待采用对象。实际`literal_conditions/apply_memory`没有变化、`capture_effective_requirements`为空，前后conditions_hash相同；它只绑定已捕获条件，不能证明当轮所有操作都执行。

A在`commands.apply_patches:85`之后增加完整变更子句覆盖、同地点动作绑定与同名拒绝，未识别/未支持的复合变更整体拒绝。全消息保存门同时拒绝“改后保存”和不带“然后”的变体。后续“假设我改主意了，人民公园改成120分钟”仍被局部modify接受的问题也已通过共同来源门封闭。红色输出见`boundary-after-coverage-extended.json`，最终4个compound全部拒绝；单目标75分钟及两目标75/105分钟两个完整正例仍成功。它们只作用于内存DraftPlan，没有publish/SQL/保存。

### P1：新生成流程将明确不去的地点变成ready游玩项

公开合成输入为：

> 请生成成都2026年11月9日玩1天的安排，每天10点出发18点结束，步行，不去人民公园，宽窄巷子要去。

注入错误V2 plan，将人民公园设为visit，source_quote仍为“不去人民公园”，分配60分钟。actual validate_decision→build_candidate→resolve_plan→prepare→candidate_presentation曾返回两处活动、stage=ready、blockers=[]，见`generation-negated-place.json`。地点与路线均由`fixture.invalid`合成provider返回；不是高德、模型原始回答或正式写入。只检查名称在原文与身份存在，不代表肯定选择；否定地点被记为soft未验证要求也不能允许反向安排。

A从原`flexible_creation.prepare_choices`提取同一纯函数`declared_place_choice:102`，V2 `service.resolve_plan:75–81`复用selected/optional/excluded极性。最终生成变体中：明确不去、仅作备选→visit均在真实POI查询前ValueError；正常两地点明确要去仍形成ready；假设generate在validate_decision清command，build未调用。输出分别为`generation-{excluded,optional,positive,hypothetical}-review.json`。这只证明所列极性反例，不宣称任意复杂否定覆盖。

### P2：同名活动的局部目标可被任意item_ref选中

原局部patch只检查选中ref的name出现在源句。给两个不同ref相同name，注入任一个ref都能把同一句“人民公园改成120分钟”应用到不同活动。完整POI准备可能拒绝同一个provider身份重复，故此反例仅针对命令层同名歧义，不能宣称真实页面已改错。

最终按名称匹配数量为1及`affirmative_entity_source`绑定自身动作，两个ref变体均拒绝。允许的许可粒子复用现有函数可选参数，未绕过主体/动作来源门。更广的地址/时间/同名消歧能力未在此验收。

## 原子绑定与展示：静态审查边界

| 路径 | 实际看到的校验 | 本轮结论 |
|---|---|---|
| published_session，atomic.py:21 | owner/kind/topic/publication ID、conditions hash、ready、protocol2、prepared/draft版本及hash、presentation内容digest与服务端重投影一致 | 没有找到可触发的新绑定绕过；仅静态，不等于完整并发验收 |
| confirm_atomic，atomic.py:40 | request/session/display hash绑定幂等键、_check_plan、locked_draft、当前发布绑定；同prepared授权复用须publication相同 | 未运行SQL、唯一键冲突/并发/取消竞态，本轮未验收 |
| resume_atomic，atomic.py:88 | 事务外refresh_equivalent；同事务_t1/_t2/_apply；最终再次核对当前会话发布与topic，异常路径整事务回滚 | 未触发真实回滚或Accept，不借用A已有PG结果冒称B跑过 |
| presentation.py | 同一PreparedPlan派生时间轴/摘要/路线/图片，presentation_digest排除stage/navigation字段；采用门另验stage及重投影 | 未见模型正文替代当前PreparedPlan的接口；未做本轮浏览器验证 |
| binding.conditions_hash | 捕获到的slots/preferences/requirements/withdrawn及records/task requirements形成语义hash | 不具有复合操作完整性证明；该缺口必须在命令层处理，不能让hash含义扩大 |

没有P0/P1新静态发现不意味着这些路径已通过；owner/公网隔离、A新工程总回归、过期/故障/并发真实恢复及模型连续任务仍由其原门槛约束。

## 原始证据与复现限制

目录为`docs/evidence/agent-b3-candidate-review-20261024/`。两个runner直接调用受审代码，socket连接guard禁止应用网络/数据库；真实调用次数为0。Windows生成探针的首个无效运行在创建asyncio内部唤醒socketpair时被guard拒绝，发生在main前，已单列`ENVIRONMENT_NOTES.md`，没有产品结果可覆盖。之后先初始化解释器内部event loop，再安装应用guard；仍不访问服务。

- `boundary-after-positive-gate.json`：保留跨子句假设/转述/撤回、部分patch及同名失败。
- `boundary-after-message-coverage.json`：这些修复后的第一次记录；随后增加的假设modify仍失败，另存下一份。
- `boundary-after-coverage-extended.json`：保留假设modify失败，不修改此前记录。
- `generation-negated-place.json`：生成否定地点ready的原失败。
- `boundary-final-with-positive-controls.json`：最终8非授权adopt、4复合反例、2同名目标均阻断；2保存正例与2完整局部修改正例保留。
- 四个`generation-*-review.json`：最终极性与假设生成边界、正向控制。

每份JSON保留输入command/原文、可见函数输出、相关源码前后hash；命令探针还保留单次函数耗时。合成准备只记录结果和provider调用，不具有真实业务时延意义。后续runner新增公开控制例，旧JSON里的完整输入原样保留；不是同一固定题集的独立准确率，也不是新holdout。所有private/sealed题面未读。

复现（B树，输出请另起名称以保留原记录）：

```powershell
& E:/Study/RoamSync/backend/.venv/Scripts/python.exe docs/evidence/agent-b3-candidate-review-20261024/probe_candidate_boundary.py --output docs/evidence/agent-b3-candidate-review-20261024/new-boundary-capture.json
& E:/Study/RoamSync/backend/.venv/Scripts/python.exe docs/evidence/agent-b3-candidate-review-20261024/probe_generation_scope.py --variant excluded --output docs/evidence/agent-b3-candidate-review-20261024/new-generation-capture.json
```

本次B仅新增报告/证据；产品修复由A完成。原B3读取范围/100与10投影/历史理由/已保存行程局部修改接口建议仍见`AGENT_B3_READ_HANDOFF_20261024.md`，没有被此次候选窄复核标为解决。B2/C2原结果不改写。A报告真实核心链成功过一次，但新鲜连续链仍有质量失败、SSLEOF/APIConnectionError与地图503；B没有独立重跑这些链，整体继续NO-GO。

## A提交后的只读身份核对

A发布下一开发起点`89b81e8d6cf5561f2bbab1a9ac437aa9dde88fb9`后，B按要求只核对，不重测。指定的4个关键文件（commands/service/flexible_creation/atomic）与上表审查字节相同，且与该Git提交归一LF后完全相等。扩展到所有15个探针相关文件时为14个相等：`draft_promotion/preparation.py`已变化，不能将整组旧合成准备结果称为精确89b81e8实测。

原15文件核对的失败记录保留为`freeze-source-equivalence.json`（all_match=false），限定范围的有效结论另存`freeze-source-equivalence-scope.json`；不删失败以换成“全部相等”。准备层旧审查字节SHA为`e97bf48dfde1dac2d956316006f9bfbb0c46f2753b832aa563bdf87155d05515`，新Git blob SHA为`e79614275a91cc00bcfee768c3defc8a92252d9774d73a3cb3aa3b29bc4a7102`，不是单纯CRLF差异。已交A说明改动并用其自己的精确提交工程证据覆盖。四个授权关键文件等价不等于完整产品、构建、数据库或模型链验收；NO-GO不变。

A已确认接受此限制：没有留下旧准备层字节，不能精确归因该变化。A报告精确89b81e8主回归1792通过、独立PG专套38尚在收尾，将另交源码哈希和覆盖证据；本段只是协作方状态，不是B自跑或最终专套通过证明。B不追加案例、不重测，不将A准备层若干最终阻断规则清单当成此差异的逐项解释。
