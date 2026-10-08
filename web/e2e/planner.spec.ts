import { expect, test } from "@playwright/test";

const testTrips = new Map<string, string>();
test.beforeEach(async ({ page }, testInfo) => {
  const copy = await page.request.post("/api/v1/trips/00000000-0000-4000-8000-000000000001/duplicate");
  expect(copy.ok()).toBeTruthy();
  const trip = await copy.json();
  testTrips.set(testInfo.testId, trip.id);
  await page.goto(`/trips/${trip.id}`);
  await expect(page.locator(".planner-sidebar")).toBeVisible();
});

test.afterEach(async ({ page }, testInfo) => {
  const id = testTrips.get(testInfo.testId);
  if (id) {
    // Archive only the copy created by this test; never reset the demo or user trips.
    await page.request.post(`/api/v1/trips/${id}/archive`);
    testTrips.delete(testInfo.testId);
  }
});

test("switches days and opens activity details", async ({ page }) => {
  await expect(page.getByText("湖滨美学、杭帮味道与南宋夜色")).toBeVisible();
  await page.locator(".timeline-card-main", { hasText: "西湖·断桥" }).click();
  await expect(page.getByTestId("inspector")).toContainText("西湖·断桥");
  await page.getByRole("tab", { name: /9月6日/ }).click();
  await expect(page.getByText("灵隐禅意、龙井茶山与从容返程")).toBeVisible();
});

test("adds a candidate and persists it across refresh", async ({ page }) => {
  await page.getByRole("button", { name: "添加地点" }).click();
  const card = page.locator(".candidate-card", { hasText: "雷峰塔" });
  await card.getByRole("button", { name: "确认加入" }).click();
  await expect(page.locator(".timeline-card", { hasText: "雷峰塔" })).toBeVisible();
  await page.reload();
  await expect(page.locator(".timeline-card", { hasText: "雷峰塔" })).toBeVisible();
});

test("searches places and recalculates the selected route mode", async ({ page }) => {
  await page.getByRole("button", { name: "添加地点" }).click();
  await page.getByPlaceholder("搜索杭州地点").fill("雷峰塔");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.locator(".candidate-card", { hasText: "雷峰塔" })).toBeVisible();
  await page.getByRole("button", { name: "关闭候选地点" }).click();
  await page.getByRole("button", { name: "地图", exact: true }).click();
  await page.locator(".route-mode-control select").selectOption("driving");
  await expect(page.locator(".route-connector").first()).toContainText("驾车");
});

