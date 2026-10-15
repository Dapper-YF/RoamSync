import { expect, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

test("real knowledge respects city scope and facts remain grounded without formal mutation", async ({ page }) => {
  expect(new URL(test.info().project.use.baseURL!).port).toBe("3001");
  const folder = resolve("../backend/evals/results/demo_acceptance_20261007");
  const trip = JSON.parse(readFileSync(resolve(folder, "execution.json"), "utf8")).trip_id;
  const get = async (path: string) => (await page.request.get(`/api/v1/${path}`)).json();
  const before = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`), runs: await get(`trips/${trip}/planning-runs`) };
  const report: any = { status: "in_progress", before, turns: [] };
  const save = () => writeFileSync(resolve(folder, "knowledge-scope.json"), JSON.stringify(report, null, 2));
  await page.goto(`/dev/agent-conversation/${trip}`);
  const texts = [
    "请根据可靠资料介绍南京的历史文化和老街巷；如果资料不足就说明，不要猜。",
    "请根据可靠资料介绍杭州西湖的历史文化，明确出处。",
    "南京明天下午天气怎么样？",
    "浙江省博物馆之江馆区2026年10月8日几点开门，几点停止入馆？",
  ];
  try {
    for (const [index, text] of texts.entries()) {
      await expect(page.getByLabel("告诉旅程总管")).toBeEnabled({ timeout: 30_000 });
      await page.getByLabel("告诉旅程总管").fill(text);
      const pending = page.waitForResponse(r => r.url().endsWith("/messages") && r.request().method() === "POST", { timeout: 180_000 });
      await page.getByRole("button", { name: "发送需求", exact: true }).click();
      const response = await pending; const session = await response.json(); const last = session.messages.at(-1);
      report.turns.push({ text, http_status: response.status(), last }); save();
      expect(response.ok()).toBeTruthy();
      expect(last.goal_routing.target_runtime).toBe("companion");
      expect(session.latest_run_id).toBeNull();
      expect(last.goal_routing.mutation_requested).toBe(false);
      const result = last.companion_result;
      if (index === 0) {
        expect(last.assistant).not.toContain("西湖");
        expect(result.conversation_destination).toBe("南京");
        expect(result.knowledge_evidence).toHaveLength(0);
        expect(result.information_gaps.some((g: any) => g.code.startsWith("knowledge_"))).toBe(true);
      } else if (index === 1) {
        expect(result.knowledge_evidence.length).toBeGreaterThan(0);
        expect(result.claims.some((c: any) => c.support_status === "supported" && c.source_attributions.length > 0)).toBe(true);
      } else {
        const kind = index === 2 ? "weather.forecast" : "place.opening_hours";
        expect(result.resolved_facts.some((f: any) => f.requirement.fact_type === kind && f.usable_as_current)).toBe(true);
      }
      await expect(page.locator(".ai-message.agent").last()).toContainText(last.assistant.slice(0, 30));
      await page.screenshot({ path: resolve(folder, `scoped-fact-${index}.png`), fullPage: true });
    }
    report.after = { trip: await get(`trips/${trip}`), days: await get(`trips/${trip}/days`), runs: await get(`trips/${trip}/planning-runs`) };
    expect(report.after).toEqual(before);
    report.status = "passed"; save();
  } catch (error) {
    report.status = "failed"; report.error = error instanceof Error ? error.message : String(error); save(); throw error;
  }
});
