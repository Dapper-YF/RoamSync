// Coalesce network fragments without changing or inventing answer text.
// Punctuation preferred; bounded latency prevents waiting for an entire paragraph.
export function createStreamBuffer(publish: (text: string) => void, delay = 160) {
  let pending = "";
  let timer: ReturnType<typeof setTimeout> | undefined;
  const flush = () => {
    clearTimeout(timer); timer = undefined;
    if (pending) { const value = pending; pending = ""; publish(value); }
  };
  const schedule = () => { timer ??= setTimeout(flush, delay); };
  return {
    push(delta: string) {
      pending += delta;
      if (pending.length >= 24 && /[，。！？；：,!?;:\n]/u.test(pending)) flush();
      else if (pending.length >= 96) flush();
      else schedule();
    },
    flush,
    reset() { clearTimeout(timer); timer = undefined; pending = ""; },
  };
}
