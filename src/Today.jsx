import { useEffect, useRef, useState } from 'react';
import { api, clearAuth } from './api';
import { LauncherClock, TaskWorkClock } from './WorkClocks';
import { useTick } from './taskTime';

function duration(seconds) {
  if (Number(seconds || 0) < 60) return `${Math.floor(Number(seconds || 0))} сек`;
  const minutes = Math.floor(Number(seconds || 0) / 60);
  return `${Math.floor(minutes / 60)} цаг ${minutes % 60} мин`;
}

export function DesktopPanel({ user, tasks, work, workday, busy }) {
  const now = useTick();
  const { state, error, connectionError, message, closed } = workday;
  const [step, setStep] = useState(1),
    [deviceName, setDeviceName] = useState('Миний компьютер'),
    [consent, setConsent] = useState(false);
  const [relink, setRelink] = useState(false);
  async function act(action, body = {}) {
    if (await workday.action(action, body)) {
      if (action === 'connect') setRelink(false);
    }
  }
  const runningWork = state?.computer_running;
  const session = work.sample?.data.session;
  const taskRunning =
    session?.running &&
    now - work.sample.at <
      Date.parse(session.lease_expires_at) - Date.parse(work.sample.data.server_now);
  const working = Boolean((runningWork && !state.paused) || taskRunning);
  const ownTasks = tasks.filter((task) => task.employee === user.id && task.status !== 'Дууссан');
  const selected = taskRunning ? String(session.task_id) : workday.choice;
  const validChoice = selected === 'none' || ownTasks.some((task) => String(task.id) === selected);
  return (
    <section className="desktop-panel" aria-label="Энэ компьютерийн удирдлага">
      <div className="workday-heading">
        <div>
          <p className="eyebrow">Эхлэх → Ажиллах → Түр зогсоох / Дуусгах</p>
          <h2>Одоо хийх ажил</h2>
        </div>
        <span className={`work-status ${working ? 'is-working' : ''}`}>
          {working ? 'Бүртгэж байна' : runningWork && state.paused ? 'Түр зогссон' : 'Эхлээгүй'}
        </span>
      </div>
      {closed ? (
        <p role="status">WorkTrack хаагдаж байна. Дараа WorkTrack.app-аа нээгээрэй.</p>
      ) : (
        <>
          {error && <p role="alert">{error}</p>}
          {message && (
            <p role="status" className="work-feedback">
              {message}
            </p>
          )}
          {connectionError && <p role="alert">{connectionError}</p>}
          {!state && !connectionError && <p>Төхөөрөмжтэй холбогдож байна…</p>}
          {connectionError && (
            <button disabled={busy} onClick={workday.refresh}>
              Дахин холбогдох
            </button>
          )}
          {session && !state?.linked && (
            <div className="task-only-status">
              <p>{session.title} · Зөвхөн даалгаврын цаг бүртгэж байна.</p>
              <button disabled={busy} onClick={workday.pause}>
                Даалгаврын цаг зогсоох
              </button>
            </div>
          )}
          {state && (
            <>
              <p className="muted">
                {state.linked
                  ? `${state.device_name} · ${state.username}`
                  : 'Эхний удаа энэ төхөөрөмжийг өөрийн бүртгэлтэй холбоно уу.'}
              </p>
              {state.another_account ? (
                <p>
                  Өөр account-ийн ажил үргэлжилж байна. Тэр account-аар нэвтэрч ажлаа дуусгана уу.
                </p>
              ) : !state.linked || relink ? (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (step < 3) setStep(step + 1);
                    else act('connect', { device_name: deviceName, consent });
                  }}
                >
                  <fieldset disabled={busy}>
                    <legend>Анхны тохиргоо · {step}/3</legend>
                    {step === 1 && (
                      <>
                        <p>1. Энэ төхөөрөмж {user.username} хэрэглэгчид хугацаа бүртгэнэ.</p>
                        <label>
                          Төхөөрөмжийн нэр
                          <input
                            required
                            maxLength={120}
                            value={deviceName}
                            onChange={(e) => setDeviceName(e.target.value)}
                          />
                        </label>
                      </>
                    )}
                    {step === 2 && (
                      <>
                        <p>
                          2. Идэвхтэй аппын нэр, ашигласан болон идэвхгүй хугацааг бүртгэнэ. Бичсэн
                          текст, URL, дэлгэцийн зураг хадгалахгүй.
                        </p>
                        <p>
                          Account-тай холбосны дараа WorkTrack нээлттэй байсан хугацаа мөн сарын
                          тайланд админд харагдана. Ажил түр зогсоосон үед ч програмын нээлттэй цаг
                          тоологдоно; бүрэн зогсоох бол WorkTrack-аа хаах эсвэл төхөөрөмжөө салгана.
                        </p>
                        <p>
                          Камер тусдаа товчоор асна. Зураг, видео хадгалахгүй; зөвхөн хүн байгаа
                          эсэх, илрүүлэлтийн итгэлцүүр бүртгэнэ.
                        </p>
                        <label className="toggle-field">
                          <input
                            type="checkbox"
                            checked={consent}
                            onChange={(e) => setConsent(e.target.checked)}
                          />
                          Мэдээлэл бүртгэхийг зөвшөөрч байна (2026-11)
                        </label>
                      </>
                    )}
                    {step === 3 && (
                      <p>
                        3. {deviceName} төхөөрөмжийг {user.username}-тай холбоно. Дараа нь “Ажил
                        эхлүүлэх” дарна; camera автоматаар асахгүй.
                      </p>
                    )}
                    <div className="desktop-actions">
                      {step > 1 && (
                        <button type="button" onClick={() => setStep(step - 1)}>
                          Буцах
                        </button>
                      )}
                      <button type="submit" disabled={step === 2 && !consent}>
                        {busy ? 'Холбож байна…' : step === 3 ? 'Төхөөрөмж холбох' : 'Үргэлжлүүлэх'}
                      </button>
                      {relink && (
                        <button type="button" onClick={() => setRelink(false)}>
                          Болих
                        </button>
                      )}
                    </div>
                  </fieldset>
                </form>
              ) : (
                <>
                  <form
                    className="workday-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      workday.start(selected);
                    }}
                  >
                    <label>
                      Хийх даалгавар
                      <select
                        value={validChoice ? selected : ''}
                        disabled={busy || working}
                        onChange={(event) => workday.selectTask(event.target.value)}
                        required
                      >
                        <option value="">Даалгавраа сонгоно уу</option>
                        {ownTasks.map((task) => (
                          <option key={task.id} value={task.id}>
                            {task.title}
                          </option>
                        ))}
                        <option value="none">Даалгаваргүй — зөвхөн аппын хэрэглээ</option>
                      </select>
                    </label>
                    {!ownTasks.length && (
                      <p className="muted">
                        Танд оноосон дуусаагүй даалгавар алга. Зөвхөн аппын хэрэглээгээ бүртгэж
                        болно.
                      </p>
                    )}
                    <p>
                      {taskRunning ? (
                        <>
                          <strong>{session.title}</strong> — даалгаврын цаг ажиллаж байна.
                        </>
                      ) : (
                        'Даалгавраа сонгоод нэг удаа эхлүүлнэ. Даалгаврын цаг болон аппын хэрэглээ хамт бүртгэгдэнэ.'
                      )}
                    </p>
                    <div className="desktop-actions workday-primary-actions">
                      {!working ? (
                        <button
                          type="submit"
                          disabled={busy || !validChoice || !work.sample || Boolean(work.error)}
                        >
                          {runningWork && state.paused ? 'Ажил үргэлжлүүлэх' : 'Ажил эхлүүлэх'}
                        </button>
                      ) : (
                        <button type="button" disabled={busy} onClick={workday.pause}>
                          Түр зогсоох
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={busy || (!runningWork && !state.camera_running && !session)}
                        onClick={workday.finish}
                      >
                        Ажил дуусгах
                      </button>
                    </div>
                    <small className="muted">
                      Эдгээр товч даалгаврын цаг болон аппын бүртгэлийг удирдана. Програм нээлттэй
                      байсан сарын цаг WorkTrack-ийг хаах хүртэл үргэлжилнэ.
                    </small>
                  </form>
                  <details className="camera-controls">
                    <summary>
                      Камер ·{' '}
                      {state.camera_running
                        ? state.paused
                          ? 'түр зогссон'
                          : 'асаалттай'
                        : 'унтраалттай'}
                    </summary>
                    <p>Камер хэрэглэх эсэхээ өөрөө сонгоно. Ажил эхлүүлэхэд автоматаар асахгүй.</p>
                    <div className="desktop-actions">
                      <button
                        disabled={
                          busy ||
                          (!state.camera_running &&
                            (!runningWork ||
                              state.paused ||
                              !state.camera_ready ||
                              state.preparing_camera))
                        }
                        onClick={() => act(state.camera_running ? 'camera-off' : 'camera-on')}
                      >
                        {state.camera_running ? 'Camera унтраах' : 'Camera асаах'}
                      </button>
                      {!state.camera_ready && (
                        <button
                          disabled={busy || state.preparing_camera}
                          onClick={() => act('prepare-camera')}
                        >
                          {state.preparing_camera ? 'Camera бэлтгэж байна…' : 'Camera бэлтгэх'}
                        </button>
                      )}
                    </div>
                  </details>
                  {state.errors?.length > 0 && (
                    <p role="alert">
                      {state.camera_error === 'permission'
                        ? 'Camera зөвшөөрөгдөөгүй. System Settings → Privacy & Security → Camera → WorkTrack Camera-ийг зөвшөөрөөд дахин асаана уу.'
                        : state.camera_error === 'setup'
                          ? 'Camera launcher бэлтгэгдсэнгүй. Camera бэлтгэх товчийг дарж, Command Line Tools болон Python суулгалтаа шалгана уу.'
                          : state.camera_error === 'startup'
                            ? 'Camera апп эхэлсэнгүй. macOS-ийн зөвшөөрлийн цонхыг шалгаад дахин асаана уу.'
                            : `${state.errors.includes('agent') ? 'Agent' : 'Camera'} зогссон байна. Зөвшөөрөл/нэвтрэлтээ шалгаад дахин холбоно уу.`}
                    </p>
                  )}
                  {state.camera_setup_error && (
                    <p role="alert">
                      Camera бэлтгэл амжилтгүй. Холболтоо шалгаад дахин бэлтгэнэ үү.
                    </p>
                  )}
                  <p className="muted">
                    Вебээс гарахад аппын бүртгэл үргэлжилж болно. Зогсоохдоо эхлээд “Ажил дуусгах”
                    дарна.
                  </p>
                  <details>
                    <summary>Төхөөрөмжийн нэмэлт үйлдэл</summary>
                    <div className="desktop-actions">
                      <button
                        disabled={busy || state.camera_running || state.preparing_camera}
                        onClick={() => act('prepare-camera')}
                      >
                        {state.preparing_camera
                          ? 'Camera бэлтгэж байна…'
                          : 'Камерын тохиргоог шинэчлэх'}
                      </button>
                      <button
                        disabled={busy || runningWork || state.camera_running}
                        onClick={() => {
                          setStep(1);
                          setConsent(false);
                          setRelink(true);
                        }}
                      >
                        Дахин холбох
                      </button>
                      <button disabled={busy} onClick={() => act('disconnect')}>
                        Холболт салгах
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => {
                          if (window.confirm('Agent, camera болон WorkTrack-ийг хаах уу?'))
                            act('quit');
                        }}
                      >
                        WorkTrack хаах
                      </button>
                    </div>
                  </details>
                </>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

export default function Today({ user, navigate, tasks, work, workday, busy }) {
  const [result, setResult] = useState(null),
    [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    const flight = { busy: false };
    async function load() {
      if (flight.busy) return;
      flight.busy = true;
      try {
        const data = await api('/api/me/today/', { signal: controller.signal });
        if (!controller.signal.aborted) {
          setResult(data);
          setError('');
        }
      } catch (failure) {
        if (!controller.signal.aborted && failure.name !== 'AbortError') setError(failure.message);
      } finally {
        flight.busy = false;
      }
    }
    load();
    const timer = setInterval(load, 30000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [user.id]);
  return (
    <section className="today-page">
      <header className="header">
        <div>
          <h1>Миний өнөөдөр</h1>
          <p>
            {user.username} · {result?.date || 'Өнөөдрийн мэдээлэл'}
          </p>
        </div>
      </header>
      <DesktopPanel
        key={user.id}
        user={user}
        tasks={tasks}
        work={work}
        workday={workday}
        busy={busy}
      />
      <section className="stats today-time-stats" aria-label="Хугацааны тойм">
        <TaskWorkClock work={work} card />
        <article className="stat-card" aria-label="Өнөөдрийн аппын хэрэглээ">
          <p className="eyebrow">Өнөөдөр</p>
          <p>Апп ашигласан</p>
          <h2>
            {result?.application_seconds != null ? duration(result.application_seconds) : '—'}
          </h2>
          <small>Идэвхгүй хугацааг хассан аппын бүртгэл.</small>
          <small>
            Идэвхгүй: {result?.idle_seconds != null ? duration(result.idle_seconds) : '—'} · Нийт
            бүртгэл: {result ? duration(result.tracked_seconds) : '—'}
          </small>
          {result && result.application_seconds == null && (
            <small>Шинэ тооцоог харахын тулд WorkTrack-аа дахин асаана уу.</small>
          )}
        </article>
        <LauncherClock user={user} card />
      </section>
      <p className="muted">
        Эдгээр цаг тусдаа утгатай тул хооронд нь нэмэхгүй. Аппын бүртгэл 30 секунд тутам
        шинэчлэгдэнэ.
      </p>
      {error && <p role="alert">{error}</p>}
      {!result && !error && <p>Өнөөдрийн мэдээлэл уншиж байна…</p>}
      {result && (
        <>
          <section className="stats today-task-stats">
            <article className="stat-card">
              <p>Дуусаагүй даалгавар</p>
              <h2>{result.open_tasks}</h2>
            </article>
            <article className="stat-card">
              <p>Хугацаа хэтэрсэн</p>
              <h2>{result.overdue_tasks}</h2>
            </article>
          </section>
          <section className="activity-detail-card">
            <h2>Өнөөдөр ашигласан аппууд</h2>
            <p>
              Сүүлд бүртгэгдсэн апп:{' '}
              {result.latest_application?.application || 'Одоогоор бүртгэлгүй'}
            </p>
            {result.applications.map((row) => (
              <div className="activity-row" key={row.application}>
                <span>{row.application}</span>
                <strong>{duration(row.seconds)}</strong>
              </div>
            ))}
          </section>
          <section className="activity-detail-card">
            <h2>Миний хийх ажлууд</h2>
            {!result.tasks.length && <p>Дуусаагүй даалгавар алга.</p>}
            {result.tasks.map((task) => (
              <div className="activity-row" key={task.id}>
                <span>{task.title}</span>
                <strong>{task.due_date || 'Хугацаа заагаагүй'}</strong>
              </div>
            ))}
            <button onClick={() => navigate('tasks')}>Даалгавраа харах</button>
          </section>
        </>
      )}
    </section>
  );
}

export function PasswordSettings() {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const controller = useRef(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function save(event) {
    event.preventDefault();
    if (busy) return;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    if (data.new_password !== data.confirm_password) {
      setError('Шинэ нууц үгүүд ижил байх ёстой.');
      return;
    }
    setBusy(true);
    setError('');
    controller.current = new AbortController();
    const signal = controller.current.signal;
    try {
      await api('/api/me/password/', { method: 'POST', body: JSON.stringify(data), signal });
      if (!signal.aborted) clearAuth('password_changed');
    } catch (failure) {
      if (!signal.aborted && failure.name !== 'AbortError') setError(failure.message);
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }
  return (
    <section>
      <h1>Миний бүртгэл</h1>
      <form className="task-form" onSubmit={save}>
        <h2>Нууц үг солих</h2>
        <p>
          Нууц үг солигдоход бүх session хүчингүй болно. Шинээр нэвтрээд төхөөрөмжөө дахин холбоно
          уу.
        </p>
        <fieldset disabled={busy}>
          <label>
            Одоогийн нууц үг
            <input
              required
              type="password"
              name="current_password"
              autoComplete="current-password"
              maxLength={256}
            />
          </label>
          <label>
            Шинэ нууц үг
            <input
              required
              type="password"
              name="new_password"
              autoComplete="new-password"
              minLength={8}
              maxLength={256}
            />
          </label>
          <label>
            Шинэ нууц үг давтах
            <input
              required
              type="password"
              name="confirm_password"
              autoComplete="new-password"
              minLength={8}
              maxLength={256}
            />
          </label>
          {error && <p role="alert">{error}</p>}
          <button type="submit">{busy ? 'Сольж байна…' : 'Нууц үг солих'}</button>
        </fieldset>
      </form>
    </section>
  );
}
