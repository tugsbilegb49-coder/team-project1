import { useEffect, useRef } from 'react';

/**
 * `poll(signal)`-ийг даруй, дараа нь `intervalMs` тутам дуудна. Өмнөх хүсэлт дуусаагүй бол
 * тухайн удаагийнхыг алгасна. `key` өөрчлөгдөх эсвэл компонент алга болоход хүсэлтийг цуцална.
 * `poll` өөрийн алдааг өөрөө барина.
 */
export function usePolling(poll, intervalMs, key, enabled = true) {
  const latest = useRef(poll);
  useEffect(() => {
    latest.current = poll;
  });
  useEffect(() => {
    if (!enabled) return undefined;
    const controller = new AbortController();
    const flight = { busy: false };
    async function tick() {
      if (flight.busy) return;
      flight.busy = true;
      try {
        await latest.current(controller.signal);
      } finally {
        flight.busy = false;
      }
    }
    tick();
    const timer = setInterval(tick, intervalMs);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [intervalMs, key, enabled]);
}
