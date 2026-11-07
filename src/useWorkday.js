import { useCallback, useEffect, useRef, useState } from 'react';
import { desktop } from './api';
import { sessionTiming } from './taskTime';

export function useWorkday(user, work) {
  const userId = user?.id;
  const [sample, setSample] = useState(null),
    [feedback, setFeedback] = useState(null);
  const [connection, setConnection] = useState(null),
    [operation, setOperation] = useState(null);
  const [selection, setSelection] = useState(null),
    [closed, setClosed] = useState(null);
  const pending = useRef(null),
    revision = useRef(0);
  const cancelPending = useCallback(() => {
    pending.current?.abort();
    pending.current = null;
  }, []);
  const isClosed = closed === userId;
  const state = sample && sample.userId === userId ? sample.data : null;
  function receive(data) {
    setSample({ userId, data });
    return data;
  }
  useEffect(() => {
    if (!userId || isClosed) return;
    const controller = new AbortController(),
      flight = { busy: false };
    async function poll() {
      if (flight.busy || pending.current) return;
      flight.busy = true;
      const expected = revision.current;
      try {
        const data = await desktop('status', { signal: controller.signal });
        if (!controller.signal.aborted && expected === revision.current) {
          setSample({ userId, data });
          setConnection(null);
        }
      } catch (error) {
        if (!controller.signal.aborted && expected === revision.current)
          setConnection({ userId, message: error.message });
      } finally {
        flight.busy = false;
      }
    }
    poll();
    const timer = setInterval(poll, 5000);
    return () => {
      // `revision` нь DOM ref биш, тоолуур: хуучин хүсэлтийн хариуг хаяхын тулд өсгөнө.
      // oxlint-disable-next-line react-hooks/exhaustive-deps
      ++revision.current;
      controller.abort();
      clearInterval(timer);
      cancelPending();
    };
  }, [userId, isClosed, cancelPending]);

  async function perform(action) {
    if (pending.current || !userId) return false;
    const controller = new AbortController();
    pending.current = controller;
    ++revision.current;
    setOperation({ userId, controller });
    setFeedback(null);
    const send = async (action, data) => {
      if (controller.signal.aborted) throw new DOMException('Cancelled', 'AbortError');
      const value = await desktop(action, {
        signal: controller.signal,
        ...(action === 'status' ? {} : { method: 'POST', body: JSON.stringify(data || {}) }),
      });
      if (!controller.signal.aborted) {
        receive(value);
        setConnection(null);
      }
      return value;
    };
    try {
      const message = await action(send, controller.signal);
      if (!controller.signal.aborted) setFeedback({ userId, message, error: false });
      return !controller.signal.aborted;
    } catch (error) {
      if (!controller.signal.aborted) setFeedback({ userId, message: error.message, error: true });
      return false;
    } finally {
      if (pending.current === controller) pending.current = null;
      setOperation((current) => (current?.controller === controller ? null : current));
    }
  }

  function selectTask(value) {
    setSelection({ userId, value: String(value) });
  }

  function start(value) {
    return perform(async (send, signal) => {
      if (!value) throw new Error('Эхлээд хийх даалгавраа сонгоно уу.');
      if (!work.sample || work.error)
        throw new Error(
          'Даалгаврын цагийн төлөвийг уншиж чадсангүй. Холболтоо шалгаад дахин оролдоно уу.',
        );
      const current = await send('status');
      if (!current.linked) throw new Error('Эхлээд энэ төхөөрөмжийг өөрийн бүртгэлтэй холбоно уу.');
      const { session, running: active } = sessionTiming(work.sample, Date.now());
      if (active && (value === 'none' || session.task_id !== Number(value)))
        throw new Error('Өмнөх даалгавраа түр зогсоогоод шинэ ажлаа сонгоно уу.');
      const needsApps = !current.computer_running || current.paused;
      const startsTask = value !== 'none' && !active;
      if (startsTask) await work.start(Number(value));
      if (signal.aborted) return;
      try {
        if (needsApps) await send(current.computer_running ? 'resume' : 'start');
      } catch (error) {
        if (signal.aborted) throw error;
        if (startsTask) {
          try {
            await work.stop();
          } catch {
            throw new Error(
              'Аппын бүртгэл эхэлсэн эсэхийг баталгаажуулж чадсангүй, даалгаврын цагийг ч зогсоож чадсангүй. «Ажил дуусгах» дарж дахин зогсооно уу.',
            );
          }
        }
        throw new Error(
          `${startsTask ? 'Шинээр эхэлсэн даалгаврын цагийг зогсоолоо.' : 'Өмнө эхэлсэн даалгаврын цаг үргэлжилж байж болно.'} Аппын төлөвийг шалгаад дахин оролдоно уу. ${error.message}`,
        );
      }
      selectTask(value);
      return value === 'none'
        ? 'Аппын хэрэглээ бүртгэгдэж байна. Даалгаврын цаг эхлүүлээгүй.'
        : 'Сонгосон даалгаврын цаг болон аппын хэрэглээ бүртгэгдэж байна.';
    });
  }

  function stop(paused = false) {
    return perform(async (send, signal) => {
      const task = work.sample?.data.session;
      if (task) selectTask(task.task_id);
      const errors = [];
      try {
        await work.stop();
      } catch (error) {
        errors.push(`Даалгаврын цаг: ${error.message}`);
      }
      if (signal.aborted) return;
      try {
        const current = await send('status');
        if (current.linked && (current.computer_running || current.camera_running)) {
          if (paused && current.computer_running) await send('pause');
          else await send('stop');
        }
      } catch (error) {
        errors.push(`Аппын бүртгэл зогссоныг баталгаажуулж чадсангүй: ${error.message}`);
      }
      if (errors.length) throw new Error(errors.join(' '));
      if (!paused) selectTask('');
      return paused
        ? 'Даалгаврын цаг, аппын бүртгэл түр зогслоо. Програм нээлттэй цаг үргэлжилнэ.'
        : 'Даалгаврын цаг, аппын бүртгэлийг зогсоолоо. Даалгаврыг дууссан төлөвт оруулаагүй. Програм нээлттэй цаг үргэлжилнэ.';
    });
  }

  function action(name, data) {
    return perform(async (send, signal) => {
      if (name === 'quit' || name === 'disconnect') await work.stop();
      if (signal.aborted) return;
      await send(name, data);
      if (name === 'quit') setClosed(userId);
      return name === 'connect' ? 'Төхөөрөмж холбогдлоо. Одоо хийх ажлаа сонгоод эхлүүлнэ үү.' : '';
    });
  }
  return {
    state,
    busy: Boolean(operation && operation.userId === userId),
    closed: isClosed,
    choice: selection && selection.userId === userId ? selection.value : '',
    selectTask,
    error: feedback && feedback.userId === userId && feedback.error ? feedback.message : '',
    message: feedback && feedback.userId === userId && !feedback.error ? feedback.message : '',
    connectionError: connection && connection.userId === userId ? connection.message : '',
    action,
    start,
    pause: () => stop(true),
    finish: () => stop(false),
    refresh: () => action('status'),
  };
}
