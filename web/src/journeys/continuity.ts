import { useEffect, useState } from "react";

export function readScene<T>(key: string, fallback: T): T {
  try { return JSON.parse(sessionStorage.getItem(`roamsync.journeys.${key}`) || "null") ?? fallback; } catch { return fallback; }
}
export function writeScene(key: string, value: unknown) {
  try { sessionStorage.setItem(`roamsync.journeys.${key}`, JSON.stringify(value)); } catch { /* In-memory editing remains available. */ }
}
export function useJourneyScene<T>(key: string, fallback: T) {
  const [value, setValue] = useState<T>(() => readScene(key, fallback));
  useEffect(() => { writeScene(key, value); }, [key, value]);
  return [value, setValue] as const;
}
