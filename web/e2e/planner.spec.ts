import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/trips/00000000-0000-4000-8000-000000000001/planner");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
});

test("switches days and opens activity details", async ({ page }) => {
  await expect(page.getByText("湖滨散步与城市夜色")).toBeVisible();
  await page.locator(".timeline-card-main", { hasText: "西湖·断桥" }).click();
  await expect(page.getByTestId("inspector")).toContainText("西湖·断桥");
  await page.getByRole("tab", { name: /9月6日/ }).click();
  await expect(page.getByText("山林茶村与从容返程")).toBeVisible();
});

test("adds a candidate and persists it across refresh", async ({ page }) => {
  await page.getByRole("button", { name: "从候选地点加入" }).click();
  const card = page.locator(".candidate-card", { hasText: "雷峰塔" });
  await card.getByRole("button", { name: "确认加入" }).click();
  await expect(page.locator(".timeline-card", { hasText: "雷峰塔" })).toBeVisible();
  await page.reload();
  await expect(page.locator(".timeline-card", { hasText: "雷峰塔" })).toBeVisible();
});

test("searches places and recalculates the selected route mode", async ({ page }) => {
  await page.getByRole("button", { name: "从候选地点加入" }).click();
  await page.getByPlaceholder("搜索杭州地点").fill("雷峰塔");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.locator(".candidate-card", { hasText: "雷峰塔" })).toBeVisible();
  await page.getByRole("button", { name: "关闭候选地点" }).click();
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
  await page.getByRole("combobox", { name: "移动到其他日期" }).selectOption("day-2");
  await page.getByRole("button", { name: "移到开头" }).click();
  await expect(page.getByText("山林茶村与从容返程")).toBeVisible();
  await expect(page.locator(".timeline-card").first()).toContainText("西湖晨间散步");
  await page.reload();
  await page.getByRole("tab", { name: /9月6日/ }).click();
  await expect(page.locator(".timeline-card").first()).toContainText("西湖晨间散步");
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 1024, height: 768 }]) {
  test(`has no horizontal overflow at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await expect(page.locator(".planner-sidebar")).toBeVisible();
    await expect(page.locator(".map-stage")).toBeVisible();
    await expect(page).toHaveScreenshot(`planner-${viewport.width}.png`, {
      animations: "disabled",
      fullPage: true,
    });
  });
}
