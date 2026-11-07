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

/** "45 сек" эсвэл "1 цаг 5 мин" гэх мэт уншихад хялбар хугацаа. */
export function durationText(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 60) return `${Math.floor(value)} сек`;
  const minutes = Math.floor(value / 60);
  return `${Math.floor(minutes / 60)} цаг ${minutes % 60} мин`;
}

/**
 * Серверээс ирсэн даалгаврын session-ийг одоогийн цагтай харьцуулна.
 * Сервер `lease_expires_at` хүртэл л цагийг ажиллаж байна гэж үзнэ; холболт тасарвал
 * тэр хугацаанаас хойш цаг тоолохгүй.
 */
export function sessionTiming(sample, now) {
  const session = sample?.data.session ?? null;
  if (!session) return { session: null, running: false, seconds: 0 };
  const allowance = Math.max(
    0,
    (Date.parse(session.lease_expires_at) - Date.parse(sample.data.server_now)) / 1000,
  );
  const elapsed = Math.max(0, now - sample.at) / 1000;
  return {
    session,
    running: Boolean(session.running) && elapsed < allowance,
    seconds: session.seconds + (session.running ? Math.min(elapsed, allowance) : 0),
  };
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