test("edits an activity and moves it to another day", async ({ page }) => {
  await page.locator(".timeline-card-main", { hasText: "西湖·断桥" }).click();
  await page.getByRole("button", { name: "编辑活动" }).click();
  await page.getByRole("textbox", { name: "显示名称" }).fill("西湖晨间散步");
  await page.getByRole("textbox", { name: "预计费用（元）" }).fill("12.34");
  await page.getByRole("checkbox", { name: /固定开始时间/ }).check();
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.locator(".timeline-card", { hasText: "西湖晨间散步" })).toBeVisible();
  await page.getByRole("combobox", { name: "移动到其他日期" }).selectOption({ index: 0 });
  await page.getByRole("button", { name: "移到开头" }).click();
  await expect(page.getByText("灵隐禅意、龙井茶山与从容返程")).toBeVisible();
  await expect(page.locator(".timeline-card", { hasText: "西湖晨间散步" })).toBeVisible();
  await expect(page.locator(".app-shell")).toHaveAttribute("aria-busy", "false");
  await page.reload();
  await page.getByRole("tab", { name: /9月6日/ }).click();
  await expect(page.locator(".timeline-card").first()).toContainText("西湖晨间散步");
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 1024, height: 768 }, { width: 390, height: 844 }]) {
  test(`has no horizontal overflow at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await expect(page.locator(".planner-sidebar")).toBeVisible();
    await expect(page.locator(".map-stage")).toBeHidden();
    await expect(page).toHaveScreenshot(`planner-${viewport.width}.png`, {
      animations: "disabled",
      fullPage: true,
    });
  });
}


test("records completion and restores it after refresh without starting a trip", async ({ page }) => {
  await expect(page.getByRole("button", { name: "开始旅行", exact: true })).toHaveCount(0);
  await page.locator(".timeline-card-main", { hasText: "西湖·断桥" }).click();
  await page.getByRole("button", { name: "完成", exact: true }).click();
  await expect(page.getByRole("button", { name: "恢复为待游玩" })).toBeVisible();
  await page.reload();
  await page.locator(".timeline-card-main", { hasText: "西湖·断桥" }).click();
  await expect(page.getByRole("button", { name: "恢复为待游玩" })).toBeVisible();
});

test("mobile switches map and opens the same assistant", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "地图", exact: true }).click();
  await expect(page.locator(".map-stage")).toBeVisible();
  await page.getByRole("button", { name: "行程", exact: true }).click();
  await expect(page.locator(".planner-sidebar")).toBeVisible();
  await page.getByRole("button", { name: "打开旅程总管" }).click();
  await expect(page.getByRole("textbox", { name: "告诉旅程总管" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
});

test("homepage conversation previews creation then continues in the same trip assistant", async ({ page }, testInfo) => {
  const tripId = testTrips.get(testInfo.testId)!;
  const session = { id: "home-test-session", trip_id: null as string | null, latest_run_id: null, pending_action: null as unknown, messages: [] as Array<{ id: string; user: string; assistant: string }> };
  await page.route("**/api/v1/assistant/sessions", route => route.fulfill({ json: session }));
  await page.route("**/api/v1/assistant/sessions/home-test-session/messages", async route => {
    session.messages.push({ id: "turn", user: route.request().postDataJSON().message, assistant: "已记下两人出行和轻松的节奏，请核对后创建。" });
    session.pending_action = { id: "create-action", tool: "create_trip", title: "对话创建验收", city: { name: "杭州市" }, start_date: "2027-01-01", end_date: "2027-01-02", total_budget_fen: 400000, daily_budget_fen: 200000, preferences: "两人出行，节奏轻松", summary: "确认后创建旅行并生成候选行程。" };
    await route.fulfill({ json: session });
  });
  await page.route("**/api/v1/assistant/sessions/home-test-session/decision", async route => {
    expect(route.request().postDataJSON()).toEqual({ action_id: "create-action", accept: true });
    session.trip_id = tripId;
    session.pending_action = null;
    await route.fulfill({ json: session });
  });
  await page.goto("/trips");
  await page.getByRole("button", { name: "旅程总管", exact: true }).click();
  const input = page.getByRole("textbox", { name: "告诉旅程总管" });
  await expect(input).toBeEnabled();
  await input.fill("2027年1月1日至2日杭州，两人4000元，轻松一点");
  await input.press("Enter");
  await expect(page.getByRole("heading", { name: "对话创建验收" })).toBeVisible();
  await expect(page).toHaveURL(/\/trips$/);
  await page.getByRole("button", { name: "确认创建", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/trips/${tripId}\\?ai=1`));
  await expect(page.getByRole("complementary", { name: "旅程总管" })).toBeVisible();
  await expect(page.getByText("已记下两人出行和轻松的节奏，请核对后创建。")).toBeVisible();
});

