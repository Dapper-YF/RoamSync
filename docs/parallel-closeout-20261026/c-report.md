# C 工程回归与 Web 超时（2026-10-26）

状态：**仅 C 分工完成，整体仍 NO-GO**。共同起点 `8e53fd68d91720f1cf1674a97483e67f9bff8bf3` 是未完成 WIP。产品提交 `098ae6bf4bd6d3ac75395186c8d3902a9f6a7912`；本报告与证据另行提交。未改正式工作区、未部署、未访问封存新题或 Obsidian。

## 修改前失败、根因与最小修改

1. `test_agent_b2_planning_snapshot.py` 的 11 个用例在独立 C 工作树复现失败，均先停在 `activity.position` 缺失（`backend-before.log`）。loader 实际还需要 `duration_minutes/version/status`；补上这些真实 Activity 字段后，假 `scalars()` 又把新的 `TripArrangementItem` 查询错送成 PlaceCandidate（`backend-after1.log`）。最终 fixture 按 DayPlan、PlaceCandidate、TripArrangementItem 精确分流，并验证冻结快照中的位置、时长、版本和状态。没有给真实排序设置默认零。
2. 独立 DB 中 `test_quantity_request_changes_whole_trip_without_searching_for_numbered_places` 复现 `duration_expression_unsupported`（`quantity-before.log`）。兜底正则把“增加1个景点/增加2个景点”的数量错当缺单位分钟。binder 现在仅剥离明确的景点/景区计数，再检查余下文本；同一操作混用时长与景点数仍澄清。新增负例覆盖“第一项增加15”、未知“公里”、时长与计数混合；已保存目标增加15分钟仍精确绑定 60→75。
3. Stage5 原始 `photos-web-full.log` 是 49 文件并发下导航用例 5000ms 超时，272/273 通过。原始隔离复核关键用例 3032ms，历史 `maxWorkers=2` 全量 273/273 通过。C 工作树修改前的定向复核关键用例 3963ms，距 5000ms 很近；`DiscoveryApp` 首屏加载宽路由树、Vitest 默认多文件并发形成 CPU 争用是有依据的推断，尚无逐阶段 CPU 剖析证据。等待条件本身是 URL 改变与仓库搜索调用，并非后端导航轮询；没有重造后端屏障。把 `maxWorkers: 2` 固定到 `web/vite.config.ts`，保留原 5000ms 预算和导航断言。C 工作树按配置定向两文件 7/7，通过时导航关键用例 2795ms。**本次没有重跑 49 文件全量，不能称当前完整 Web 已通过。**

## 修改后验证

- Windows Python 3.14.3、`E:/Study/RoamSync/backend/.venv/Scripts/python.exe`、`PYTHONUTF8=1`、SelectorEventLoopPolicy；独立 `127.0.0.1:15435/roamsync_s6_c_regression_20261026_test`，从空库建表。定向快照 11、Stage6 绑定 8、数量回归 2，**21 passed / 0 failed / 0 skipped，5.27s**，详见 `backend-after-final.log/xml`。测试用了 `--legacy-unit-estimates` 供 demo reset 在无 AMap key 的测试环境生成演示路线；不代表真实 AMap。
- Web `pnpm exec vitest run src/discovery/DiscoveryNavigation.test.tsx src/journeys/HandbookPhotoLoading.test.tsx`：**7 passed / 0 failed，12.36s 总耗时**；`pnpm typecheck` 通过。未跑 Web build 或完整 49 文件。
- 该分工没有调用真实模型或 AMap，也没有浏览器全链。因此不存在可报告的真实模型全文/工具轨迹/模型耗时；这些仍由整合后的正式验收记录。隔离 DB 原本为空，经 `demo/reset` 最终仅有 `trips=1, day_plans=2, activities=5, planning_runs=0, plan_revisions=0`；该过程是测试数据创建，不是正式状态差异证明。
- 四个产品文件的 SHA256 见本分工证据 `MANIFEST.md`。日志完整拷贝到本树证据目录，原始 C 外部目录为 `E:/Study/RoamSync-parallel-evidence-20261026/c`。

## 整合后的工程命令与 40 个 skip

主对话须在正式工作区整合并冻结实际源码后，用独立测试 DB 重新跑全后端、专用库、Web、typecheck、build。`run_tests.py` 是复制改写的 C 工作树/独立 DB harness，**不可直接拿其硬编码路径做正式工作区验收**。最终全后端 wrapper 应明确指向正式 `backend`、15435 上新建且带独立 `test` token 的库，设置 `PYTHONUTF8=1`、Windows SelectorEventLoopPolicy，并以 `--junitxml` 记录结果；Web 使用锁文件的 `pnpm install --frozen-lockfile`、`pnpm test`、`pnpm typecheck`、`pnpm build`。不得把 `--legacy-unit-estimates` 当作真实供应商验收。

Batch3 的 40 skip 不是通过：2 个 `test_agent_b_postgres` 需 `ROAMSYNC_AGENT_B_POSTGRES=1` 且测试代码仅接受独占 `roamsync_agent_b_test` 或 `roamsync_test_write_protection`；37 个 `test_draft_promotion` 需独立 `PROMOTION_TEST_DATABASE_URL` 且库名精确 `promotion_test`；1 个 `test_place_content_postgres` 需 `APP_ENV=test` 且 `DATABASE_URL` 库名精确 `roamsync_test`。三类均应分别新建/隔离、定向运行，不能复用本 C 库或用正式 15432。需要主对话协调专用库占用与最终全量时间。

剩余阻断：整体 Batch3 尚有 B 负责的开园分类失败及产品真实模型链/独立封存验收；当前 C 的 Web CPU 争用原因属于推断，需在正式冻结源码与固定双 worker 配置上完成 49 文件同版复验。架构无新增写端点/业务表，原 Planner→Revision→Validator→Accept 保持不变。
