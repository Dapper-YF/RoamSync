# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: demo-execution.spec.ts >> real execution experience and simulated navigation produce an explicitly accepted recovery
- Location: e2e\demo-execution.spec.ts:7:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: "in_progress"
Received: undefined
```

# Page snapshot

```yaml
- main [ref=e3]:
  - generic [ref=e4]:
    - link "RoamSync TRIPS" [ref=e5] [cursor=pointer]:
      - /url: /trips
      - strong [ref=e10]: RoamSync
      - generic [ref=e11]: TRIPS
    - generic [ref=e12]:
      - generic [ref=e13]: 南京3日之旅
      - generic [ref=e14]: 10月9日 — 10月11日
    - generic [ref=e17]:
      - generic [ref=e22]: 交通
      - combobox "交通" [ref=e23] [cursor=pointer]:
        - option "步行" [selected]
        - option "公交"
        - option "驾车"
    - generic [ref=e24]:
      - generic [ref=e29]:
        - generic [ref=e30]: 预计支出
        - strong [ref=e31]: ¥240
      - generic [ref=e32]: / ¥3,000
    - generic [ref=e33]: 即将出发
    - generic "查看方式" [ref=e34]:
      - button "行程" [pressed] [ref=e35] [cursor=pointer]
      - button "地图" [ref=e36] [cursor=pointer]
    - button "打开旅程总管" [ref=e37] [cursor=pointer]:
      - generic [ref=e40]: 旅程总管
    - link "打开监控台" [ref=e41] [cursor=pointer]:
      - /url: /dev/agent-monitor?trip=2b7f4d91-b776-4154-aee3-c95c0be16e7d
    - link "编辑旅行设置" [ref=e45] [cursor=pointer]:
      - /url: /trips/2b7f4d91-b776-4154-aee3-c95c0be16e7d/edit
  - complementary [ref=e50]:
    - generic [ref=e52]:
      - generic [ref=e53]: DAY PLAN
      - heading "探索南京市" [level=1] [ref=e54]
    - generic [ref=e58]:
      - strong [ref=e59]: 当前没有正在执行的路段
      - paragraph [ref=e60]: 更新于 23:29
    - region "当前活动体验" [ref=e61]:
      - generic [ref=e62]:
        - generic [ref=e63]:
          - generic [ref=e64]: 当前活动
          - strong [ref=e68]: 南京博物院
        - generic [ref=e69]: 正在游玩
      - paragraph [ref=e70]: 延长或结束游玩会重新评估后续行程。
      - generic [ref=e71]:
        - generic [ref=e72]:
          - generic [ref=e73]: 计划停留
          - strong [ref=e74]: 180 分钟
        - generic [ref=e75]:
          - generic [ref=e76]: 已游玩
          - strong [ref=e77]: 0 分钟
        - generic [ref=e78]:
          - generic [ref=e79]: 已延长
          - strong [ref=e80]: 30 分钟
        - generic [ref=e81]:
          - generic [ref=e82]: 预计结束
          - strong [ref=e83]: 02:59
      - generic [ref=e84]:
        - button "再待 15 分钟" [ref=e85] [cursor=pointer]
        - button "再待 30 分钟" [ref=e87] [cursor=pointer]
        - button "再待 60 分钟" [ref=e89] [cursor=pointer]
      - button "结束游玩，前往下一站" [ref=e91] [cursor=pointer]
      - paragraph [ref=e95]: 后续时间余量有所减少，目前仍可继续原计划。最小余量：0 分钟。
    - generic [ref=e96]:
      - strong [ref=e97]: 当天已安排 4 项
      - generic [ref=e98]: 可以继续添加地点，也可以拖拽卡片调整顺序。路线和预算会同步更新。
      - button "让旅程总管规划或调整" [ref=e100] [cursor=pointer]
    - tablist "旅行日期" [ref=e101]:
      - tab "1 10月9日 第 1 天 · 4 项" [selected] [ref=e102] [cursor=pointer]:
        - generic [ref=e103]: "1"
        - generic [ref=e104]:
          - strong [ref=e105]: 10月9日
          - generic [ref=e106]: 第 1 天 · 4 项
      - tab "2 10月10日 第 2 天 · 2 项" [ref=e107] [cursor=pointer]:
        - generic [ref=e108]: "2"
        - generic [ref=e109]:
          - strong [ref=e110]: 10月10日
          - generic [ref=e111]: 第 2 天 · 2 项
      - tab "3 10月11日 第 3 天 · 2 项" [ref=e112] [cursor=pointer]:
        - generic [ref=e113]: "3"
        - generic [ref=e114]:
          - strong [ref=e115]: 10月11日
          - generic [ref=e116]: 第 3 天 · 2 项
    - generic [ref=e118]:
      - generic [ref=e123]: 当天预计
      - strong [ref=e124]: ¥140
      - generic [ref=e125]: 剩余 ¥860
    - list [ref=e129]:
      - listitem [ref=e130]:
        - article [ref=e131]:
          - button "拖动 南京博物院" [ref=e132]
          - button "1 09:00 180 分钟 南京博物院 玄武区 ¥30" [ref=e140] [cursor=pointer]:
            - generic [ref=e141]: "1"
            - generic [ref=e142]:
              - generic [ref=e143]:
                - generic [ref=e144]: 09:00
                - generic [ref=e148]: 180 分钟
              - strong [ref=e149]: 南京博物院
              - paragraph [ref=e150]: 玄武区
            - generic [ref=e154]: ¥30
        - generic [ref=e155]: 步行 17 分钟 · 1.2 km
      - listitem [ref=e162]:
        - article [ref=e163]:
          - button "拖动 南京明故宫遗址公园" [ref=e164]
          - button "2 12:40 90 分钟 南京明故宫遗址公园 玄武区 ¥30" [ref=e172] [cursor=pointer]:
            - generic [ref=e173]: "2"
            - generic [ref=e174]:
              - generic [ref=e175]:
                - generic [ref=e176]: 12:40
                - generic [ref=e180]: 90 分钟
              - strong [ref=e181]: 南京明故宫遗址公园
              - paragraph [ref=e182]: 玄武区
            - generic [ref=e186]: ¥30
        - generic [ref=e187]: 公交 38 分钟 · 4.0 km
      - listitem [ref=e194]:
        - article [ref=e195]:
          - button "拖动 红庙" [ref=e196]
          - button "3 16:54 90 分钟 红庙 玄武区 ¥50" [ref=e204] [cursor=pointer]:
            - generic [ref=e205]: "3"
            - generic [ref=e206]:
              - generic [ref=e207]:
                - generic [ref=e208]: 16:54
                - generic [ref=e212]: 90 分钟
              - strong [ref=e213]: 红庙
              - paragraph [ref=e214]: 玄武区
            - generic [ref=e218]: ¥50
        - generic [ref=e219]: 公交 36 分钟 · 4.2 km
      - listitem [ref=e226]:
        - article [ref=e227]:
          - button "拖动 夫子庙" [ref=e228]
          - button "4 19:00 120 分钟 夫子庙 秦淮区 ¥30" [ref=e236] [cursor=pointer]:
            - generic [ref=e237]: "4"
            - generic [ref=e238]:
              - generic [ref=e239]:
                - generic [ref=e240]: 19:00
                - generic [ref=e244]: 120 分钟
              - strong [ref=e245]: 夫子庙
              - paragraph [ref=e246]: 秦淮区
            - generic [ref=e250]: ¥30
    - status [ref=e251]
    - button "添加地点" [ref=e252] [cursor=pointer]
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | import { readFileSync, writeFileSync } from "node:fs";
  3  | import { resolve } from "node:path";
  4  | 
  5  | const evidence = resolve("../backend/evals/results/demo_acceptance_20261007");
  6  | 
  7  | test("real execution experience and simulated navigation produce an explicitly accepted recovery", async ({ page }) => {
  8  |   expect(new URL(test.info().project.use.baseURL!).port).toBe("3001");
  9  |   const lifecycle = JSON.parse(readFileSync(resolve(evidence, "lifecycle.json"), "utf8"));
  10 |   expect(lifecycle.status).toBe("formalized_execution_pending");
  11 |   const trip = lifecycle.trip_id;
  12 |   const report: Record<string, any> = { status: "in_progress", trip_id: trip, isolated: true, mock: false, navigation_input: "simulation_not_real_device_gps", observations: [] };
  13 |   const save = () => writeFileSync(resolve(evidence, "execution.json"), JSON.stringify(report, null, 2));
  14 |   const get = async (path: string) => {
  15 |     const response = await page.request.get(`/api/v1/${path}`);
  16 |     expect(response.ok()).toBeTruthy(); return response.json();
  17 |   };
  18 |   const post = async (path: string, data: any) => {
  19 |     const response = await page.request.post(`/api/v1/${path}`, { data });
  20 |     expect(response.ok(), await response.text()).toBeTruthy(); return response.json();
  21 |   };
  22 |   try {
  23 |     report.before = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`) };
  24 |     await page.goto(`/trips/${trip}/planner`);
  25 |     await expect(page.getByRole("button", { name: "开始行程", exact: true })).toBeVisible({ timeout: 30_000 });
  26 |     await page.getByRole("button", { name: "开始行程", exact: true }).click();
  27 |     await expect(page.getByRole("button", { name: "我已到达", exact: true })).toBeVisible({ timeout: 30_000 });
  28 |     report.started = await get(`trips/${trip}/execution-progress`); save();
  29 |     expect(report.started.execution.status).toBe("in_progress");
  30 |     await page.getByRole("button", { name: "我已到达", exact: true }).click();
  31 |     await expect(page.getByRole("button", { name: "开始游玩", exact: true })).toBeVisible();
  32 |     await page.getByRole("button", { name: "开始游玩", exact: true }).click();
  33 |     await expect(page.getByRole("button", { name: "再待 30 分钟", exact: true })).toBeVisible();
  34 |     report.experience_before = await get(`trips/${trip}/execution-progress`);
  35 |     await page.getByRole("button", { name: "再待 30 分钟", exact: true }).click();
  36 |     await expect.poll(async () => (await get(`trips/${trip}/execution-progress`)).current_activity_experience.total_extension_minutes).toBe(30);
  37 |     report.experience_after = await get(`trips/${trip}/execution-progress`); save();
> 38 |     expect(report.experience_after.current_activity_experience.status).toBe("in_progress");
     |                                                                        ^ Error: expect(received).toBe(expected) // Object.is equality
  39 |     expect(Date.parse(report.experience_after.current_activity_experience.projected_end_at) - Date.parse(report.experience_before.current_activity_experience.projected_end_at)).toBe(30 * 60_000);
  40 |     expect(report.experience_after.experience_impact).toBeTruthy();
  41 |     expect(await get(`trips/${trip}/days`)).toEqual(report.before.days);
  42 |     expect((await get(`trips/${trip}`)).version).toBe(report.before.trip.version);
  43 |     await page.screenshot({ path: resolve(evidence, "experience-30.png"), fullPage: true });
  44 |     await page.getByRole("button", { name: "结束游玩，前往下一站", exact: true }).click();
  45 |     await expect.poll(async () => (await get(`trips/${trip}/execution-progress`)).execution.current_activity_id).not.toBe(report.started.execution.current_activity_id);
  46 |     report.departed = await get(`trips/${trip}/execution-progress`);
  47 |     report.navigation_start = await post(`trips/${trip}/navigation/start`, { expected_itinerary_version: report.before.trip.version });
  48 |     const navigation = report.navigation_start.navigation_session;
  49 |     const planned = Date.parse(navigation.planned_arrival_at);
  50 |     const date = navigation.planned_arrival_at.slice(0, 10);
  51 |     // Replay explicit client inputs through real ingestion/detector, never claim real travel/GPS.
  52 |     const severe = Date.parse(`${date}T16:30:00+08:00`);
  53 |     for (let sequence = 1; sequence <= 4; sequence++) {
  54 |       const eta = sequence === 1 ? planned + 20 * 60_000 : Math.max(severe, planned + 180 * 60_000);
  55 |       const input = {
  56 |         session_id: navigation.id, itinerary_version: navigation.itinerary_version, sequence,
  57 |         observed_at: new Date(Date.now() + sequence * 1000).toISOString(),
  58 |         position: navigation.origin, coordinate_system: navigation.coordinate_system,
  59 |         location_accuracy_meters: 8, remaining_distance_meters: 1500, remaining_duration_seconds: 1200,
  60 |         eta: new Date(eta).toISOString(), route_revision: navigation.route_revision,
  61 |         navigation_status: "navigating", source: "simulation",
  62 |       };
  63 |       const output = await post("navigation-observations", input);
  64 |       report.observations.push({ input, output }); save();
  65 |     }
  66 |     report.disruption = await get(`trips/${trip}/execution-progress`); save();
  67 |     expect(report.disruption.delay_minutes).toBeGreaterThan(20);
  68 |     expect(report.disruption.active_disruption).toBeTruthy();
  69 |     expect(report.disruption.active_recovery_run).toBeTruthy();
  70 |     const runId = report.disruption.active_recovery_run.id;
  71 |     report.recovery_run_id = runId; save();
  72 |     await expect.poll(async () => {
  73 |       const run = await get(`planning-runs/${runId}`); report.latest_run = run; save();
  74 |       if (["failed", "cancelled", "awaiting_clarification"].includes(run.status)) throw new Error(`Recovery ${run.status}: ${run.error_code ?? JSON.stringify(run.pending_interrupt)}`);
  75 |       return run.status;
  76 |     }, { timeout: 480_000, intervals: [2000, 5000] }).toBe("awaiting_confirmation");
  77 |     report.recovery = await get(`planning-runs/${runId}/revision`);
  78 |     expect(report.recovery.validation_result.valid).toBe(true);
  79 |     expect(await get(`trips/${trip}/days`)).toEqual(report.before.days);
  80 |     expect((await get(`trips/${trip}`)).version).toBe(report.before.trip.version);
  81 |     await page.reload();
  82 |     await expect(page.getByLabel("恢复方案", { exact: true })).toBeVisible({ timeout: 30_000 });
  83 |     await page.screenshot({ path: resolve(evidence, "recovery-candidate.png"), fullPage: true });
  84 |     await page.getByRole("button", { name: "采用方案", exact: true }).click();
  85 |     await page.getByRole("button", { name: "确认应用", exact: true }).click();
  86 |     await expect.poll(async () => (await get(`trips/${trip}`)).version).toBe(report.before.trip.version + 1);
  87 |     report.after = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`), progress: await get(`trips/${trip}/execution-progress`) }; save();
  88 |     expect((await get(`planning-runs/${runId}`)).status).toBe("accepted");
  89 |     const first = report.before.days[0].activities[0];
  90 |     expect(report.after.days[0].activities.find((a: any) => a.id === first.id)).toEqual(first);
  91 |     await page.screenshot({ path: resolve(evidence, "recovery-applied.png"), fullPage: true });
  92 |     report.status = "execution_recovery_passed_explanation_pending"; save();
  93 |   } catch (error) {
  94 |     report.status = "failed"; report.error = error instanceof Error ? error.message : String(error); save(); throw error;
  95 |   }
  96 | });
  97 | 
```