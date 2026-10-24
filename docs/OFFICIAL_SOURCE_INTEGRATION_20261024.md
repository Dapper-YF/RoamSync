# 正式工作区源码整合（2026-10-24）

用户本次明确要求“现在把所有修改合并到正式工作区”。本次范围是将当前
A/B/C最终有效交付合入唯一正式源码目录`E:/Study/RoamSync`，不启动或部署
3000，不改生产数据库，不将源码合并解释为产品质量GO。

## 输入与整合范围

- 正式原HEAD：`6b298caddb79125991bfc5183ddeefc09029f31c`。
- A最终交付/审查：`a1e5946`，其中产品BASE为`89b81e8`。
- B最终交付：`f036d0a`，产品`3f98303`、仅测试观测`b393bfd`。
- C最终前端产品`e102205`/`ba143a2`及交付`207c9b7`已在A89b81e8祖先中；
  C对话最后公开交付未提出额外新产品提交。不能将历史已失败实验分支全部重放。
- 新隔离集成树`E:/Study/RoamSync-source-integration-20261024`，分支
  `codex/official-source-integration-20261024`；A+B合并提交`d37da85`。
  仅三份架构/交接文档冲突，两个功能契约都保留；产品源码无合并冲突。
- 合并后backend/app和web/src产品逻辑与B最终继承的A/C版本一致；
  集成测试发现候选保存后的测试桩把Session响应用于Arrangement接口，
  `f7fc455`仅修CandidateAssistant测试桩返回类型，未改产品逻辑或旧断言。

## 正式目录保全

外部保全目录`E:/Study/RoamSync-deployment-backups/20261024-source-integration`：
`before.json`逐文件记录原HEAD、4个tracked修改、2015个untracked文件和
1个ignored环境文件的原始字节哈希；tracked原文及binary patch单独备份。
原README、.env.example、backend/scripts/quality_runtime.py、web/nginx.conf
均不在本次入库变更路径，保留原修改，不reset/stash/clean或批量add。

4个untracked与入库路径重叠：assistant_capability_cases.py及三份20261021
旧报告。逐字节或规范化换行后均与入库版本一致，原文完整另存
untracked-collisions目录；合入后仍恢复原始字节，不能静默覆盖。
`.env`密钥、数据库备份、私有会话不入Git。无Obsidian写入。

## 本次合并版本验证

外部证据目录`E:/Study/RoamSync-source-integration-evidence-20261024`。

- 使用项目`scripts/run-isolated-tests.py`，新唯一Compose项目
  `roamsync-test-d9b1a1f7eb92`、tmpfs测试PG，无host数据卷/端口、不读正式.env。
  合并产品d37da85：主套1816通过，专库38通过，0失败；source_unchanged=true。
  该runner已清理自己的隔离资源，保留共享synthetic15435；正式容器未动。
- Web初次默认并行：261通过/4项5秒超时，日志web-test.log保留。
  标准maxWorkers=2再次265断言通过但1个unhandled错误，不能计为通过；
  日志web-test-bounded.log保留。错误来自测试网络桩把Session对象返回给
  保存后触发的arrangement-items请求。只修测试桩，所有原断言保留。
- 最终完整Web测试47文件265通过、0失败/未处理错误，exit0；类型检查
  exit0，正确正式标志构建exit0。外部result JSON和日志保留，整合收据
  绑定实测源码，不能只用旧89的工程数字。
- 默认构建通过；另一次content flag误写travel-content-v1的构建也保留
  为wrong-content-flag，不作正式标志证据。正确正式标志使用
  VITE_DISCOVERY_PRODUCT=true、VITE_TRAVEL_CONTENT_CONTRACT=place-content-v1、
  VITE_ASSISTANT_CONTEXT_CONTRACT=assistant-context-v1，生产构建通过。

## 运行与质量边界

合入前正式Web/API/Worker/PG均Exited255，3000无监听。源码合入不重建
既有镜像，也不启动容器。前端dist构建在隔离树中，不冒充正式运行版本。
既有数据卷保留，未连接生产PG15432做迁移/更新或数据清理。

用户已授权源码合入；此前NO-GO阻止未经质量验收发布，不再阻止本次明确
要求的源码整合。模型schema波动、事实支持、公网身份隔离和新独立题门槛
仍开放。B最终公开开发题5/6、C历史严格2/20原样保留，不以工程通过替代。
后续若发布，须另核验备份、运行配置、镜像/源码一致性和真实用户链路。
