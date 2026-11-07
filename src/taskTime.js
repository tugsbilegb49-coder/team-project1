import { useEffect, useRef, useState } from 'react';
import { api } from './api';

export function useTick() {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

export function clockTime(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  return [Math.floor(value / 3600), Math.floor(value / 60) % 60, value % 60]
    .map((part) => String(part).padStart(2, '0'))
    .join(':');
}

export function useTaskWork(user) {
  const [sample, setSample] = useState(null),
    [failure, setFailure] = useState(null);
  const latest = useRef(null),
    revision = useRef(0),
    mutating = useRef(false);
  const userId = user?.id;
  function receive(data, id) {
    const value = { data, userId: id, at: Date.now() };
    latest.current = value;
    setSample(value);
    setFailure(null);
  }
  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController(),
      flight = { busy: false };
    async function poll(initial = false) {
      if (flight.busy || mutating.current) return;
      flight.busy = true;
      const expected = revision.current;
      const session =
        !initial && latest.current?.userId === userId ? latest.current.data.session : null;
      try {
        const data = await api('/api/tasks/work-session/', {
          signal: controller.signal,
          ...(session?.running
            ? { method: 'POST', body: JSON.stringify({ session_id: session.id }) }
            : {}),
        });
        if (!controller.signal.aborted && expected === revision.current) receive(data, userId);
      } catch (error) {
        if (
          !controller.signal.aborted &&
          expected === revision.current &&
          error.name !== 'AbortError'
        )
          setFailure({ userId, message: error.message });
      } finally {
        flight.busy = false;
      }
    }
    poll(true);
    const timer = setInterval(() => poll(), 20000);
    return () => {
      revision.current += 1;
      controller.abort();
      clearInterval(timer);
    };
  }, [userId]);
  async function start(taskId) {
    const expected = ++revision.current;
    mutating.current = true;
    try {
      const data = await api(`/api/tasks/${taskId}/work-start/`, { method: 'POST', body: '{}' });
      if (expected === revision.current) receive(data, userId);
    } finally {
      mutating.current = false;
    }
  }
  async function stop() {
    const session = latest.current?.userId === userId ? latest.current.data.session : null;
    if (!session) return;
    const expected = ++revision.current;
    mutating.current = true;
    try {
      const data = await api(`/api/tasks/${session.task_id}/work-stop/`, {
        method: 'POST',
        body: JSON.stringify({ session_id: session.id }),
      });
      if (expected === revision.current) receive(data, userId);
    } finally {
      mutating.current = false;
    }
  }
  return {
    sample: sample?.userId === userId ? sample : null,
    error: failure && failure.userId === userId ? failure.message : '',
    start,
    stop,
  };
}
