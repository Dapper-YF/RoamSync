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

## C—E

待各阶段实际实现和验收后逐项更新；已完成前置工程不代表后续产品体验完成。
