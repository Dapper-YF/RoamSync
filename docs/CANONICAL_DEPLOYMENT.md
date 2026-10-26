# RoamSync 正式源码与 Docker 部署

2026-10-15，用户指定 `E:\Study\RoamSync` 为唯一正式源码目录。

正式 Compose 项目为 `roamsync`，所有服务统一使用本目录的 `compose.yaml`、`.env` 和构建上下文。
其他目录、历史镜像、实验工作区不能直接部署为此项目。需要的实验改动必须先整合进本目录并验证。
这里指本目录的实际文件，包括现有未提交改动，不代表其他工作区已经合并或 Git 工作区已经清理。

## 启动与更新

先启动 Docker Desktop，再双击根目录 `Start-RoamSync.cmd`，或运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:\Study\RoamSync\scripts\start-roamsync.ps1
```

脚本固定正式目录和 Compose 项目，清除本进程中会覆盖 `.env` 的同名环境变量，构建当前文件并等待服务启动。
随后检查全部五个服务的部署来源、API/Worker 的后端文件集合及 SHA256、GLM 配置与健康端点。
失败返回非零退出码。脚本不初始化演示旅行或重置数据。

网页：<http://127.0.0.1:3000>。Docker Desktop 对 `roamsync` 点击启动，运行的是最近构建的镜像；
它不会把源码改动自动编译进去。修改代码后应再次运行启动脚本。

只读核对：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:\Study\RoamSync\scripts\verify-roamsync.ps1
```

## 本次切换证据

VERIFIED：从 E 盘重建 API、Worker、checkpoint init、Web，并重建 Postgres 容器以统一 Compose 来源。
原 `roamsync_postgres_data` 卷继续使用，未删除或重置。切换前无 queued/running Planning Run。
正式数据备份位于被 Git 忽略的 `backups/roamsync-before-canonical-20261015.dump`，不提交数据库内容。

VERIFIED：独立 tmpfs PostgreSQL 的后端测试 956 passed / 2 既有弃用警告；
Web 132 passed，typecheck/build 成功。临时测试容器与网络已移除。
API/Worker 各 140 个后端文件与正式目录逐字节哈希一致，涵盖 app、migrations 与依赖定义。
Docker 的运行项目配置来源仅为 `E:\Study\RoamSync\compose.yaml`。
7 张已记录业务表切换前后数量与完整行内容指纹一致。API ready、Web healthz 均成功。

MEASURED：新 API 内使用实际 CompanionRuntime、合成无数据库 Reader，真实调用
`glm-5.3-flash` 一次成功，finish_reason=stop；没有创建聊天、旅行或候选方案。

结构化证据见 `docs/evidence/canonical-deployment-20261015/`，不含密钥和真实聊天内容。
这证明部署来源与本轮检查通过，不代表所有实验工作区已整合、天气城市范围已扩展或既有模型质量问题已关闭。
