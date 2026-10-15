# Chat/Planning页面一致性与保存说明修复 — 2026-10-12

实现、隔离验证及用户授权的当前 Demo 发布完成。HEAD 0b5010fe（完整值见manifest）；
未提交、清理工作树或覆盖其他任务改动。

## 根因与修复

运行 Web 的 index-Bfjhn9hB.js 缺少工作区已有的 latest_run_id 恢复逻辑。
创建旅行后的导航让左侧丢失 Run，而独立监控仍跟踪任务。Companion成功回复还
清空会话latest_run_id，前端也无条件清Run，导致追问后候选/确认消失。
现在导航/刷新恢复显式同Trip任务，保留Companion回复后的Run/Revision；旧会话有
规划对话证据时可恢复唯一同Trip活跃Run，多份则要求选择。普通解释不重新读取
Planning context，也不闪烁清空候选。进度沿用现有PlanningProgress与轮询。

原解释分支只读取严格验证的 accepted Ledger 或保存的Suggestion，没有读取
pending Revision已有的 snapshot.explanation/activity.reason。新增SELECT-only
reader返回这些保存的说明，标记saved_plan_notes、Revision来源及未验证事实警告。
不会通过模型重新推测当时理由，也不把模型说明升级为已验证决策依据。

调用链：AiPlannerPanel → AssistantSession/latest_run_id → PlanningRun →
PlanRevision → 进度/候选/确认；解释：assistant_service → CompanionRuntime →
CompanionContextReader → read_saved_plan_notes → CompanionGraph →
CompanionExplanation → CompanionThinking。

reader禁止autoflush；绑定Trip/Run/Revision、当前/base版本、状态、可解析snapshot、
validation_result.valid及同Trip地点。歧义、过期版本、拒绝、未知明确主体与显式
时间不匹配均不继承说明。原original_validated_decision/Validator/Accept门槛不降。
历史确实没有保存说明时仍诚实返回缺失；未补写历史，不证明旅游事实或偏好选择正确。

## 本轮证据

证据目录：backend/evals/results/chat_plan_consistency_20261012。

| 验证层 | 结果 | 日志 |
|---|---|---|
| 当前工作区后端，独立空PG/tmpfs，迁移0034 | 950通过/2既有警告 | backend_full_final.log |
| 最终Web发布镜像 | 129通过、typecheck/build通过 | web_release_final.log |
| 旧运行API基镜像的最小补丁，隔离PG | 18通过，12新增+6原解释边界 | hotfix_boundaries.log |
| Chrome/最终Web镜像/合成API | 6项通过、正式写入0 | browser_result.json及browser_*.png |

浏览器验证搜索进度、轮询进入待确认、旧会话刷新、确认入口、解释来源及追问后
确认保留；解释截图与滚动到确认卡片后的截图分开展示。没有点击接受，没有请求
正式API；不是Real Model/E2E正式Revision验收。Provider稳定性仍受Phase0.5阻塞，
本次解释读取无需模型调用，不扩大到真实规划质量评测。

第一次后端stale夹具用了被DB禁止的base_version=0（949通过/1失败），改为合法
旧版本后通过950。Web空候选被正确禁止确认，修正夹具；来源标签断言也已修正。
Compose相对路径、FROM镜像ID解析、浏览器缺少合成context响应的失败日志保留。
最终使用绑定本地基镜像别名、同锁dev环境及完整合成路由通过独立验证。

## 已准备的最小发布与回滚

旧API：60723c02c240875e3956744440ab19ea609dcf8ca31b6668a00845b57c2ef7a5。
新API：23248fc5bf2b722dbd2ba94f8e5b07fa37469aeaf652b70d979167560a707618。
旧Web：9794c7029f6ca25800174e7072d701065df2b6bbff6110dd168f4c6b614f99b8。
新Web：4e2d793b8918a750f7bc8b42685160262943277f29b5420cf93e805768202fa3。

release_app_diff.json证明API只有assistant_service、companion_context、contracts、
graph四文件变更和saved_plan_notes新增，没有夹带其余工作区Companion改动。
pyproject/uv.lock与旧API一致；生产补丁不携带tests/dev环境。
verification_manifest.json绑定281个源码/测试/eval/依赖配置文件及镜像；
拟发布API32项、Worker37项Compose环境与真实容器差异0，不输出凭据。

用户回复“允许”后仅切换当前项目API/Web，短暂影响页面/API请求；Worker/Postgres不重启，
不执行migration/checkpoint初始化，不写正式Trip。已准备release.override.yaml、
rollback.override.yaml及旧镜像别名。获批后已执行以下命令：

```powershell
docker compose -p roamsync -f compose.yaml -f backend/evals/results/chat_plan_consistency_20261012/release.override.yaml up -d --no-build --no-deps api web
```

失败以同样参数改用rollback.override.yaml。两者API均直接启动uvicorn，避免原默认
启动脚本自动迁移。发布前复核镜像/配置及进行中任务，发布后只做健康与页面读取
核验，不代替用户接受方案。生产部署禁止未经批准的原约束仍有效。

发布后证据：deployment_result.json与deployment.log。API live/ready HTTP200，
Web HTTP200，两个服务最终healthy；镜像与上述新API/Web完整ID一致。
发布前working_runs=0，前后10张表（正式旅行表及planning_runs/plan_revisions）的
行数与整行摘要完全一致，Worker/Postgres容器ID未变。未运行migration或提交用户决策。
原verification_manifest.json保留发布前快照，不回写历史验证。

deployment_ui/browser_result.json记录真实已发布Web产物上的6项界面验证，API全部
拦截为合成响应，不接触业务会话。另在数据库强制READ ONLY事务中按截图精确Run前缀
88df1262读取真实保存记录：唯一匹配，目前状态accepted，解释类型saved_plan_notes，
Revision为bf8c2138-be20-4ca4-b463-9d48fa9bf6fc，返回10条保存说明，模型调用/写入均0。
这证明当前该方案的保存说明可被实际运行的Companion读取；不等同于这些理由已获事实验证。
详见affected_candidate_readonly.json。用户浏览器需刷新以加载新JS产物。

隔离资源仅本任务roamsync-chat-consistency-20261012、
roamsync-chat-hotfix-test-20261012及独立3012预览容器，结束精确清理；
证据和发布/回滚镜像保留。没有清理现有工作树、生产容器或业务数据。