test("an open formal itinerary picks up place replacements from another client", async ({ page }, testInfo) => {
  const tripId = testTrips.get(testInfo.testId)!;
  const days = await (await page.request.get(`/api/v1/trips/${tripId}/days`)).json();
  const candidates = await (await page.request.get(`/api/v1/trips/${tripId}/candidates`)).json();
  const replacement = candidates.find((item: { name: string }) => item.name === "雷峰塔");
  expect(replacement).toBeTruthy();
  // Write through a separate API client while the mounted page keeps its old state.
  expect((await page.request.delete(`/api/v1/activities/${days[0].activities[0].id}`)).ok()).toBeTruthy();
  expect((await page.request.post(`/api/v1/day-plans/${days[0].id}/activities`, { data: { place_id: replacement.id } })).ok()).toBeTruthy();
  await expect(page.locator(".timeline-card", { hasText: "雷峰塔" })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".timeline-card", { hasText: "西湖·断桥" })).toHaveCount(0);
  await expect(page.getByText("正式行程有新修改，已同步到当前页面")).toBeVisible();
  await page.reload();
  await expect(page.locator(".timeline-card", { hasText: "雷峰塔" })).toBeVisible();
});

test("Enter sends the request and Shift+Enter keeps a newline", async ({ page }, testInfo) => {
  const tripId = testTrips.get(testInfo.testId)!;
  const requests: string[] = [];
  await page.route("**/api/v1/assistant/sessions/*/messages", async (route) => {
    const message = route.request().postDataJSON().message;
    requests.push(message);
    await route.fulfill({ json: { id: "keyboard-session", trip_id: tripId, messages: [], pending_action: null, latest_run_id: "keyboard-test-run" } });
  });
  await page.route("**/api/v1/planning-runs/keyboard-test-run", route => route.fulfill({ json: { id: "keyboard-test-run", trip_id: tripId, run_type: "replan", status: "awaiting_clarification", user_request: requests[0], token_usage: 0, pending_interrupt: { kind: "clarification", questions: ["希望增加哪类体验？"] } } }));
  await page.getByRole("button", { name: "打开旅程总管" }).click();
  const input = page.getByRole("textbox", { name: "告诉旅程总管" });
  await expect(input).toBeEnabled();
  await input.fill("我希望这次旅行可以丰富一些");
  await input.press("Shift+Enter");
  await expect(input).toHaveValue("我希望这次旅行可以丰富一些\n");
  expect(requests).toHaveLength(0);
  await input.press("Enter");
  await expect(page.getByText("希望增加哪类体验？")).toBeVisible();
  expect(requests).toEqual(["我希望这次旅行可以丰富一些"]);
});

test("a question renders an answer and keeps the formal itinerary unchanged", async ({ page }, testInfo) => {
  const tripId = testTrips.get(testInfo.testId)!;
  const before = await (await page.request.get(`/api/v1/trips/${tripId}/days`)).json();
  let question: string | undefined;
  await page.route("**/api/v1/assistant/sessions/*/messages", async (route) => {
    question = route.request().postDataJSON().message;
    await route.fulfill({ json: { id: "answer-session", trip_id: tripId, messages: [], pending_action: null, latest_run_id: "answer-test-run" } });
  });
  await page.route("**/api/v1/planning-runs/answer-test-run", route => route.fulfill({ json: { id: "answer-test-run", trip_id: tripId, run_type: "replan", status: "answered", user_request: question, response_text: "第一天从西湖断桥出发，午间保留休息，因为连续步行容易疲劳。", token_usage: 0, pending_interrupt: null } }));
  await page.getByRole("button", { name: "打开旅程总管" }).click();
  const input = page.getByRole("textbox", { name: "告诉旅程总管" });
  await expect(input).toBeEnabled();
  await input.fill("现在的旅行行程是怎样的，你建议我怎么走这一趟？");
  await input.press("Enter");
  await expect(page.locator(".ai-answer")).toContainText("因为连续步行容易疲劳");
  await expect(page.getByRole("button", { name: "确认并应用" })).toHaveCount(0);
  await expect(input).toBeEnabled();
  expect(question).toBe("现在的旅行行程是怎样的，你建议我怎么走这一趟？");
  expect(await (await page.request.get(`/api/v1/trips/${tripId}/days`)).json()).toEqual(before);
});
