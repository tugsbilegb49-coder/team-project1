import { useEffect, useId, useRef, useState } from 'react';
import { api, clearAuth } from './api';
import { LauncherClock, TaskWorkClock } from './WorkClocks';
import { durationText, sessionTiming, useTick } from './taskTime';
import { usePolling } from './usePolling';
import { launcherName } from './platform';
import WeekSummary from './WeekSummary';

const DEFAULT_DEVICE_NAME = 'Миний компьютер';

const CAMERA_ERRORS = {
  permission:
    'Камер зөвшөөрөгдөөгүй байна. System Settings → Privacy & Security → Camera → WorkTrack Camera-г асаагаад дахин оролдоно уу.',
  setup:
    'Камер бэлтгэгдээгүй байна. «Камер бэлтгэх» товчийг дарна уу. Дахин алдаа гарвал админдаа хандана уу.',
  startup: 'Камер асахгүй байна. macOS зөвшөөрөл асуусан бол зөвшөөрөөд дахин оролдоно уу.',
};

// Windows-д тусдаа зөвшөөрлийн цонх гардаггүй; камер зүгээр л нээгдэхгүй.
const WINDOWS_CAMERA_PERMISSION =
  'Камер нээгдсэнгүй. Windows Settings → Privacy & security → Camera дээр "Camera access" болон "Let desktop apps access your camera"-г асаагаад дахин оролдоно уу. Өөр програм камер ашиглаж байвал хаана уу.';

function deviceErrorMessage(state) {
  if (state.camera_error === 'permission' && state.platform === 'Windows')
    return WINDOWS_CAMERA_PERMISSION;
  if (CAMERA_ERRORS[state.camera_error]) return CAMERA_ERRORS[state.camera_error];
  if (state.errors.includes('agent'))
    return 'Аппын бүртгэл гэнэт зогссон байна. «Ажил эхлүүлэх»-ийг дахин дарна уу. Болохгүй бол «Төхөөрөмжийн нэмэлт үйлдэл» → «Дахин холбох».';
  return 'Камер гэнэт зогссон байна. «Камер асаах»-ыг дахин дарна уу. Болохгүй бол WorkTrack-аа хааж дахин нээнэ үү.';
}

/** Энэ компьютерийг хэрэглэгчийн бүртгэлтэй холбох 3 алхам. */
function DeviceSetup({ user, busy, initialName, autostart, onConnect, onCancel }) {
  const [step, setStep] = useState(1);
  const [deviceName, setDeviceName] = useState(initialName);
  const [consent, setConsent] = useState(false);
  function submit(event) {
    event.preventDefault();
    if (step < 3) setStep(step + 1);
    else onConnect({ device_name: deviceName, consent });
  }
  return (
    <form onSubmit={submit}>
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
                onChange={(event) => setDeviceName(event.target.value)}
              />
            </label>
          </>
        )}
        {step === 2 && (
          <>
            <p>2. Юуг бүртгэх вэ:</p>
            <ul className="consent-list">
              <li>
                <strong>Бүртгэнэ:</strong> идэвхтэй аппын нэр, ашигласан болон идэвхгүй хугацаа,
                WorkTrack нээлттэй байсан хугацаа. Эдгээр нь сарын тайланд админд харагдана.
              </li>
              <li>
                <strong>Бүртгэхгүй:</strong> бичсэн текст, вэб хаяг (URL), дэлгэцийн зураг.
              </li>
              <li>
                <strong>Камер:</strong> зөвхөн та өөрөө асаана. Зураг, видео хадгалахгүй; хүн байгаа
                эсэх, түүний итгэлцүүрийг л бүртгэнэ.
              </li>
              <li>
                «Түр зогсоох» үед ч WorkTrack нээлттэй цаг тоологдоно. Бүрэн зогсоох бол
                WorkTrack-аа хаах эсвэл төхөөрөмжөө салгана.
              </li>
              <li>
                <strong>Сануулга:</strong> ажил эхлүүлэхээ мартсан эсэхийг мэдэхийн тулд зөвхөн
                сүүлд товшсоноос хойших хугацааг шалгана. Үүнийг хадгалахгүй, илгээхгүй;
                «Төхөөрөмжийн нэмэлт үйлдэл»-ээс унтрааж болно.
              </li>
              {autostart && (
                <li>
                  <strong>Автоматаар асах:</strong> компьютер асахад WorkTrack далд асна. Бүртгэл
                  эхлэхгүй, «Ажил эхлүүлэх»-ийг та өөрөө дарна. Энэ хуудаснаас унтрааж болно.
                </li>
              )}
            </ul>
            <label className="toggle-field">
              <input
                type="checkbox"
                checked={consent}
                onChange={(event) => setConsent(event.target.checked)}
              />
              Мэдээлэл бүртгэхийг зөвшөөрч байна (2026-11)
            </label>
          </>
        )}
        {step === 3 && (
          <p>
            3. «{deviceName}» төхөөрөмжийг {user.username}-тай холбоно. Дараа нь «Ажил эхлүүлэх»
            дарна; камер автоматаар асахгүй.
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
          {onCancel && (
            <button type="button" onClick={onCancel}>
              Болих
            </button>
          )}
        </div>
      </fieldset>
    </form>
  );
}

