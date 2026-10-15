// Same-origin UI request observations; durable Agent stages still come from the API.
export const MONITOR_CHANNEL = "roamsync-agent-monitor-v1";
export interface DialogueObservation {
  type: "request_started" | "request_completed" | "request_failed" | "trip_selected";
  requestId: string; tripId?: string; message?: string; at: string; runId?: string;
  sessionId?: string; messageId?: string;
  assistant?: string; runtimeTrace?: string[]; error?: string;
}
export function publishMonitor(event: Omit<DialogueObservation, "at">) {
  try {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(MONITOR_CHANNEL);
    channel.postMessage({ ...event, at: new Date().toISOString() });
    channel.close();
  } catch { /* A missing observer never affects sending a user request. */ }
}
