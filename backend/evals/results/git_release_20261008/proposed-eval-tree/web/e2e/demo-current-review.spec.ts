import { expect, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

test("ordinary planning during execution protects current activity and current candidate rejection preserves formal state", async ({ page }) => {
  expect(new URL(test.info().project.use.baseURL!).port).toBe("3001");
  const folder = resolve("../backend/evals/results/demo_acceptance_20261007");
  const trip = JSON.parse(readFileSync(resolve(folder, "execution.json"), "utf8")).trip_id;
  const resume = process.env.ROAMSYNC_CURRENT_REVIEW_RESUME === "1";
  const report: any = resume ? JSON.parse(readFileSync(resolve(folder, "current-review.json"), "utf8")) : { trip_id: trip, status: "in_progress", mock: false };
  report.status = "in_progress";
  delete report.error;
  const save = () => writeFileSync(resolve(folder, "current-review.json"), JSON.stringify(report, null, 2));
  const get = async (path: string) => {
    const response = await page.request.get(`/api/v1/${path}`);
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  try {
    if (!resume) report.before = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`) };
    await page.goto(`/dev/agent-conversation/${trip}`);
    await expect(page.getByLabel("告诉旅程总管")).toBeEnabled({ timeout: 30_000 });
    if (resume) {
      const run = await get(`planning-runs/${report.run_id}`);
      if (run.status === "awaiting_clarification") {
        await expect(page.getByLabel("补充回答")).toBeVisible({ timeout: 30_000 });
        await page.getByLabel("补充回答").fill("已完成活动指后台已经完成的活动状态，不是景点名称。请保持所有已完成活动和当前活动不变，只调整2026年10月11日后续可调整的活动，节奏轻松一点，给候选等待确认。");
        const answer = page.waitForResponse(r => r.url().includes(`/planning-runs/${report.run_id}/`) && r.request().method() === "POST");
        await page.getByRole("button", { name: "提交补充", exact: true }).click();
        report.clarification = await (await answer).json();
      }
    } else {
    const text = "请调整2026年10月11日的后续行程，让节奏轻松一点，保留当前活动和已完成活动。先给候选，等我确认。";
    await page.getByLabel("告诉旅程总管").fill(text);
    const pending = page.waitForResponse(r => r.url().endsWith("/messages") && r.request().method() === "POST", { timeout: 180_000 });
    await page.getByRole("button", { name: "发送需求", exact: true }).click();
    const response = await pending;
    report.message = await response.json();
    expect(response.ok()).toBeTruthy();
    report.run_id = report.message.latest_run_id;
    expect(report.run_id).toBeTruthy();
    }
    save();
    await expect.poll(async () => {
      report.run = await get(`planning-runs/${report.run_id}`);
      save();
      if (["failed", "cancelled", "awaiting_clarification"].includes(report.run.status)) throw new Error(`Run ${report.run.status}: ${report.run.error_code ?? JSON.stringify(report.run.pending_interrupt)}`);
      return report.run.status;
    }, { timeout: 480_000, intervals: [2000, 5000] }).toBe("awaiting_confirmation");
    report.revision = await get(`planning-runs/${report.run_id}/revision`);
    expect(report.revision.validation_result.valid).toBe(true);
    expect(report.revision.status).toBe("pending");
    expect(report.run.disruption_event_id).toBeNull();
    expect(report.run.base_trip_version).toBe(report.before.trip.version);
    expect(await get(`trips/${trip}/days`)).toEqual(report.before.days);
    await expect(page.getByRole("button", { name: "暂不采用", exact: true })).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: resolve(folder, "current-valid-candidate.png"), fullPage: true });
    await page.getByRole("button", { name: "暂不采用", exact: true }).click();
    await page.getByLabel("拒绝原因", { exact: true }).selectOption("too_rushed");
    await page.getByLabel("补充拒绝原因", { exact: true }).fill("这次候选暂不采用，保留已经确认的正式行程。");
    await page.getByRole("button", { name: "确认拒绝", exact: true }).click();
    await expect.poll(async () => (await get(`planning-runs/${report.run_id}`)).status).toBe("rejected");
    report.rejected = await get(`planning-runs/${report.run_id}/revision`);
    report.after = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`) };
    expect(report.after).toEqual(report.before);
    expect(report.rejected.rejection_reason_code).toBe("too_rushed");
    expect(report.rejected.rejection_reason_text).toContain("正式行程");
    report.status = "passed";
    save();
    await page.screenshot({ path: resolve(folder, "current-rejection.png"), fullPage: true });
  } catch (error) {
    report.status = "failed";
    report.error = error instanceof Error ? error.message : String(error);
    save();
    throw error;
  }
});