/** Даалгавар сонгоод ажил эхлүүлэх, түр зогсоох, дуусгах. */
function WorkControls({ user, tasks, state, work, workday, session, taskRunning, working, busy }) {
  const selectId = useId();
  const paused = state.computer_running && state.paused;
  const ownTasks = tasks.filter((task) => task.employee === user.id && task.status !== 'Дууссан');
  const selected = taskRunning ? String(session.task_id) : workday.choice;
  const validChoice = selected === 'none' || ownTasks.some((task) => String(task.id) === selected);
  const canFinish = state.computer_running || state.camera_running || session;
  function submit(event) {
    event.preventDefault();
    workday.start(selected);
  }
  return (
    <form className="workday-form" onSubmit={submit}>
      <div className="workday-field">
        <label htmlFor={selectId}>Хийх даалгавар</label>
        <select
          id={selectId}
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
      </div>
      {!ownTasks.length && (
        <p className="muted">
          Танд оноосон дуусаагүй даалгавар алга. Зөвхөн аппын хэрэглээгээ бүртгэж болно.
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
        {working ? (
          <button type="button" disabled={busy} onClick={workday.pause}>
            Түр зогсоох
          </button>
        ) : (
          <button
            type="submit"
            disabled={busy || !validChoice || !work.sample || Boolean(work.error)}
          >
            {paused ? 'Ажил үргэлжлүүлэх' : 'Ажил эхлүүлэх'}
          </button>
        )}
        <button type="button" disabled={busy || !canFinish} onClick={workday.finish}>
          Ажил дуусгах
        </button>
      </div>
      <small className="muted">
        Эдгээр товч даалгаврын цаг болон аппын бүртгэлийг удирдана. Програм нээлттэй байсан сарын
        цаг WorkTrack-ийг хаах хүртэл үргэлжилнэ.
      </small>
    </form>
  );
}

/** Камерыг ажил эхэлсэн, түр зогсоогоогүй үед л асаана. */
function CameraControls({ state, busy, act }) {
  const canTurnOn =
    state.computer_running && !state.paused && state.camera_ready && !state.preparing_camera;
  const status = state.camera_running
    ? state.paused
      ? 'түр зогссон'
      : 'асаалттай'
    : 'унтраалттай';
  return (
    <details className="camera-controls">
      <summary>Камер · {status}</summary>
      <p>Камер хэрэглэх эсэхээ өөрөө сонгоно. Ажил эхлүүлэхэд автоматаар асахгүй.</p>
      <div className="desktop-actions">
        <button
          disabled={busy || (!state.camera_running && !canTurnOn)}
          onClick={() => act(state.camera_running ? 'camera-off' : 'camera-on')}
        >
          {state.camera_running ? 'Камер унтраах' : 'Камер асаах'}
        </button>
        {!state.camera_ready && (
          <button disabled={busy || state.preparing_camera} onClick={() => act('prepare-camera')}>
            {state.preparing_camera ? 'Камер бэлтгэж байна…' : 'Камер бэлтгэх'}
          </button>
        )}
      </div>
    </details>
  );
}

/** Ховор хэрэглэгддэг үйлдлүүд: камер шинэчлэх, дахин холбох, салгах, хаах. */
function DeviceMenu({ state, busy, act, onRelink }) {
  function quit() {
    if (window.confirm('WorkTrack-ийг хаах уу? Аппын бүртгэл болон камер зогсоно.')) act('quit');
  }
  return (
    <details>
      <summary>Төхөөрөмжийн нэмэлт үйлдэл</summary>
      <div className="desktop-actions">
        {state.camera_supported !== false && (
          <button
            disabled={busy || state.camera_running || state.preparing_camera}
            onClick={() => act('prepare-camera')}
          >
            {state.preparing_camera ? 'Камер бэлтгэж байна…' : 'Камерын тохиргоог шинэчлэх'}
          </button>
        )}
        <button
          disabled={busy || state.computer_running || state.camera_running}
          onClick={onRelink}
        >
          Дахин холбох
        </button>
        <button
          disabled={busy}
          onClick={() => act(state.reminders_enabled ? 'reminders-off' : 'reminders-on')}
        >
          {state.reminders_enabled ? 'Сануулга унтраах' : 'Сануулга асаах'}
        </button>
        <button disabled={busy} onClick={() => act('disconnect')}>
          Холболт салгах
        </button>
        <button disabled={busy} onClick={quit}>
          WorkTrack хаах
        </button>
      </div>
    </details>
  );
}

export function DesktopPanel({ user, tasks, work, workday, busy }) {
  const { state, error, connectionError, message, closed } = workday;
  const { session, running: taskRunning } = sessionTiming(work.sample, useTick());
  const [relink, setRelink] = useState(false);
  const paused = Boolean(state?.computer_running && state.paused);
  const working = Boolean((state?.computer_running && !state.paused) || taskRunning);
  async function act(action, body = {}) {
    if ((await workday.action(action, body)) && action === 'connect') setRelink(false);
  }
  return (
    <section className="desktop-panel" aria-label="Энэ компьютерийн удирдлага">
      <div className="workday-heading">
        <div>
          <p className="eyebrow">Эхлэх → Ажиллах → Түр зогсоох / Дуусгах</p>
          <h2>Одоо хийх ажил</h2>
        </div>
        <span className={`work-status ${working ? 'is-working' : ''}`}>
          {working ? 'Бүртгэж байна' : paused ? 'Түр зогссон' : 'Эхлээгүй'}
        </span>
      </div>
      {closed ? (
        <p role="status">WorkTrack хаагдаж байна. Дараа {launcherName}-аа нээгээрэй.</p>
      ) : (
        <>
          {error && <p role="alert">{error}</p>}
          {message && (
            <p role="status" className="work-feedback">
              {message}
            </p>
          )}
          {state?.reminder && (
            <p role="status" className="work-reminder">
              🔔 {state.reminder}
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
                  Энэ компьютер дээр өөр хэрэглэгчийн ажил үргэлжилж байна. Тэр хэрэглэгчээр нэвтэрч
                  ажлаа дуусгана уу.
                </p>
              ) : !state.linked || relink ? (
                <DeviceSetup
                  user={user}
                  busy={busy}
                  initialName={state.device_name || DEFAULT_DEVICE_NAME}
                  autostart={state.autostart_on_connect}
                  onConnect={(body) => act('connect', body)}
                  onCancel={relink ? () => setRelink(false) : null}
                />
              ) : (
                <>
                  <WorkControls
                    user={user}
                    tasks={tasks}
                    state={state}
                    work={work}
                    workday={workday}
                    session={session}
                    taskRunning={taskRunning}
                    working={working}
                    busy={busy}
                  />
                  {state.camera_supported !== false && (
                    <CameraControls state={state} busy={busy} act={act} />
                  )}
                  {state.errors?.length > 0 && <p role="alert">{deviceErrorMessage(state)}</p>}
                  {state.camera_setup_error && (
                    <p role="alert">
                      Камер бэлтгэж чадсангүй. Интернэт холболтоо шалгаад «Камер бэлтгэх»-ийг дахин
                      дарна уу.
                    </p>
                  )}
                  <p className="muted">
                    Вебээс гарахад аппын бүртгэл үргэлжилж болно. Зогсоохдоо эхлээд “Ажил дуусгах”
                    дарна.
                  </p>
                  <DeviceMenu
                    state={state}
                    busy={busy}
                    act={act}
                    onRelink={() => setRelink(true)}
                  />
                </>
              )}
              {state.autostart_supported && !state.another_account && (
                <AutostartSwitch state={state} busy={busy} act={act} />
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

function AutostartSwitch({ state, busy, act }) {
  return (
    <div className="autostart-field">
      <label className="toggle-field">
        <input
          type="checkbox"
          checked={state.autostart_enabled}
          disabled={busy}
          onChange={(event) => act(event.target.checked ? 'autostart-on' : 'autostart-off')}
        />
        Компьютер асахад WorkTrack-ийг автоматаар асаах
      </label>
      <p className="muted">
        Далд асна, browser нээгдэхгүй. Бүртгэл «Ажил эхлүүлэх» дарсны дараа л эхэлнэ. WorkTrack-ийн
        дүрс дээр дахин дарахад энэ хуудас нээгдэнэ.
      </p>
    </div>
  );
}

export default function Today({ user, navigate, tasks, work, workday, busy }) {
  const [result, setResult] = useState(null),
    [error, setError] = useState('');
  usePolling(
    async (signal) => {
      try {
        const data = await api('/api/me/today/', { signal });
        if (!signal.aborted) {
          setResult(data);
          setError('');
        }
      } catch (failure) {
        if (!signal.aborted && failure.name !== 'AbortError') setError(failure.message);
      }
    },
    30000,
    user.id,
  );
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
          <p>Компьютер дээр ажилласан</p>
          <h2>
            {result?.application_seconds != null ? durationText(result.application_seconds) : '—'}
          </h2>
          <small>
            Идэвхгүй {result?.idle_seconds != null ? durationText(result.idle_seconds) : '—'}-ийг
            хассан.
          </small>
          {result && result.application_seconds == null && (
            <small>Шинэ тооцоог харахын тулд WorkTrack-аа дахин асаана уу.</small>
          )}
        </article>
        <LauncherClock user={user} card />
      </section>
      <p className="muted">
        Гурван цаг өөр өөр зүйлийг хэмждэг тул хооронд нь нэмэхгүй. 30 секунд тутам шинэчлэгдэнэ.
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
                <strong>{durationText(row.seconds)}</strong>
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
      <WeekSummary key={`week:${user.id}`} user={user} />
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
          Нууц үг солигдоход бүх төхөөрөмж дээрх нэвтрэлт дуусна. Шинэ нууц үгээр нэвтрээд
          төхөөрөмжөө дахин холбоно уу.
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
