import { expect, it } from "vitest";
import { readAssistantStream } from "./assistantStream";

it("decodes split UTF-8 and delivers deltas before done", async () => {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start(value) { controller = value; } });
  const events: unknown[] = [];
  const result = readAssistantStream(new Response(body, { headers: { "Content-Type": "text/event-stream" } }), (event) => events.push(event));
  const frame = encoder.encode('data: {"type":"answer_delta","delta":"钟山。"}\n\n');
  for (const byte of frame) controller.enqueue(new Uint8Array([byte]));
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(events).toEqual([{ type: "answer_delta", delta: "钟山。" }]);
  controller.enqueue(encoder.encode('data: {"type":"done","session":{"id":"session","messages":[]}}\n\n'));
  expect((await result).id).toBe("session");
});

it("never treats a truncated answer as a completed session", async () => {
  const body = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new TextEncoder().encode('data: {"type":"answer_delta","delta":"半截"}\n\n')); controller.close(); } });
  await expect(readAssistantStream(new Response(body, { headers: { "Content-Type": "text/event-stream" } }), () => {})).rejects.toThrow("回答尚未完成");
});
