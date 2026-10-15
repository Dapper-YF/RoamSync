import type { AssistantSession, AssistantStreamEvent } from "../domain/types";

export async function readAssistantStream(response: Response, onEvent: (event: AssistantStreamEvent) => void): Promise<AssistantSession> {
  if (!response.ok) throw new Error(`AI 请求失败（${response.status}）`);
  if (!response.headers.get("content-type")?.includes("text/event-stream") || !response.body) {
    throw new Error("AI 服务没有返回数据流，请重试。");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
        if (!data) continue;
        const event = JSON.parse(data) as AssistantStreamEvent;
        if (event.type === "error") throw new Error(event.message);
        if (event.type === "done") return event.session;
        onEvent(event);
      }
      if (done) throw new Error("连接中断，回答尚未完成。可以重试发送。");
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
