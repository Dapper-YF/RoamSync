import { expect, test } from "@playwright/test";
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const evidence = resolve("../backend/evals/results/demo_acceptance_20261007");

test("real conversation reaches validated candidate without formal itinerary mutation", async ({ page }) => {
  mkdirSync(evidence, { recursive: true });
  const resume = process.env.ROAMSYNC_ACCEPTANCE_RESUME === "1";
  const previewResume = process.env.ROAMSYNC_ACCEPTANCE_PREVIEW_RESUME === "1";
  const report: Record<string, any> = resume || previewResume ? JSON.parse(readFileSync(resolve(evidence, "conversation.json"), "utf8")) :
    { status: "in_progress", mock: false, isolated: true, turns: [], observations: [] };
  if (resume) { report.resumed_existing_run = true; report.status = "in_progress"; }
  if (previewResume) { expect(report.turns).toHaveLength(7); expect(report.run_id).toBeUndefined(); report.status = "in_progress"; delete report.error; }
  const save = () => writeFileSync(resolve(evidence, "conversation.json"), JSON.stringify(report, null, 2));
  save();
  // Refuse the production URL; preserve any earlier isolated acceptance fixtures.
  expect(new URL(test.info().project.use.baseURL!).port).toBe("3001");
  const initialTrips = await (await page.request.get("/api/v1/trips")).json();
  if (resume) expect(initialTrips.some((t: any) => t.id === report.trip_id)).toBe(true);
  else report.initial_trips = initialTrips;
  await page.goto(resume ? `/dev/agent-conversation/${report.trip_id}` : "/dev/agent-conversation");
  await expect(page.getByLabel("告诉旅程总管")).toBeEnabled({ timeout: 30_000 });
  const texts = [
    "你好",
    "最近想出去玩，一个人有点怕无聊，先聊聊，不要创建旅行。",
    "南京怎么样？我喜欢历史文化和老街巷，想轻松一点。",
    "请根据可靠资料介绍南京的历史文化和老街巷；如果资料不足就说明，不要猜。",
    "南京明天下午天气怎么样？",
    "南京博物院2026年10月7日几点开门，几点停止入馆？",
    "请帮我创建一趟新的独立南京三天旅行，已有旅行保留不改。2026年10月9日出发，10月11日返程，一个人，总预算3000元，喜欢历史文化、老街巷和本地小吃，节奏轻松。先给创建预览，等我确认。",
  ];
  try {
    if (!resume) {
    for (const [index, text] of (previewResume ? [] : texts).entries()) {
      await page.getByLabel("告诉旅程总管").fill(text);
      const response = page.waitForResponse(r => r.url().includes("/assistant/sessions/") && r.url().endsWith("/messages") && r.request().method() === "POST", { timeout: 180_000 });
      await page.getByRole("button", { name: "发送需求", exact: true }).click();
      const result = await response;
      const body = await result.json();
      const last = body.messages?.at(-1);
      report.turns.push({ text, http_status: result.status(), session_id: body.id, last, pending_action: body.pending_action });
      report.session_id = body.id;
      save();
      console.log("turn", index + 1, result.status(), last?.goal_routing?.target_runtime);
      expect(result.ok()).toBeTruthy();
      expect(last.assistant.trim().length).toBeGreaterThan(0);
      await expect(page.locator(".ai-message.agent").last()).toContainText(last.assistant.slice(0, 20));
      expect(await (await page.request.get("/api/v1/trips")).json()).toEqual(initialTrips);
      if (index < 6) {
        expect(last.goal_routing.target_runtime).toBe("companion");
        expect(last.goal_routing.mutation_requested).toBe(false);
        expect(body.latest_run_id).toBeNull();
        expect(body.pending_action).toBeNull();
      } else {
        expect(last.goal_routing.target_runtime).toBe("planning");
        expect(last.planning_brief).toBeTruthy();
        expect(body.pending_action?.tool).toBe("create_trip");
      }
      if (index === 4) {
        expect(last.companion_result.resolved_facts.some((f: any) => f.requirement.fact_type === "weather.forecast" && f.usable_as_current)).toBe(true);
      }
      if (index === 3) {
        expect(last.assistant).not.toContain("西湖");
        expect(last.companion_result.conversation_destination).toBe("南京");
        expect(last.companion_result.information_gaps.some((g: any) => g.code.startsWith("knowledge_"))).toBe(true);
      }
      if (index === 5) {
        expect(last.companion_result.resolved_facts.some((f: any) => f.requirement.fact_type === "place.opening_hours" && f.usable_as_current)).toBe(true);
      }
      await page.screenshot({ path: resolve(evidence, `turn-${index + 1}.png`), fullPage: true });
      await expect(page.getByLabel("告诉旅程总管")).toBeEnabled({ timeout: 30_000 });
    }
    if (previewResume) {
      const text = "请创建一趟新的独立旅行，已有那趟保留不改。南京三天，2026年10月9日至11日，一个人，总预算3000元，喜欢历史文化、老街巷和本地小吃，节奏轻松。先给创建预览，等我确认。";
      await page.getByLabel("告诉旅程总管").fill(text);
      const pending = page.waitForResponse(r => r.url().endsWith("/messages") && r.request().method() === "POST", { timeout: 180_000 });
      await page.getByRole("button", { name: "发送需求", exact: true }).click();
      const response = await pending;
      const body = await response.json();
      report.creation_clarification = { text, http_status: response.status(), last: body.messages.at(-1), pending_action: body.pending_action };
      save();
      expect(response.ok()).toBeTruthy();
      expect(body.id).toBe(report.turns.at(-1).session_id);
      expect(body.latest_run_id).toBeNull();
      expect(body.pending_action?.tool).toBe("create_trip");
      expect(await (await page.request.get("/api/v1/trips")).json()).toEqual(initialTrips);
    }
    await expect(page.getByRole("button", { name: "确认创建", exact: true })).toBeVisible();
    const decision = page.waitForResponse(r => r.url().endsWith("/decision") && r.request().method() === "POST", { timeout: 180_000 });
    await page.getByRole("button", { name: "确认创建", exact: true }).click();
    const response = await decision;
    expect(response.ok()).toBeTruthy();
    const created = await response.json();
    report.creation = created;
    report.trip_id = created.trip_id;
    report.run_id = created.latest_run_id;
    save();
    expect(created.trip_id).toBeTruthy();
    expect(created.latest_run_id).toBeTruthy();
    report.formal_before_candidate = await (await page.request.get(`/api/v1/trips/${created.trip_id}/days`)).json();
    }
    const created = report.creation;
    const daysBefore = report.formal_before_candidate;
    expect(daysBefore.flatMap((d: any) => d.activities)).toHaveLength(0);
    await expect.poll(async () => {
      const run = await (await page.request.get(`/api/v1/planning-runs/${created.latest_run_id}`)).json();
      report.latest_run = run;
      report.observations.push({ at: new Date().toISOString(), status: run.status, progress: run.progress, heartbeat_at: run.heartbeat_at });
      save();
      if (["failed", "cancelled", "awaiting_clarification"].includes(run.status)) throw new Error(`Run ${run.status}: ${run.error_code ?? JSON.stringify(run.pending_interrupt)}`);
      return run.status;
    }, { timeout: 480_000, intervals: [2000, 5000] }).toBe("awaiting_confirmation");
    const revision = await (await page.request.get(`/api/v1/planning-runs/${created.latest_run_id}/revision`)).json();
    report.revision = revision;
    expect(revision.status).toBe("pending");
    expect(revision.validation_result.valid).toBe(true);
    expect(revision.proposed_snapshot.activities.length).toBeGreaterThan(0);
    const daysAfter = await (await page.request.get(`/api/v1/trips/${created.trip_id}/days`)).json();
    expect(daysAfter).toEqual(daysBefore);
    await expect(page.locator(".ai-proposal").filter({ hasText: "候选方案" })).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: resolve(evidence, "candidate.png"), fullPage: true });
    report.status = "candidate_gate_passed_lifecycle_pending";
    delete report.error;
    save();
  } catch (error) {
    report.status = "failed";
    report.error = error instanceof Error ? error.message : String(error);
    save();
    throw error;
  }
});
