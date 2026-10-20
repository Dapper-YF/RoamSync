import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AssistantAnswer, type AnswerSearch } from "./AssistantAnswer";
const search: AnswerSearch = { status: "available", sources: [{ url: "https://example.org/food", title: "成都美食" }], images: [{ url: "https://images.example.org/hotpot.jpg", source_url: "https://images.example.org/hotpot.jpg", description: "成都火锅" }] };
it("only renders exact current-turn search images and keeps text when an image fails", () => {
  const { rerender } = render(<AssistantAnswer text={"**火锅**\n\n成都美食"} />);
  expect(screen.queryByRole("img")).toBeNull();
  rerender(<AssistantAnswer text={"**火锅**\n\n成都美食"} search={search} />);
  expect(screen.getByText("火锅").tagName).toBe("STRONG");
  const image = screen.getByRole("img", { name: "成都火锅" });
  expect(image).toHaveAttribute("referrerpolicy", "no-referrer");
  fireEvent.error(image); expect(screen.queryByRole("img")).toBeNull(); expect(screen.getByText("成都美食", { selector: "p" })).toBeVisible();
});
it("does not render unsafe image schemes or unavailable search leftovers", () => {
  render(<AssistantAnswer text="回答仍可阅读" search={{ ...search, status: "unavailable" }} />);
  expect(screen.queryByRole("img")).toBeNull(); expect(screen.getByText(/联网搜索暂不可用/)).toBeVisible();
});
