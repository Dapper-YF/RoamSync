import { afterEach, expect, it, vi } from "vitest";
import { createStreamBuffer } from "./streamBuffer";
afterEach(() => vi.useRealTimers());
it("coalesces individual network characters and bounds first-content latency", () => {
  vi.useFakeTimers(); const publish = vi.fn(); const buffer = createStreamBuffer(publish);
  for (const char of "如果喜欢慢慢逛，推荐两个气质不同的方向：") buffer.push(char);
  expect(publish).not.toHaveBeenCalled();
  vi.advanceTimersByTime(160);
  expect(publish).toHaveBeenCalledExactlyOnceWith("如果喜欢慢慢逛，推荐两个气质不同的方向：");
});
it("flushes complete clauses and never loses a tail or leaks a reset attempt", () => {
  vi.useFakeTimers(); const chunks: string[] = []; const buffer = createStreamBuffer(v => chunks.push(v));
  const text = "一是成都，街巷生活气息浓，人民公园喝茶，很适合随意走走停停；二是苏州。";
  for (const char of text) buffer.push(char);
  buffer.flush(); expect(chunks.join("")).toBe(text); expect(chunks.every(c => c.length > 1)).toBe(true);
  buffer.push("丢弃的预览"); buffer.reset(); vi.runAllTimers(); expect(chunks.join("")).toBe(text);
});
