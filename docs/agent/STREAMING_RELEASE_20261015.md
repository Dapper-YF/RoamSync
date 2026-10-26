# 正式目录流式聊天验收与发布

2026-10-15。唯一正式源码与部署来源：`E:\Study\RoamSync`。

## 结果与修复

VERIFIED：正式目录已有的 SSE 接口、模型公开文字回调、前端逐字展示和 Nginx 无缓冲配置已进入正式运行版本。本轮使用正式目录的 `scripts/start-roamsync.ps1` 重建并核对，没有从其他 worktree 部署源码。

修复一个可复现异常：生成请求失败后，如果数据库回滚也失败，原 SSE 任务会退出，但客户端只能继续收到心跳。现在回滚异常只记录类型，仍发送统一 `error` 事件并结束数据流，不泄露连接信息或模型正文。新增回归先复现超时，再通过修复。

原有消息编号幂等、完整回答提交、断线取消、格式修复清预览、候选确认和正式行程写入边界继续保留。没有新增数据迁移或修改规划接受规则。

## 本轮证据

| 检查 | 结果 |
| --- | --- |
| 最终正式源码，独立 tmpfs PostgreSQL 后端全量 | 976 passed，2 个既有警告 |
| 测试镜像 app/tests/migrations 与正式源码 | 206 文件，差异 0 |
| 正式 Web 构建 | 132 测试通过，typecheck/build 通过 |
| 部署后实际 Web 产物，Chrome + 独立 SSE socket | 7 项通过，浏览器运行错误 0 |
| 正式 API/Worker 与源码 | 各 140 个运行文件哈希匹配 |
| 发布前后 7 张业务表 | 数量和内容 SHA256 一致 |
| API ready / Web healthz | 均通过 |

Chrome 加载实际部署的 JS/CSS，聊天 API 全部由隔离合成 HTTP 服务提供。检查分析先出现、正文完成前增长、完成后替换预览、刷新恢复、断线清除半截回答、重试复用同一消息编号；不读取私人会话或操作正式行程。

MEASURED：正式 API 容器中的真实 GLM、合成无数据库 Reader，一次调用成功，首次正文 3.3049 秒，完成 5.4304 秒，4 个正文增量、32 个公开事件，finish_reason=stop。仅记录时间和数量，不保存生成正文。一次调用不证明长期稳定性或全面事实质量。

第一次全量测试为 975 项；随后发现同目录天气模块有两项源码/测试差异，保留初次记录，重新构建并完成上述 976 项最终回归。最终源码绑定差异为 0，未回退天气工作。

证据在 `docs/evidence/streaming-release-20261015/`：最终日志 `backend-final.log`、`deployment.log`、`deployment-verify.log`，源码绑定 `source-binding-final.json`，浏览器 `browser.json`，模型 `provider.json`，数据 `data-before.json` / `data-after.json`。初次检查记录保留。

部署静态产物验收：在 `web` 目录运行 `node e2e/assistant-stream-release.smoke.mjs`，不访问正式聊天 API。`scripts/verify-streaming-provider.py` 显式执行时会产生一次付费模型调用；没有后台任务。`scripts/streaming-release-state.py` 仅在数据库只读事务内输出指纹。

本任务测试 Compose 项目 `roamsync-stream-release-20261015` 已清理，正式数据库卷保留。发布前 API、Worker、Web 镜像另存 `:before-stream-20261015` 标签。

## 边界

模型公开正文支持生成中增量展示，不读取内部 thinking。分析摘要不代表完整内部推理。需来源核验、事实拼装的回答仍先经过服务端检查，不保证所有回答路径直接按模型 token 输出。历史消息直接展示。模型事实质量与 Provider 长期稳定性仍保留原有未完成结论。
