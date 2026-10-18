import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PreferencePanel } from "./PreferencePanel";
afterEach(() => vi.unstubAllGlobals());
it("loads explicit preferences and persists only user selections", async () => {
  const pref = { version: "travel-preferences-v1", preferred_categories: [], interests: ["Tea"] };
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(pref))).mockImplementation(async (_url, init) => new Response(init.body));
  vi.stubGlobal("fetch", fetch); const onSaved = vi.fn(); render(<PreferencePanel onSaved={onSaved} />);
  const input = await screen.findByRole("textbox", { name: "兴趣关键词" });
  await waitFor(() => expect(input).not.toBeDisabled());
  fireEvent.change(input, { target: { value: "Tea，Museum" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "餐饮美食" }));
  fireEvent.click(screen.getByRole("button", { name: "保存探索偏好" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  const body = JSON.parse(fetch.mock.calls[1][1].body);
  expect(body.interests).toEqual(["Tea", "Museum"]); expect(body.preferred_categories).toEqual(["food"]);
  expect(body).not.toHaveProperty("owner_id");
});
