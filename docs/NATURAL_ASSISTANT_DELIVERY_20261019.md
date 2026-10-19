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

## B—E

待各阶段实际实现和验收后逐项更新；阶段A不代表后续产品体验完成。
