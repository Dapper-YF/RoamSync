# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: demo-execution.spec.ts >> real execution experience and simulated navigation produce an explicitly accepted recovery
- Location: e2e\demo-execution.spec.ts:7:1

# Error details

```
Error: expect(received).toEqual(expected) // deep equality

- Expected  - 1
+ Received  + 1

@@ -27,8 +27,8 @@
      "queried_at": "2026-10-07T15:22:35.305380Z",
      "title": "高德地点搜索：南京博物院",
      "url": "https://www.amap.com/search?id=B001907TGR",
    },
    "status": "completed",
-   "updated_at": "2026-10-07T15:30:57.444893Z",
+   "updated_at": "2026-10-07T15:38:09.469841Z",
    "version": 1,
  }
```

# Page snapshot

```yaml
- main [ref=f1e3]:
  - generic [ref=f1e4]:
    - link "RoamSync TRIPS" [ref=f1e5] [cursor=pointer]:
      - /url: /trips
      - strong [ref=f1e10]: RoamSync
      - generic [ref=f1e11]: TRIPS
    - generic [ref=f1e12]:
      - generic [ref=f1e13]: 南京3日之旅
      - generic [ref=f1e14]: 10月9日 — 10月11日
    - generic [ref=f1e17]:
      - generic [ref=f1e22]: 交通
      - combobox "交通" [ref=f1e23] [cursor=pointer]:
        - option "步行" [selected]
        - option "公交"
        - option "驾车"
    - generic [ref=f1e24]:
      - generic [ref=f1e29]:
        - generic [ref=f1e30]: 预计支出
        - strong [ref=f1e31]: ¥240
      - generic [ref=f1e32]: / ¥3,000
    - generic [ref=f1e33]: 即将出发
    - generic "查看方式" [ref=f1e34]:
      - button "行程" [pressed] [ref=f1e35] [cursor=pointer]
      - button "地图" [ref=f1e36] [cursor=pointer]
    - button "打开旅程总管" [ref=f1e37] [cursor=pointer]:
      - generic [ref=f1e40]: 旅程总管
    - link "打开监控台" [ref=f1e41] [cursor=pointer]:
      - /url: /dev/agent-monitor?trip=2b7f4d91-b776-4154-aee3-c95c0be16e7d
    - link "编辑旅行设置" [ref=f1e45] [cursor=pointer]:
      - /url: /trips/2b7f4d91-b776-4154-aee3-c95c0be16e7d/edit
  - generic [ref=f1e49]:
    - status [ref=f1e50]:
      - generic [ref=f1e51]: 恢复方案已应用，正式行程已更新。
      - button "关闭行程更新提示" [ref=f1e52] [cursor=pointer]: 关闭
    - complementary [ref=f1e53]:
      - generic [ref=f1e55]:
        - generic [ref=f1e56]: DAY PLAN
        - heading "探索南京市" [level=1] [ref=f1e57]
      - generic [ref=f1e61]:
        - strong [ref=f1e62]: 当前没有正在执行的路段
        - paragraph [ref=f1e63]: 更新于 23:38
      - region "当前活动体验" [ref=f1e64]:
        - generic [ref=f1e65]:
          - generic [ref=f1e66]:
            - generic [ref=f1e67]: 当前活动
            - strong [ref=f1e71]: 南京明故宫遗址公园
          - generic [ref=f1e72]: 即将抵达
        - paragraph [ref=f1e73]: 到达后即可开始记录实际游玩时间。
        - generic [ref=f1e74]:
          - generic [ref=f1e75]:
            - generic [ref=f1e76]: 计划停留
            - strong [ref=f1e77]: 90 分钟
          - generic [ref=f1e78]:
            - generic [ref=f1e79]: 已延长
            - strong [ref=f1e80]: 0 分钟
          - generic [ref=f1e81]:
            - generic [ref=f1e82]: 预计结束
            - strong [ref=f1e83]: —
        - button "我已到达" [ref=f1e84] [cursor=pointer]
      - generic [ref=f1e88]:
        - strong [ref=f1e89]: 当天已安排 4 项
        - generic [ref=f1e90]: 可以继续添加地点，也可以拖拽卡片调整顺序。路线和预算会同步更新。
        - button "让旅程总管规划或调整" [ref=f1e92] [cursor=pointer]
      - tablist "旅行日期" [ref=f1e93]:
        - tab "1 10月9日 第 1 天 · 4 项" [selected] [ref=f1e94] [cursor=pointer]:
          - generic [ref=f1e95]: "1"
          - generic [ref=f1e96]:
            - strong [ref=f1e97]: 10月9日
            - generic [ref=f1e98]: 第 1 天 · 4 项
        - tab "2 10月10日 第 2 天 · 2 项" [ref=f1e99] [cursor=pointer]:
          - generic [ref=f1e100]: "2"
          - generic [ref=f1e101]:
            - strong [ref=f1e102]: 10月10日
            - generic [ref=f1e103]: 第 2 天 · 2 项
        - tab "3 10月11日 第 3 天 · 2 项" [ref=f1e104] [cursor=pointer]:
          - generic [ref=f1e105]: "3"
          - generic [ref=f1e106]:
            - strong [ref=f1e107]: 10月11日
            - generic [ref=f1e108]: 第 3 天 · 2 项
      - generic [ref=f1e110]:
        - generic [ref=f1e115]: 当天预计
        - strong [ref=f1e116]: ¥140
        - generic [ref=f1e117]: 剩余 ¥860
      - list [ref=f1e121]:
        - listitem [ref=f1e122]:
          - article [ref=f1e123]:
            - button "拖动 南京博物院" [ref=f1e124]
            - button "1 09:00 180 分钟 南京博物院 玄武区 已完成" [ref=f1e132] [cursor=pointer]:
              - generic [ref=f1e133]: "1"
              - generic [ref=f1e134]:
                - generic [ref=f1e135]:
                  - generic [ref=f1e136]: 09:00
                  - generic [ref=f1e140]: 180 分钟
                - strong [ref=f1e141]: 南京博物院
                - paragraph [ref=f1e142]: 玄武区
              - generic [ref=f1e146]: 已完成
          - generic [ref=f1e147]: 步行 17 分钟 · 1.2 km
        - listitem [ref=f1e154]:
          - article [ref=f1e155]:
            - button "拖动 南京明故宫遗址公园" [ref=f1e156]
            - button "2 12:40 90 分钟 南京明故宫遗址公园 玄武区 ¥30" [ref=f1e164] [cursor=pointer]:
              - generic [ref=f1e165]: "2"
              - generic [ref=f1e166]:
                - generic [ref=f1e167]:
                  - generic [ref=f1e168]: 12:40
                  - generic [ref=f1e172]: 90 分钟
                - strong [ref=f1e173]: 南京明故宫遗址公园
                - paragraph [ref=f1e174]: 玄武区
              - generic [ref=f1e178]: ¥30
          - generic [ref=f1e179]: 公交 38 分钟 · 4.0 km
        - listitem [ref=f1e186]:
          - article [ref=f1e187]:
            - button "拖动 红庙" [ref=f1e188]
            - button "3 18:45 35 分钟 红庙 玄武区 ¥50" [ref=f1e196] [cursor=pointer]:
              - generic [ref=f1e197]: "3"
              - generic [ref=f1e198]:
                - generic [ref=f1e199]:
                  - generic [ref=f1e200]: 18:45
                  - generic [ref=f1e204]: 35 分钟
                - strong [ref=f1e205]: 红庙
                - paragraph [ref=f1e206]: 玄武区
              - generic [ref=f1e210]: ¥50
          - generic [ref=f1e211]: 公交 36 分钟 · 4.2 km
        - listitem [ref=f1e218]:
          - article [ref=f1e219]:
            - button "拖动 夫子庙" [ref=f1e220]
            - button "4 20:05 55 分钟 夫子庙 秦淮区 ¥30" [ref=f1e228] [cursor=pointer]:
              - generic [ref=f1e229]: "4"
              - generic [ref=f1e230]:
                - generic [ref=f1e231]:
                  - generic [ref=f1e232]: 20:05
                  - generic [ref=f1e236]: 55 分钟
                - strong [ref=f1e237]: 夫子庙
                - paragraph [ref=f1e238]: 秦淮区
              - generic [ref=f1e242]: ¥30
      - status [ref=f1e243]
      - button "添加地点" [ref=f1e244] [cursor=pointer]
```

