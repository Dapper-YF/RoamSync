import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AssistantAnswer, type AnswerSearch } from "./AssistantAnswer";
it("links only server-owned references and labels page reads", () => {
  render(<AssistantAnswer text="文章提到牛油锅底。[1]" search={{ status: "available",
    sources: [{ source_id: "web_valid", url: "https://example.org/branch", title: "玉林分店探店", read_level: "page_text" }], images: [] }} />);
  expect(screen.getByRole("link", { name: "查看来源：玉林分店探店" })).toHaveAttribute("href", "https://example.org/branch");
  expect(screen.getByText(/已读取正文/)).toBeInTheDocument();
  expect(screen.queryByText(/web_unknown/)).toBeNull();
});
it("shows a reviewed place photo with attribution without requiring its name in prose", () => {
  render(<AssistantAnswer text="找到一个可比较的地方。" search={{ status: "available", sources: [{ source_id: "poi_1", place_id: "p1", title: "地点", url: "https://www.amap.com/search?id=test" }],
    images: [{ place_id: "p1", topic: "玄武湖", url: "/api/v1/media/place-images/park-1-960.jpg", source_url: "https://commons.wikimedia.org/wiki/File:park.jpg", description: "玄武湖实景", usage_basis: "reviewed_commons_license", attribution: "Photo Author", license_name: "CC BY-SA 4.0", license_url: "https://creativecommons.org/licenses/by-sa/4.0/" }] }} />);
  expect(screen.getByRole("img", { name: "玄武湖实景" })).toBeVisible();
  expect(screen.getByRole("link", { name: "CC BY-SA 4.0" })).toHaveAttribute("href", "https://creativecommons.org/licenses/by-sa/4.0/");
  expect(screen.getByText(/Photo Author/)).toBeVisible();
});
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
