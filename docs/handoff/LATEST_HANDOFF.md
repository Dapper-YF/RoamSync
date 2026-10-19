# Latest Handoff

## Snapshot
2026-10-19 自然旅行助手A—E隔离集成，总体PARTIAL，未合并或部署。
目录E:/Study/RoamSync-natural-assistant-20261019；分支
codex/natural-assistant-integration-20261019，基线1ce7e5d。
唯一正式源码仍E:/Study/RoamSync，HEAD25a62cb；其README/nginx及旧文件保持。

## Current Freeze / Rehearsal Status
VERIFIED：共同正式写保护复验；路线GET不改正式时间，POST默认仅刷新证据，明确授权
才修复真实重叠，不压缩已有间隔。新增有限TripArrangementItem关系表0037，保留未排程/
备选/撤销/明确留白，Activity独占精确时间；转换/来源/版本/Accept同事务校验。
自然助手预览采用后才建Trip，普通咨询不创建；页面与对话共享版本化结果。
旧Graph/Validator/Accept保留，复杂修改不直接应用。新Web默认入口AI助手＋我的安排。
范围：日期明确单城市1—3天；未新增通用任务中心、Android或商业平台能力。

## Prior milestone baseline (before shadow split)
A 2f2def5；B 7468363；C 739ef56；D ed6ea2d；E见当前分支后续提交。
基于正式写保护评审1ce7e5d，不要再次应用等价7b67f68。
正式3000与生产数据库均未改动，迁移只在独立tmpfs测试PG执行。

## Prior verification
MEASURED：最终Windows后端1316 passed/1 skipped；Web192通过，类型检查/构建通过。
收藏并发独立库1通过。Linux最终同样1316通过/1跳过（release-linux.xml）。
真实模型glm-5.3-flash＋AMap：咨询/采用/交叉修改通过；另一次真实局部冲突Graph/
路线/Validator/用户Accept/刷新通过。合成预约并非真实订票。
同一Trip全段浏览器链未通过：明确排程后，Router重写的“留白保留）”导致保护活动
解析要求澄清“）”。未写坏安排，不能把分段通过称为完整产品GO。
真实反例、截图、模型失败与回归XML见docs/evidence/natural-assistant。
报告docs/NATURAL_ASSISTANT_DELIVERY_20261019.md。

## Prior blockers (historical)
当前优先阻塞是旧意图解析与新自然修改交接，下一步应以同一失败长链建立有界回归，
修复后验证固定预约、未排程决定、留白、不同日期都能保留，不要增加功能或更换容易
成功的演示输入。新增地点研究Provider本轮未配置，失败明确保留；原模型代理失败仅
隔离进程改为直连，生产配置未变。模型存在重复地点/引用错误，Validator阻止采用。
max_walking_minutes不完整仍独立P1；旧编辑部分网络调用持锁，未做负载验收。
无版本旧客户端保护边界仍在。0037含数据降级会丢新事项，空表迁移实验不等于生产回退。

## Interview framing
可证明版本/幂等/锁/回滚、路线事实与排时权限分离、混合精度的单一精确时间源、
有证据的真实Agent局部取舍与用户采用。不可声称全自然语言稳定、真实全链已完成、
生产已发布或任意约束都能满足。