# Test source

```ts
  18  |     expect(response.ok()).toBeTruthy(); return response.json();
  19  |   };
  20  |   const post = async (path: string, data: any) => {
  21  |     const response = await page.request.post(`/api/v1/${path}`, { data });
  22  |     expect(response.ok(), await response.text()).toBeTruthy(); return response.json();
  23  |   };
  24  |   try {
  25  |     if (!resume) report.before = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`) };
  26  |     await page.goto(`/trips/${trip}/planner`);
  27  |     if (!report.experience_after) {
  28  |     await expect(page.getByRole("button", { name: "开始行程", exact: true })).toBeVisible({ timeout: 30_000 });
  29  |     await page.getByRole("button", { name: "开始行程", exact: true }).click();
  30  |     await expect(page.getByRole("button", { name: "我已到达", exact: true })).toBeVisible({ timeout: 30_000 });
  31  |     report.started = await get(`trips/${trip}/execution-progress`); save();
  32  |     expect(report.started.execution.status).toBe("in_progress");
  33  |     await page.getByRole("button", { name: "我已到达", exact: true }).click();
  34  |     await expect(page.getByRole("button", { name: "开始游玩", exact: true })).toBeVisible();
  35  |     await page.getByRole("button", { name: "开始游玩", exact: true }).click();
  36  |     await expect(page.getByRole("button", { name: "再待 30 分钟", exact: true })).toBeVisible();
  37  |     report.experience_before = await get(`trips/${trip}/execution-progress`);
  38  |     await page.getByRole("button", { name: "再待 30 分钟", exact: true }).click();
  39  |     await expect.poll(async () => (await get(`trips/${trip}/execution-progress`)).current_activity_experience.total_extension_minutes).toBe(30);
  40  |     report.experience_after = await get(`trips/${trip}/execution-progress`); save();
  41  |     }
  42  |     if (!report.departed) {
  43  |     const experience = report.experience_after.current_activity_experience;
  44  |     const current = report.experience_after.execution.activities.find((a: any) => a.activity_id === experience.activity_id);
  45  |     expect(current.status).toBe("in_progress");
  46  |     expect((await get(`trips/${trip}/execution-progress`)).current_activity_experience.total_extension_minutes).toBe(30);
  47  |     expect(Date.parse(report.experience_after.current_activity_experience.projected_end_at) - Date.parse(report.experience_before.current_activity_experience.projected_end_at)).toBe(30 * 60_000);
  48  |     expect(report.experience_after.experience_impact).toBeTruthy();
  49  |     const schedule = (days: any[]) => days.map(d => ({ ...d, activities: d.activities.map(({ status, updated_at, ...a }: any) => a) }));
  50  |     expect(schedule(await get(`trips/${trip}/days`))).toEqual(schedule(report.before.days));
  51  |     expect((await get(`trips/${trip}`)).version).toBe(report.before.trip.version);
  52  |     await page.screenshot({ path: resolve(evidence, "experience-30.png"), fullPage: true });
  53  |     }
  54  |     if (!report.departed) {
  55  |     await page.getByRole("button", { name: "结束游玩，前往下一站", exact: true }).click();
  56  |     await expect.poll(async () => (await get(`trips/${trip}/execution-progress`)).execution.current_activity_id).not.toBe(report.started.execution.current_activity_id);
  57  |     report.departed = await get(`trips/${trip}/execution-progress`);
  58  |     save();
  59  |     }
  60  |     if (!report.navigation_start) {
  61  |       report.navigation_start = await post(`trips/${trip}/navigation/start`, { expected_itinerary_version: report.before.trip.version });
  62  |       report.formal_before_recovery = await get(`trips/${trip}/days`); save();
  63  |     }
  64  |     const navigation = report.navigation_start.navigation_session;
  65  |     const planned = Date.parse(navigation.planned_arrival_at);
  66  |     const date = navigation.planned_arrival_at.slice(0, 10);
  67  |     // Replay explicit client inputs through real ingestion/detector, never claim real travel/GPS.
  68  |     const severe = Date.parse(`${date}T16:30:00+08:00`);
  69  |     for (let sequence = report.observations.length + 1; sequence <= 4; sequence++) {
  70  |       const eta = sequence === 1 ? planned + 20 * 60_000 : Math.max(severe, planned + 180 * 60_000);
  71  |       const input = {
  72  |         session_id: navigation.id, itinerary_version: navigation.itinerary_version, sequence,
  73  |         observed_at: new Date(Date.now() + sequence * 1000).toISOString(),
  74  |         position: navigation.origin, coordinate_system: navigation.coordinate_system,
  75  |         location_accuracy_meters: 8, remaining_distance_meters: 1500, remaining_duration_seconds: 1200,
  76  |         eta: new Date(eta).toISOString(), route_revision: navigation.route_revision,
  77  |         navigation_status: "navigating", source: "simulation",
  78  |       };
  79  |       const output = await post("navigation-observations", input);
  80  |       report.observations.push({ input, output }); save();
  81  |     }
  82  |     report.disruption = await get(`trips/${trip}/execution-progress`); save();
  83  |     if (process.env.ROAMSYNC_RECOVERY_RETRY === "1" && !report.retry) {
  84  |       const previous = await get(`planning-runs/${report.recovery_run_id}`);
  85  |       expect(previous.status).toBe("failed");
  86  |       expect(report.disruption.active_disruption.id).toBe(previous.disruption_event_id);
  87  |       report.retry = await post(`trips/${trip}/planning-runs`, {
  88  |         run_type: "replan", user_request: "导航延误已使原安排不可行，请重新生成恢复候选，仅调整尚未完成的活动，等待我确认。",
  89  |         disruption_event_id: previous.disruption_event_id,
  90  |         selected_day_id: report.disruption.execution.current_day_plan_id,
  91  |       });
  92  |       report.previous_failed_recovery_run = previous.id; save();
  93  |       report.disruption = await get(`trips/${trip}/execution-progress`); save();
  94  |     }
  95  |     expect(Date.parse(report.disruption.navigation_session.current_eta) - planned).toBeGreaterThan(20 * 60_000);
  96  |     expect(report.disruption.active_disruption).toBeTruthy();
  97  |     expect(report.disruption.active_recovery_run).toBeTruthy();
  98  |     const runId = report.disruption.active_recovery_run.id;
  99  |     report.recovery_run_id = runId; save();
  100 |     await expect.poll(async () => {
  101 |       const run = await get(`planning-runs/${runId}`); report.latest_run = run; save();
  102 |       if (["failed", "cancelled", "awaiting_clarification"].includes(run.status)) throw new Error(`Recovery ${run.status}: ${run.error_code ?? JSON.stringify(run.pending_interrupt)}`);
  103 |       return run.status;
  104 |     }, { timeout: 480_000, intervals: [2000, 5000] }).toBe("awaiting_confirmation");
  105 |     report.recovery = await get(`planning-runs/${runId}/revision`);
  106 |     expect(report.recovery.validation_result.valid).toBe(true);
  107 |     expect(await get(`trips/${trip}/days`)).toEqual(report.formal_before_recovery);
  108 |     expect((await get(`trips/${trip}`)).version).toBe(report.before.trip.version);
  109 |     await page.reload();
  110 |     await expect(page.getByLabel("恢复方案", { exact: true })).toBeVisible({ timeout: 30_000 });
  111 |     await page.screenshot({ path: resolve(evidence, "recovery-candidate.png"), fullPage: true });
  112 |     await page.getByRole("button", { name: "采用方案", exact: true }).click();
  113 |     await page.getByRole("button", { name: "确认应用", exact: true }).click();
  114 |     await expect.poll(async () => (await get(`trips/${trip}`)).version).toBe(report.before.trip.version + 1);
  115 |     report.after = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`), progress: await get(`trips/${trip}/execution-progress`) }; save();
  116 |     expect((await get(`planning-runs/${runId}`)).status).toBe("accepted");
  117 |     const first = report.formal_before_recovery[0].activities[0];
> 118 |     expect(report.after.days[0].activities.find((a: any) => a.id === first.id)).toEqual(first);
      |                                                                                 ^ Error: expect(received).toEqual(expected) // deep equality
  119 |     await page.screenshot({ path: resolve(evidence, "recovery-applied.png"), fullPage: true });
  120 |     report.status = "execution_recovery_passed_explanation_pending"; save();
  121 |   } catch (error) {
  122 |     report.status = "failed"; report.error = error instanceof Error ? error.message : String(error); save(); throw error;
  123 |   }
  124 | });
  125 | 
```