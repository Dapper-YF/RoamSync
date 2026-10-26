import { expect, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const evidence = resolve("../backend/evals/results/demo_acceptance_20261007");

test("real execution experience and simulated navigation produce an explicitly accepted recovery", async ({ page }) => {
  expect(new URL(test.info().project.use.baseURL!).port).toBe("3001");
  const lifecycle = JSON.parse(readFileSync(resolve(evidence, "lifecycle.json"), "utf8"));
  expect(lifecycle.status).toBe("formalized_execution_pending");
  const trip = lifecycle.trip_id;
  const resume = process.env.ROAMSYNC_EXECUTION_RESUME === "1";
  const report: Record<string, any> = resume ? JSON.parse(readFileSync(resolve(evidence, "execution.json"), "utf8")) : { status: "in_progress", trip_id: trip, isolated: true, mock: false, navigation_input: "simulation_not_real_device_gps", observations: [] };
  report.status = "in_progress"; delete report.error;
  const save = () => writeFileSync(resolve(evidence, "execution.json"), JSON.stringify(report, null, 2));
  const get = async (path: string) => {
    const response = await page.request.get(`/api/v1/${path}`);
    expect(response.ok()).toBeTruthy(); return response.json();
  };
  const post = async (path: string, data: any) => {
    const response = await page.request.post(`/api/v1/${path}`, { data });
    expect(response.ok(), await response.text()).toBeTruthy(); return response.json();
  };
  try {
    if (!resume) report.before = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`) };
    await page.goto(`/trips/${trip}/planner`);
    if (!report.experience_after) {
    await expect(page.getByRole("button", { name: "开始行程", exact: true })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "开始行程", exact: true }).click();
    await expect(page.getByRole("button", { name: "我已到达", exact: true })).toBeVisible({ timeout: 30_000 });
    report.started = await get(`trips/${trip}/execution-progress`); save();
    expect(report.started.execution.status).toBe("in_progress");
    await page.getByRole("button", { name: "我已到达", exact: true }).click();
    await expect(page.getByRole("button", { name: "开始游玩", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "开始游玩", exact: true }).click();
    await expect(page.getByRole("button", { name: "再待 30 分钟", exact: true })).toBeVisible();
    report.experience_before = await get(`trips/${trip}/execution-progress`);
    await page.getByRole("button", { name: "再待 30 分钟", exact: true }).click();
    await expect.poll(async () => (await get(`trips/${trip}/execution-progress`)).current_activity_experience.total_extension_minutes).toBe(30);
    report.experience_after = await get(`trips/${trip}/execution-progress`); save();
    }
    if (!report.departed) {
    const experience = report.experience_after.current_activity_experience;
    const current = report.experience_after.execution.activities.find((a: any) => a.activity_id === experience.activity_id);
    expect(current.status).toBe("in_progress");
    expect((await get(`trips/${trip}/execution-progress`)).current_activity_experience.total_extension_minutes).toBe(30);
    expect(Date.parse(report.experience_after.current_activity_experience.projected_end_at) - Date.parse(report.experience_before.current_activity_experience.projected_end_at)).toBe(30 * 60_000);
    expect(report.experience_after.experience_impact).toBeTruthy();
    const schedule = (days: any[]) => days.map(d => ({ ...d, activities: d.activities.map(({ status, updated_at, ...a }: any) => a) }));
    expect(schedule(await get(`trips/${trip}/days`))).toEqual(schedule(report.before.days));
    expect((await get(`trips/${trip}`)).version).toBe(report.before.trip.version);
    await page.screenshot({ path: resolve(evidence, "experience-30.png"), fullPage: true });
    }
    if (!report.departed) {
    await page.getByRole("button", { name: "结束游玩，前往下一站", exact: true }).click();
    await expect.poll(async () => (await get(`trips/${trip}/execution-progress`)).execution.current_activity_id).not.toBe(report.started.execution.current_activity_id);
    report.departed = await get(`trips/${trip}/execution-progress`);
    save();
    }
    if (!report.navigation_start) {
      report.navigation_start = await post(`trips/${trip}/navigation/start`, { expected_itinerary_version: report.before.trip.version });
      report.formal_before_recovery = await get(`trips/${trip}/days`); save();
    }
    let navigation = report.navigation_start.navigation_session;
    let planned = Date.parse(navigation.planned_arrival_at);
    let date = navigation.planned_arrival_at.slice(0, 10);
    // Replay explicit client inputs through real ingestion/detector, never claim real travel/GPS.
    const severe = Date.parse(`${date}T16:30:00+08:00`);
    for (let sequence = report.observations.length + 1; sequence <= 4; sequence++) {
      const eta = sequence === 1 ? planned + 20 * 60_000 : Math.max(severe, planned + 180 * 60_000);
      const input = {
        session_id: navigation.id, itinerary_version: navigation.itinerary_version, sequence,
        observed_at: new Date(Date.now() + sequence * 1000).toISOString(),
        position: navigation.origin, coordinate_system: navigation.coordinate_system,
        location_accuracy_meters: 8, remaining_distance_meters: 1500, remaining_duration_seconds: 1200,
        eta: new Date(eta).toISOString(), route_revision: navigation.route_revision,
        navigation_status: "navigating", source: "simulation",
      };
      const output = await post("navigation-observations", input);
      report.observations.push({ input, output }); save();
    }
    report.disruption = await get(`trips/${trip}/execution-progress`); save();
    if (!report.disruption.active_disruption && !report.navigation_segments) {
      const eligible = report.before.days.find((d: any) => d.activities.length >= 3 && d.date > report.departed.execution.current_date);
      expect(eligible, "Need a later real planned day with mutable downstream activities").toBeTruthy();
      report.navigation_segments = [{ navigation_start: report.navigation_start, observations: report.observations, result: report.disruption }];
      report.accelerated_execution = { label: "compressed_fixture_actions_not_real_visit_durations", steps: [] }; save();
      await post(`navigation-sessions/${navigation.id}/actions`, { action: "complete" });
      const target = eligible.activities[1].id;
      for (let count = 0; count < 12; count++) {
        const current = await get(`trips/${trip}/execution-progress`);
        if (current.execution.current_activity_id === target) break;
        const activity = current.execution.activities.find((a: any) => a.activity_id === current.execution.current_activity_id);
        expect(activity).toBeTruthy();
        if (activity.status === "pending") await post(`trip-executions/${current.execution.id}/actions`, { action: "arrive", activity_id: activity.activity_id });
        if (["pending", "arrived"].includes(activity.status)) await post(`trip-executions/${current.execution.id}/actions`, { action: "start_activity", activity_id: activity.activity_id });
        const completed = await post(`trip-executions/${current.execution.id}/actions`, { action: "complete", activity_id: activity.activity_id });
        report.accelerated_execution.steps.push({ activity_id: activity.activity_id, result: completed }); save();
      }
      expect((await get(`trips/${trip}/execution-progress`)).execution.current_activity_id).toBe(target);
      report.navigation_start = await post(`trips/${trip}/navigation/start`, { expected_itinerary_version: report.before.trip.version });
      report.formal_before_recovery = await get(`trips/${trip}/days`); report.observations = []; save();
      navigation = report.navigation_start.navigation_session; planned = Date.parse(navigation.planned_arrival_at); date = navigation.planned_arrival_at.slice(0, 10);
      for (let sequence = 1; sequence <= 4; sequence++) {
        const eta = sequence === 1 ? planned + 20 * 60_000 : Math.max(Date.parse(`${date}T16:30:00+08:00`), planned + 180 * 60_000);
        const input = { session_id: navigation.id, itinerary_version: navigation.itinerary_version, sequence, observed_at: new Date(Date.now() + sequence * 1000).toISOString(), position: navigation.origin, coordinate_system: navigation.coordinate_system, location_accuracy_meters: 8, remaining_distance_meters: 1500, remaining_duration_seconds: 1200, eta: new Date(eta).toISOString(), route_revision: navigation.route_revision, navigation_status: "navigating", source: "simulation" };
        report.observations.push({ input, output: await post("navigation-observations", input) }); save();
      }
      report.disruption = await get(`trips/${trip}/execution-progress`); save();
    }
    if (process.env.ROAMSYNC_RECOVERY_RETRY === "1" && !report.retry) {
      const previous = await get(`planning-runs/${report.recovery_run_id}`);
      expect(previous.status).toBe("failed");
      expect(report.disruption.active_disruption.id).toBe(previous.disruption_event_id);
      report.retry = await post(`trips/${trip}/planning-runs`, {
        run_type: "replan", user_request: "导航延误已使原安排不可行，请重新生成恢复候选，仅调整尚未完成的活动，等待我确认。",
        disruption_event_id: previous.disruption_event_id,
        selected_day_id: report.disruption.execution.current_day_plan_id,
      });
      report.previous_failed_recovery_run = previous.id; save();
      report.disruption = await get(`trips/${trip}/execution-progress`); save();
    }
    expect(Date.parse(report.disruption.navigation_session.current_eta) - planned).toBeGreaterThan(20 * 60_000);
    expect(report.disruption.active_disruption).toBeTruthy();
    expect(report.disruption.active_recovery_run).toBeTruthy();
    const runId = report.disruption.active_recovery_run.id;
    report.recovery_run_id = runId; save();
    await expect.poll(async () => {
      const run = await get(`planning-runs/${runId}`); report.latest_run = run; save();
      if (["failed", "cancelled", "awaiting_clarification"].includes(run.status)) throw new Error(`Recovery ${run.status}: ${run.error_code ?? JSON.stringify(run.pending_interrupt)}`);
      return run.status;
    }, { timeout: 480_000, intervals: [2000, 5000] }).toBe("awaiting_confirmation");
    report.recovery = await get(`planning-runs/${runId}/revision`);
    expect(report.recovery.validation_result.valid).toBe(true);
    expect(await get(`trips/${trip}/days`)).toEqual(report.formal_before_recovery);
    expect((await get(`trips/${trip}`)).version).toBe(report.before.trip.version);
    await page.reload();
    await expect(page.getByLabel("恢复方案", { exact: true })).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: resolve(evidence, "recovery-candidate.png"), fullPage: true });
    await page.getByRole("button", { name: "采用方案", exact: true }).click();
    await page.getByRole("button", { name: "确认应用", exact: true }).click();
    await expect.poll(async () => (await get(`trips/${trip}`)).version).toBe(report.before.trip.version + 1);
    report.after = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`), progress: await get(`trips/${trip}/execution-progress`) }; save();
    expect((await get(`planning-runs/${runId}`)).status).toBe("accepted");
    const first = report.formal_before_recovery[0].activities[0];
    const { updated_at: beforeUpdated, ...beforeProtected } = first;
    const { updated_at: afterUpdated, ...afterProtected } = report.after.days[0].activities.find((a: any) => a.id === first.id);
    expect(afterProtected).toEqual(beforeProtected);
    expect(report.recovery.difference_summary.planned_total_fen).toBe(report.after.days.flatMap((d: any) => d.activities).filter((a: any) => a.status !== "skipped").reduce((total: number, a: any) => total + a.estimated_cost_fen, 0));
    await page.screenshot({ path: resolve(evidence, "recovery-applied.png"), fullPage: true });
    report.status = "execution_recovery_passed_explanation_pending"; save();
  } catch (error) {
    report.status = "failed"; report.error = error instanceof Error ? error.message : String(error); save(); throw error;
  }
});
