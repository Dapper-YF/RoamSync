# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: demo-lifecycle.spec.ts >> lifecycle revises an unaccepted candidate then formalizes only on explicit approval
- Location: e2e\demo-lifecycle.spec.ts:7:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: "candidate_gate_passed_lifecycle_pending"
Received: "failed"
```

# Test source

```ts
  1   | import { expect, test } from "@playwright/test";
  2   | import { readFileSync, writeFileSync } from "node:fs";
  3   | import { resolve } from "node:path";
  4   | 
  5   | const evidence = resolve("../backend/evals/results/demo_acceptance_20261007");
  6   | 
  7   | test("lifecycle revises an unaccepted candidate then formalizes only on explicit approval", async ({ page }) => {
  8   |   expect(new URL(test.info().project.use.baseURL!).port).toBe("3001");
  9   |   const earlier = JSON.parse(readFileSync(resolve(evidence, "conversation.json"), "utf8"));
> 10  |   expect(earlier.status).toBe("candidate_gate_passed_lifecycle_pending");
      |                          ^ Error: expect(received).toBe(expected) // Object.is equality
  11  |   const resume = process.env.ROAMSYNC_LIFECYCLE_RESUME === "1";
  12  |   const report: Record<string, any> = resume
  13  |     ? JSON.parse(readFileSync(resolve(evidence, "lifecycle.json"), "utf8"))
  14  |     : { status: "in_progress", trip_id: earlier.trip_id, stages: [], mock: false, isolated: true };
  15  |   report.status = "in_progress";
  16  |   delete report.error;
  17  |   const save = () => writeFileSync(resolve(evidence, "lifecycle.json"), JSON.stringify(report, null, 2));
  18  |   const trip = earlier.trip_id;
  19  |   const get = async (path: string) => {
  20  |     const r = await page.request.get(`/api/v1/${path}`);
  21  |     expect(r.ok()).toBeTruthy();
  22  |     return r.json();
  23  |   };
  24  |   try {
  25  |     const beforeTrip = await get(`trips/${trip}`);
  26  |     const beforeDays = await get(`trips/${trip}/days`);
  27  |     report.before = { trip: beforeTrip, days: beforeDays };
  28  |     expect(beforeDays.flatMap((d: any) => d.activities)).toHaveLength(0);
  29  |     await page.goto(`/dev/agent-conversation/${trip}`);
  30  |     if (!resume) await expect(page.locator(".ai-proposal").filter({ hasText: "候选方案" })).toBeVisible({ timeout: 30_000 });
  31  |     await expect(page.getByLabel("告诉旅程总管")).toBeEnabled();
  32  |     const request = "第二天我不想那么赶，请把2026年10月10日安排得轻松一点。先给我新的候选，不要直接保存正式行程。";
  33  |     if (resume) {
  34  |       expect(report.run_id).toBeTruthy();
  35  |       const existing = await get(`planning-runs/${report.run_id}`);
  36  |       if (existing.status === "awaiting_clarification") {
  37  |         await expect(page.getByLabel("补充回答")).toBeVisible({ timeout: 30_000 });
  38  |         const answer = "这些是旅行设置和偏好，不是活动名称。保持日期、预算和一人出行不变，只让第二天轻松一点，生成候选供我确认。";
  39  |         await page.getByLabel("补充回答").fill(answer);
  40  |         const response = page.waitForResponse(r => r.url().includes(`/planning-runs/${report.run_id}/`) && r.request().method() === "POST");
  41  |         await page.getByRole("button", { name: "提交补充", exact: true }).click();
  42  |         const result = await response;
  43  |         report.clarification = { answer, response: await result.json(), http_status: result.status() };
  44  |         expect(result.ok()).toBeTruthy();
  45  |       } else {
  46  |         expect(["queued", "researching", "planning", "validating", "awaiting_confirmation"]).toContain(existing.status);
  47  |       }
  48  |       report.resumed_existing_run = true;
  49  |       save();
  50  |     } else {
  51  |     await page.getByLabel("告诉旅程总管").fill(request);
  52  |     const message = page.waitForResponse(r => r.url().endsWith("/messages") && r.request().method() === "POST", { timeout: 180_000 });
  53  |     await page.getByRole("button", { name: "发送需求", exact: true }).click();
  54  |     const response = await message;
  55  |     const session = await response.json();
  56  |     report.second_day_request = { text: request, response: session, http_status: response.status() };
  57  |     save();
  58  |     expect(response.ok()).toBeTruthy();
  59  |     expect(session.latest_run_id).toBeTruthy();
  60  |     expect(session.latest_run_id).not.toBe(earlier.run_id);
  61  |     report.run_id = session.latest_run_id;
  62  |     }
  63  |     await expect.poll(async () => {
  64  |       const run = await get(`planning-runs/${report.run_id}`);
  65  |       report.latest_run = run;
  66  |       save();
  67  |       if (["failed", "cancelled", "awaiting_clarification"].includes(run.status)) throw new Error(`Second-day Run ${run.status}: ${run.error_code ?? JSON.stringify(run.pending_interrupt)}`);
  68  |       return run.status;
  69  |     }, { timeout: 480_000, intervals: [2000, 5000] }).toBe("awaiting_confirmation");
  70  |     const revised = await get(`planning-runs/${report.run_id}/revision`);
  71  |     report.revised = revised;
  72  |     const oldDay = earlier.revision.proposed_snapshot.activities.filter((a: any) => a.day_date === "2026-10-10");
  73  |     const newDay = revised.proposed_snapshot.activities.filter((a: any) => a.day_date === "2026-10-10");
  74  |     const duration = (items: any[]) => items.reduce((total, item) => total + item.duration_minutes, 0);
  75  |     report.pace = { original_count: oldDay.length, revised_count: newDay.length, original_minutes: duration(oldDay), revised_minutes: duration(newDay) };
  76  |     save();
  77  |     expect(revised.status).toBe("pending");
  78  |     expect(revised.validation_result.valid).toBe(true);
  79  |     expect(newDay.length).toBeGreaterThan(0);
  80  |     expect(newDay.length < oldDay.length || duration(newDay) < duration(oldDay)).toBe(true);
  81  |     const outside = (items: any[]) => items.filter(a => a.day_date !== "2026-10-10").sort((a, b) => a.candidate_id.localeCompare(b.candidate_id));
  82  |     expect(outside(revised.proposed_snapshot.activities)).toEqual(outside(earlier.revision.proposed_snapshot.activities));
  83  |     expect(await get(`trips/${trip}/days`)).toEqual(beforeDays);
  84  |     expect((await get(`trips/${trip}`)).version).toBe(beforeTrip.version);
  85  |     await expect(page.locator(".ai-proposal").filter({ hasText: "候选方案" })).toBeVisible({ timeout: 30_000 });
  86  |     await page.screenshot({ path: resolve(evidence, "lighter-candidate.png"), fullPage: true });
  87  |     const accepted = page.waitForResponse(r => r.url().includes(`/planning-runs/${report.run_id}/decision`) && r.request().method() === "POST", { timeout: 180_000 });
  88  |     await page.getByRole("button", { name: "确认并应用", exact: true }).click();
  89  |     const acceptedResponse = await accepted;
  90  |     report.acceptance = await acceptedResponse.json();
  91  |     expect(acceptedResponse.ok()).toBeTruthy();
  92  |     expect(report.acceptance.run.status).toBe("accepted");
  93  |     const afterTrip = await get(`trips/${trip}`);
  94  |     const afterDays = await get(`trips/${trip}/days`);
  95  |     report.after = { trip: afterTrip, days: afterDays };
  96  |     expect(afterTrip.version).toBe(beforeTrip.version + 1);
  97  |     expect(afterDays.flatMap((d: any) => d.activities).length).toBe(revised.proposed_snapshot.activities.length);
  98  |     for (const day of afterDays) expect(day.activities.length).toBeGreaterThan(0);
  99  |     await expect(page.getByText("已保存到正式行程", { exact: true })).toBeVisible();
  100 |     await page.reload();
  101 |     await expect(page.getByText("已保存到正式行程", { exact: true })).toBeVisible({ timeout: 30_000 });
  102 |     await page.screenshot({ path: resolve(evidence, "formalized.png"), fullPage: true });
  103 |     report.status = "formalized_execution_pending";
  104 |     save();
  105 |   } catch (error) {
  106 |     report.status = "failed";
  107 |     report.error = error instanceof Error ? error.message : String(error);
  108 |     save();
  109 |     throw error;
  110 |   }
```