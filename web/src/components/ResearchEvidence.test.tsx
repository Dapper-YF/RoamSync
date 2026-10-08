import { render, screen } from "@testing-library/react";
import { ResearchEvidence } from "./ResearchEvidence";

it("shows deduplicated research links and omits unsafe source URLs", () => {
  const sources = [{ title: "景区介绍", url: "https://example.com/guide" }, { title: "错误链接", url: "javascript:alert(1)" }];
  render(<ResearchEvidence value={{ queried_at: "2026-09-09", places: { first: { sources }, second: { sources } } }} />);
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(screen.getByRole("link", { name: "景区介绍" })).toHaveAttribute("href", "https://example.com/guide");
  expect(screen.queryByText("错误链接")).not.toBeInTheDocument();
});
