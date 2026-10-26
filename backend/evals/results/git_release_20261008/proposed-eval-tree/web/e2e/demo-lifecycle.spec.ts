import { expect, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const evidence = resolve("../backend/evals/results/demo_acceptance_20261007");

test("lifecycle revises an unaccepted candidate then formalizes only on explicit approval", async ({ page }) => {
  expect(new URL(test.info().project.use.baseURL!).port).toBe("3001");
  const earlier = JSON.parse(readFileSync(resolve(evidence, "conversation.json"), "utf8"));
  expect(earlier.status).toBe("candidate_gate_passed_lifecycle_pending");
  const resume = process.env.ROAMSYNC_LIFECYCLE_RESUME === "1";
  const report: Record<string, any> = resume
    ? JSON.parse(readFileSync(resolve(evidence, "lifecycle.json"), "utf8"))
    : { status: "in_progress", trip_id: earlier.trip_id, stages: [], mock: false, isolated: true };
  report.status = "in_progress";
  delete report.error;
  const save = () => writeFileSync(resolve(evidence, "lifecycle.json"), JSON.stringify(report, null, 2));
  const trip = earlier.trip_id;
  const get = async (path: string) => {
    const r = await page.request.get(`/api/v1/${path}`);
    expect(r.ok()).toBeTruthy();
    return r.json();
  };
  try {
    const beforeTrip = await get(`trips/${trip}`);
    const beforeDays = await get(`trips/${trip}/days`);
    report.before = { trip: beforeTrip, days: beforeDays };
    expect(beforeDays.flatMap((d: any) => d.activities)).toHaveLength(0);
    await page.goto(`/dev/agent-conversation/${trip}`);
    if (!resume) await expect(page.locator(".ai-proposal").filter({ hasText: "候选方案" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("告诉旅程总管")).toBeEnabled();
    const request = "第二天我不想那么赶，请把2026年10月10日安排得轻松一点。先给我新的候选，不要直接保存正式行程。";
    if (resume) {
      expect(report.run_id).toBeTruthy();
      const existing = await get(`planning-runs/${report.run_id}`);
      if (existing.status === "awaiting_clarification") {
        await expect(page.getByLabel("补充回答")).toBeVisible({ timeout: 30_000 });
        const answer = "这些是旅行设置和偏好，不是活动名称。保持日期、预算和一人出行不变，只让第二天轻松一点，生成候选供我确认。";
        await page.getByLabel("补充回答").fill(answer);
        const response = page.waitForResponse(r => r.url().includes(`/planning-runs/${report.run_id}/`) && r.request().method() === "POST");
        await page.getByRole("button", { name: "提交补充", exact: true }).click();
        const result = await response;
        report.clarification = { answer, response: await result.json(), http_status: result.status() };
        expect(result.ok()).toBeTruthy();
      } else {
        expect(["queued", "researching", "planning", "validating", "awaiting_confirmation"]).toContain(existing.status);
      }
      report.resumed_existing_run = true;
      save();
    } else {
    await page.getByLabel("告诉旅程总管").fill(request);
    const message = page.waitForResponse(r => r.url().endsWith("/messages") && r.request().method() === "POST", { timeout: 180_000 });
    await page.getByRole("button", { name: "发送需求", exact: true }).click();
    const response = await message;
    const session = await response.json();
    report.second_day_request = { text: request, response: session, http_status: response.status() };
    save();
    expect(response.ok()).toBeTruthy();
    expect(session.latest_run_id).toBeTruthy();
    expect(session.latest_run_id).not.toBe(earlier.run_id);
    report.run_id = session.latest_run_id;
    }
    await expect.poll(async () => {
      const run = await get(`planning-runs/${report.run_id}`);
      report.latest_run = run;
      save();
      if (["failed", "cancelled", "awaiting_clarification"].includes(run.status)) throw new Error(`Second-day Run ${run.status}: ${run.error_code ?? JSON.stringify(run.pending_interrupt)}`);
      return run.status;
    }, { timeout: 480_000, intervals: [2000, 5000] }).toBe("awaiting_confirmation");
    const revised = await get(`planning-runs/${report.run_id}/revision`);
    report.revised = revised;
    const oldDay = earlier.revision.proposed_snapshot.activities.filter((a: any) => a.day_date === "2026-10-10");
    const newDay = revised.proposed_snapshot.activities.filter((a: any) => a.day_date === "2026-10-10");
    const duration = (items: any[]) => items.reduce((total, item) => total + item.duration_minutes, 0);
    report.pace = { original_count: oldDay.length, revised_count: newDay.length, original_minutes: duration(oldDay), revised_minutes: duration(newDay) };
    save();
    expect(revised.status).toBe("pending");
    expect(revised.validation_result.valid).toBe(true);
    expect(newDay.length).toBeGreaterThan(0);
    expect(newDay.length < oldDay.length || duration(newDay) < duration(oldDay)).toBe(true);
    const outside = (items: any[]) => items.filter(a => a.day_date !== "2026-10-10").sort((a, b) => a.candidate_id.localeCompare(b.candidate_id));
    expect(outside(revised.proposed_snapshot.activities)).toEqual(outside(earlier.revision.proposed_snapshot.activities));
    expect(await get(`trips/${trip}/days`)).toEqual(beforeDays);
    expect((await get(`trips/${trip}`)).version).toBe(beforeTrip.version);
    await expect(page.locator(".ai-proposal").filter({ hasText: "候选方案" })).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: resolve(evidence, "lighter-candidate.png"), fullPage: true });
    const accepted = page.waitForResponse(r => r.url().includes(`/planning-runs/${report.run_id}/decision`) && r.request().method() === "POST", { timeout: 180_000 });
    await page.getByRole("button", { name: "确认并应用", exact: true }).click();
    const acceptedResponse = await accepted;
    report.acceptance = await acceptedResponse.json();
    expect(acceptedResponse.ok()).toBeTruthy();
    expect(report.acceptance.run.status).toBe("accepted");
    const afterTrip = await get(`trips/${trip}`);
    const afterDays = await get(`trips/${trip}/days`);
    report.after = { trip: afterTrip, days: afterDays };
    expect(afterTrip.version).toBe(beforeTrip.version + 1);
    expect(afterDays.flatMap((d: any) => d.activities).length).toBe(revised.proposed_snapshot.activities.length);
    for (const day of afterDays) expect(day.activities.length).toBeGreaterThan(0);
    await expect(page.getByText("已保存到正式行程", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText("已保存到正式行程", { exact: true })).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: resolve(evidence, "formalized.png"), fullPage: true });
    report.status = "formalized_execution_pending";
    save();
  } catch (error) {
    report.status = "failed";
    report.error = error instanceof Error ? error.message : String(error);
    save();
    throw error;
  }
});
