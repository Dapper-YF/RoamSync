import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AssistantAnswer, type AnswerSearch } from "./AssistantAnswer";
it("renders optional illustrations without factual web sources and hides failed images", () => {
  const { rerender } = render(<AssistantAnswer text="介绍成都火锅" visuals={{status:"available",images:[{url:"https://images.example.org/food.jpg",source_url:"https://example.org/food",description:"火锅参考图",topic:"火锅"}]}} />);
  expect(screen.queryByRole("img")).toBeNull();
  fireEvent.error(screen.getByRole("img", {hidden:true}));
  expect(screen.getByText("介绍成都火锅")).toBeVisible();
  expect(screen.queryByRole("img")).toBeNull();
  rerender(<AssistantAnswer text="正常回答" visuals={{status:"unavailable",images:[]}} />);
  expect(screen.getByText("正常回答")).toBeVisible();
  expect(screen.queryByText(/联网搜索暂不可用/)).toBeNull();
});
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
  fireEvent.load(screen.getByRole("img", { name: "玄武湖实景", hidden:true }));
  expect(screen.getByRole("img", { name: "玄武湖实景" })).toBeVisible();
  expect(screen.getByRole("link", { name: "CC BY-SA 4.0" })).toHaveAttribute("href", "https://creativecommons.org/licenses/by-sa/4.0/");
  expect(screen.getByText(/Photo Author/)).not.toBeVisible();
  fireEvent.click(screen.getByLabelText("图片来源与许可"));
  expect(screen.getByText(/Photo Author/)).toBeVisible();
});
const search: AnswerSearch = { status: "available", sources: [{ url: "https://example.org/food", title: "成都美食" }], images: [{ url: "https://images.example.org/hotpot.jpg", source_url: "https://images.example.org/hotpot.jpg", description: "成都火锅" }] };
it("only renders exact current-turn search images and keeps text when an image fails", () => {
  const { rerender } = render(<AssistantAnswer text={"**火锅**\n\n成都美食"} />);
  expect(screen.queryByRole("img")).toBeNull();
  rerender(<AssistantAnswer text={"**火锅**\n\n成都美食"} search={search} />);
  expect(screen.getByText("火锅").tagName).toBe("STRONG");
  const image = screen.getByRole("img", { name: "成都火锅", hidden:true });
  fireEvent.load(image);
  expect(image).toHaveAttribute("referrerpolicy", "no-referrer");
  fireEvent.error(image); expect(screen.queryByRole("img")).toBeNull(); expect(screen.getByText("成都美食", { selector: "p" })).toBeVisible();
});
it("embeds a loaded picture beside its own paragraph and shows no reference-photo label", () => {
  const {container}=render(<AssistantAnswer text={"先比较两种吃法。\n\n牛油火锅适合围坐涮菜。\n\n串串香用竹签串好食材。"} visuals={{status:"available",images:[{url:"https://images.example.org/skewers.jpg",source_url:"https://example.org/photo",topic:"串串香",description:"串串香参考图 · 竹签食材",usage_basis:"search_reference"}]}} />);
  const image=screen.getByRole("img",{hidden:true});
  expect(image.closest("figure")).not.toBeVisible();
  fireEvent.load(image);
  expect(image.closest(".assistant-answer-block")).toHaveTextContent("串串香用竹签串好食材");
  expect(image).toBeVisible();
  expect(container.querySelector(".assistant-photo-kind")).toBeNull();
  expect(screen.queryByText("参考图")).toBeNull();
  expect(image.getAttribute("alt")).not.toContain("参考图");
  fireEvent.error(image);
  expect(container.querySelector("figure")).toBeNull();
  expect(screen.getByText("串串香用竹签串好食材。")).toBeVisible();
});
it("does not render unsafe image schemes or unavailable search leftovers", () => {
  render(<AssistantAnswer text="回答仍可阅读" search={{ ...search, status: "unavailable" }} />);
  expect(screen.queryByRole("img")).toBeNull(); expect(screen.getByText(/联网搜索暂不可用/)).toBeVisible();
});
