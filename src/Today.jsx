import { useCallback, useEffect, useId, useRef, useState } from 'react';
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
    'Камер бэлтгэгдээгүй байна. «Камер ашиглах» унтраалгыг дахин асаана уу. Дахин алдаа гарвал админдаа хандана уу.',
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
    return 'Ажлын бүртгэл гэнэт зогссон байна. «Ажил эхлүүлэх»-ийг дахин дарна уу. Болохгүй бол «Бусад тохиргоо» → «Дахин холбох».';
  return 'Камер гэнэт зогссон байна. «Камер ашиглах» унтраалгыг дахин асаана уу. Болохгүй бол WorkTrack-аа хааж дахин нээнэ үү.';
}

const RATINGS = [
  ['LOW', 'Бага'],
  ['MEDIUM', 'Дунд'],
  ['HIGH', 'Өндөр'],
];
const RATING_NAMES = Object.fromEntries(RATINGS);

/** Өнөөдрийн өөрийн үнэлгээ (AI туршилтын шошго): уншина, хадгална. */
function useSelfRating(userId) {
  const [rating, setRating] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    api('/api/me/self-rating/', { signal: controller.signal })
      .then((data) => setRating(data))
      .catch(() => {}); // Optional: the page works without it.
    return () => controller.abort();
  }, [userId]);
  async function save(label) {
    setRating(
      await api('/api/me/self-rating/', { method: 'PUT', body: JSON.stringify({ label }) }),
    );
  }
  return { label: rating?.label || null, loaded: rating !== null, save };
}

function RatingButtons({ current, onPick, busy }) {
  return (
    <div className="rating-buttons" role="group" aria-label="Өнөөдрийн бүтээмж">
      {RATINGS.map(([value, name]) => (
        <button
          type="button"
          key={value}
          className={current === value ? 'is-selected' : 'secondary-button'}
          aria-pressed={current === value}
          disabled={busy}
          onClick={() => onPick(value)}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

/** «Ажил дуусгах»-ын дараа: өнөөдөр хэр бүтээмжтэй байсныг өөрөө үнэлнэ. */
function RatingDialog({ current, onPick, onClose }) {
  const dialog = useRef(null);
  const [saving, setSaving] = useState(false),
    [failure, setFailure] = useState('');
  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    return () => element?.open && element.close();
  }, []);
  async function pick(value) {
    setSaving(true);
    setFailure('');
    try {
      await onPick(value);
      onClose();
    } catch (error) {
      setFailure(error.message);
      setSaving(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="consent-dialog"
      aria-labelledby="rating-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="rating-dialog">
        <h3 id="rating-title">Өнөөдөр хэр бүтээмжтэй байсан бэ?</h3>
        <RatingButtons current={current} onPick={pick} busy={saving} />
        <p className="muted">
          Таны өөрийн үнэлгээ. Албан ёсны оноонд нөлөөлөхгүй; нэргүйгээр AI судалгаанд ашиглагдана.
        </p>
        {failure && <p role="alert">{failure}</p>}
        <button type="button" className="secondary-button" onClick={onClose}>
          Дараа
        </button>
      </div>
    </dialog>
  );
}

/** Анх «Ажил эхлүүлэх» дарахад гарах жижиг цонх: юу бүртгэгдэхийг хэлээд зөвшөөрөл авна. */
function ConsentDialog({ user, busy, initialName, autostart, relink, onAccept, onCancel }) {
  const dialog = useRef(null);
  const [deviceName, setDeviceName] = useState(initialName);
  const [agree, setAgree] = useState(false);
  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    return () => element?.open && element.close();
  }, []);
  function submit(event) {
    event.preventDefault();
    onAccept({ device_name: deviceName.trim() || DEFAULT_DEVICE_NAME, consent: true });
  }
  return (
    <dialog
      ref={dialog}
      className="consent-dialog"
      aria-labelledby="consent-title"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form onSubmit={submit}>
        <h3 id="consent-title">
          {relink ? 'Компьютерийг дахин холбох' : 'Энэ компьютер дээр ажлаа бүртгэх'}
        </h3>
        <p>WorkTrack энэ компьютер дээрх ажлын цагийг {user.username}-д бүртгэнэ.</p>
        <ul className="consent-list">
          <li>
            <strong>Бүртгэнэ:</strong> ямар програм хэр удаан нээлттэй байсан, идэвхгүй хугацаа.
            Сарын тайланд админд харагдана.
          </li>
          <li>
            <strong>Бүртгэхгүй:</strong> бичсэн текст, вэб хаяг, дэлгэцийн зураг.
          </li>
          <li>
            <strong>Камер</strong> зөвхөн та өөрөө асаавал ажиллана; зураг хадгалахгүй.
          </li>
          {autostart && (
            <li>
              Компьютер асахад WorkTrack далд асна; бүртгэл таныг «Ажил эхлүүлэх» дартал эхлэхгүй.
            </li>
          )}
        </ul>
        <label>
          Компьютерийн нэр
          <input
            required
            maxLength={120}
            value={deviceName}
            onChange={(event) => setDeviceName(event.target.value)}
          />
        </label>
        <label className="toggle-field">
          <input
            type="checkbox"
            checked={agree}
            onChange={(event) => setAgree(event.target.checked)}
          />
          Зөвшөөрч байна
        </label>
        <div className="desktop-actions">
          <button type="submit" disabled={!agree || busy}>
            {relink ? 'Холбох' : 'Зөвшөөрөөд эхлүүлэх'}
          </button>
          <button type="button" className="secondary-button" onClick={onCancel}>
            Болих
          </button>
        </div>
      </form>
    </dialog>
  );
}

/** Даалгавраа сонгоод нэг том товчоор эхлүүлэх; ажиллаж байхад түр зогсоох, дуусгах. */
function WorkControls({
  user,
  tasks,
  state,
  work,
  workday,
  session,
  taskRunning,
  working,
  busy,
  onStart,
  onFinish,
}) {
  const selectId = useId();
  const paused = Boolean(state?.computer_running && state.paused);
  const ownTasks = tasks.filter((task) => task.employee === user.id && task.status !== 'Дууссан');
  const chosen = taskRunning ? String(session.task_id) : workday.choice || 'none';
  const selected =
    chosen === 'none' || ownTasks.some((task) => String(task.id) === chosen) ? chosen : 'none';
  const canFinish = state?.computer_running || state?.camera_running || session;
  function start(event) {
    event.preventDefault();
    const task = ownTasks.find((row) => String(row.id) === selected);
    onStart(selected, task ? task.title : '');
  }
  return (
    <form className="workday-form" onSubmit={start}>
      <div className="workday-field">
        <label htmlFor={selectId}>Хийх даалгавар</label>
        <select
          id={selectId}
          value={selected}
          disabled={busy || working}
          onChange={(event) => workday.selectTask(event.target.value)}
        >
          {ownTasks.map((task) => (
            <option key={task.id} value={task.id}>
              {task.title}
            </option>
          ))}
          <option value="none">Даалгаваргүй — зөвхөн компьютерийн цаг</option>
        </select>
      </div>
      <div className="desktop-actions workday-primary-actions">
        {working ? (
          <button type="button" disabled={busy} onClick={workday.pause}>
            Түр зогсоох
          </button>
        ) : (
          <button
            type="submit"
            className="start-button"
            disabled={busy || !work.sample || Boolean(work.error)}
          >
            {paused ? 'Ажил үргэлжлүүлэх' : 'Ажил эхлүүлэх'}
          </button>
        )}
        {canFinish && (
          <button type="button" className="secondary-button" disabled={busy} onClick={onFinish}>
            Ажил дуусгах
          </button>
        )}
      </div>
      {taskRunning && (
        <p className="muted">
          <strong>{session.title}</strong> даалгаврын цаг ажиллаж байна.
        </p>
      )}
    </form>
  );
}

/** Камерыг нэг унтраалгаар: анх асаахад шаардлагатай зүйлсийг өөрөө бэлдээд асаана. */
function CameraSwitch({ state, busy, act }) {
  const waiting = useRef(false);
  const working = state.computer_running && !state.paused;
  useEffect(() => {
    // Turned on before the camera was ready: switch it on once preparing has finished.
    if (waiting.current && state.camera_ready && !state.preparing_camera) {
      waiting.current = false;
      if (working && !state.camera_running) act('camera-on');
    }
    if (state.camera_setup_error) waiting.current = false;
  }, [
    state.camera_ready,
    state.preparing_camera,
    state.camera_setup_error,
    state.camera_running,
    working,
    act,
  ]);
  function toggle(event) {
    if (!event.target.checked) {
      waiting.current = false;
      act('camera-off');
    } else if (state.camera_ready) act('camera-on');
    else {
      waiting.current = true;
      if (!state.preparing_camera) act('prepare-camera');
    }
  }
  // Boolean(): an undefined value would make the switch uncontrolled and stop following the state.
  const on = Boolean(state.camera_running || state.preparing_camera);
  return (
    <div className="camera-switch">
      <label className="toggle-field">
        <input
          type="checkbox"
          checked={on}
          disabled={busy || (!on && !working)}
          onChange={toggle}
        />
        Камер ашиглах
      </label>
      <p className="muted">
        {state.preparing_camera
          ? 'Камерыг анх удаа бэлдэж байна (хэдэн минут). Бэлэн болмогц асна.'
          : !working && !state.camera_running
            ? 'Ажил эхлүүлсний дараа асааж болно. Зураг, бичлэг хадгалахгүй.'
            : 'Хүн байгаа эсэхийг л тэмдэглэнэ. Зураг, бичлэг хадгалахгүй.'}
      </p>
      {state.camera_setup_error && (
        <p role="alert">
          Камер бэлдэж чадсангүй. Интернэт холболтоо шалгаад унтраалгыг дахин асаана уу.
        </p>
      )}
    </div>
  );
}

/** Ховор хэрэглэгддэг тохиргоо: автоматаар асах, сануулга, дахин холбох, салгах, хаах. */
function MoreSettings({ state, busy, act, onRelink }) {
  const [confirming, setConfirming] = useState(false);
  return (
    <details className="more-settings">
      <summary>Бусад тохиргоо</summary>
      <div className="more-settings-body">
        {state.autostart_supported && !state.another_account && (
          <label className="toggle-field">
            <input
              type="checkbox"
              checked={Boolean(state.autostart_enabled)}
              disabled={busy}
              onChange={(event) => act(event.target.checked ? 'autostart-on' : 'autostart-off')}
            />
            Компьютер асахад WorkTrack-ийг автоматаар асаах
          </label>
        )}
        {state.autostart_note && <p className="muted">{state.autostart_note}</p>}
        {state.linked && (
          <label className="toggle-field">
            <input
              type="checkbox"
              checked={Boolean(state.reminders_enabled)}
              disabled={busy}
              onChange={(event) => act(event.target.checked ? 'reminders-on' : 'reminders-off')}
            />
            Ажил эхлүүлэхээ мартвал сануулах
          </label>
        )}
        <div className="desktop-actions">
          {state.linked && (
            <button
              type="button"
              disabled={busy || state.computer_running || state.camera_running}
              onClick={onRelink}
            >
              Дахин холбох
            </button>
          )}
          {state.linked && (
            <button type="button" disabled={busy} onClick={() => act('disconnect')}>
              Холболт салгах
            </button>
          )}
          {state.linked && state.camera_supported !== false && (
            <button
              type="button"
              disabled={busy || state.camera_running || state.preparing_camera}
              onClick={() => act('prepare-camera')}
            >
              Камерын тохиргоог шинэчлэх
            </button>
          )}
          {confirming ? (
            <>
              <button type="button" disabled={busy} onClick={() => act('quit')}>
                Тийм, WorkTrack хаах
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setConfirming(false)}
              >
                Болих
              </button>
            </>
          ) : (
            <button type="button" disabled={busy} onClick={() => setConfirming(true)}>
              WorkTrack хаах
            </button>
          )}
        </div>
        {confirming && <p className="muted">Хаавал ажлын бүртгэл болон камер зогсоно.</p>}
      </div>
    </details>
  );
}

export function DesktopPanel({ user, tasks, work, workday, busy, workedToday }) {
  const { state, error, connectionError, message, closed } = workday;
  const rating = useSelfRating(user.id);
  const [ratingOpen, setRatingOpen] = useState(false);
  const { session, running: taskRunning } = sessionTiming(work.sample, useTick());
  const [asking, setAsking] = useState(null); // null | 'start' | 'relink'
  const pendingStart = useRef(null);
  const paused = Boolean(state?.computer_running && state.paused);
  const working = Boolean((state?.computer_running && !state.paused) || taskRunning);
  const act = useCallback((action, body = {}) => workday.action(action, body), [workday]);
  function start(task, title) {
    if (!state?.linked) {
      // First time on this computer: ask once, then link and start in one go.
      pendingStart.current = { task, title };
      setAsking('start');
      return;
    }
    workday.start(task, title);
  }
  async function finish() {
    // The end of the day is when people know how it went: ask once, unless already answered.
    if ((await workday.finish()) && rating.loaded && !rating.label) setRatingOpen(true);
  }
  async function accept(body) {
    const next = asking === 'start' ? pendingStart.current : null;
    setAsking(null);
    if ((await workday.action('connect', body)) && next) workday.start(next.task, next.title);
  }
  return (
    <section className="desktop-panel" aria-label="Энэ компьютерийн удирдлага">
      <div className="workday-heading">
        <h2>Одоо хийх ажил</h2>
        <span className={`work-status ${working ? 'is-working' : ''}`}>
          {working ? 'Бүртгэж байна' : paused ? 'Түр зогссон' : 'Эхлээгүй'}
        </span>
      </div>
      {closed ? (
        <p role="status">WorkTrack хаагдаж байна. Дараа {launcherName}-аа нээгээрэй.</p>
      ) : (
        <>
          {state?.update && /^https?:\/\//i.test(state.update.download_url) && (
            <p role="status" className="work-reminder">
              WorkTrack-ийн шинэ хувилбар {state.update.version} гарлаа (энэ компьютерт{' '}
              {state.version}).{' '}
              <a href={state.update.download_url} target="_blank" rel="noreferrer">
                Татаж авах
              </a>
              . WorkTrack-аа хаагаад шинэ хувилбарыг хуучных нь оронд хуулна; таны мэдээлэл
              хадгалагдана.
            </p>
          )}
          {state?.reminder && (
            <p role="status" className="work-reminder">
              🔔 {state.reminder}
            </p>
          )}
          {error && <p role="alert">{error}</p>}
          {message && (
            <p role="status" className="work-feedback">
              {message}
            </p>
          )}
          {connectionError && (
            <>
              <p role="alert">{connectionError}</p>
              <button disabled={busy} onClick={workday.refresh}>
                Дахин холбогдох
              </button>
            </>
          )}
          {!state && !connectionError && <p>WorkTrack-тэй холбогдож байна…</p>}
          {session && !state?.linked && !asking && (
            <div className="task-only-status">
              <p>{session.title} · Зөвхөн даалгаврын цаг бүртгэж байна.</p>
              <button disabled={busy} onClick={workday.pause}>
                Даалгаврын цаг зогсоох
              </button>
            </div>
          )}
          {state && state.another_account && (
            <p>
              Энэ компьютер дээр өөр хэрэглэгчийн ажил үргэлжилж байна. Тэр хэрэглэгчээр нэвтэрч
              ажлаа дуусгана уу.
            </p>
          )}
          {state && !state.another_account && (
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
                onStart={start}
                onFinish={finish}
              />
              {rating.loaded && !rating.label && workedToday && !working && (
                <div className="rating-prompt">
                  <p>Өнөөдөр хэр бүтээмжтэй байсан бэ?</p>
                  <RatingButtons current={null} onPick={rating.save} busy={busy} />
                </div>
              )}
              {rating.label && (
                <p className="muted rating-line">
                  Өнөөдрийн үнэлгээ: <strong>{RATING_NAMES[rating.label]}</strong> ·{' '}
                  <button type="button" className="link-button" onClick={() => setRatingOpen(true)}>
                    Өөрчлөх
                  </button>
                </p>
              )}
              {state.linked && state.camera_supported !== false && (
                <CameraSwitch state={state} busy={busy} act={act} />
              )}
              {state.errors?.length > 0 && <p role="alert">{deviceErrorMessage(state)}</p>}
              {state.linked && (
                <p className="muted device-line">
                  {state.device_name} · {state.username}
                </p>
              )}
            </>
          )}
          {state && (
            <MoreSettings
              state={state}
              busy={busy}
              act={act}
              onRelink={() => setAsking('relink')}
            />
          )}
          {ratingOpen && (
            <RatingDialog
              current={rating.label}
              onPick={rating.save}
              onClose={() => setRatingOpen(false)}
            />
          )}
          {asking && state && (
            <ConsentDialog
              user={user}
              busy={busy}
              initialName={state.device_name || DEFAULT_DEVICE_NAME}
              autostart={state.autostart_on_connect}
              relink={asking === 'relink'}
              onAccept={accept}
              onCancel={() => setAsking(null)}
            />
          )}
        </>
      )}
    </section>
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
        workedToday={Boolean(result?.application_seconds)}
      />
      <section className="stats today-time-stats" aria-label="Өнөөдрийн цаг">
        <TaskWorkClock work={work} card />
        <article className="stat-card" aria-label="Өнөөдрийн компьютерийн цаг">
          <p className="eyebrow">Өнөөдөр</p>
          <p>Компьютер дээр ажилласан</p>
          <h2>
            {result?.application_seconds != null ? durationText(result.application_seconds) : '—'}
          </h2>
          <small>Идэвхгүй байсан хугацааг хассан.</small>
        </article>
      </section>
      {error && <p role="alert">{error}</p>}
      {!result && !error && <p>Өнөөдрийн мэдээлэл уншиж байна…</p>}
      {result && (
        <section className="activity-detail-card">
          <h2>
            Миний хийх ажлууд
            {result.overdue_tasks > 0 && (
              <span className="overdue-count"> · {result.overdue_tasks} хугацаа хэтэрсэн</span>
            )}
          </h2>
          {!result.tasks.length && <p>Дуусаагүй даалгавар алга.</p>}
          {result.tasks.map((task) => (
            <div className="activity-row" key={task.id}>
              <span>{task.title}</span>
              <strong>{task.due_date || 'Хугацаа заагаагүй'}</strong>
            </div>
          ))}
          <button onClick={() => navigate('tasks')}>Даалгавраа харах</button>
        </section>
      )}
      <WeekSummary key={`week:${user.id}`} user={user} />
      <details className="today-more">
        <summary>Дэлгэрэнгүй</summary>
        {result && (
          <section className="activity-detail-card">
            <h2>Өнөөдөр ашигласан програмууд</h2>
            <p>
              Сүүлд ашигласан: {result.latest_application?.application || 'Одоогоор бүртгэлгүй'}
            </p>
            {result.applications.map((row) => (
              <div className="activity-row" key={row.application}>
                <span>{row.application}</span>
                <strong>{durationText(row.seconds)}</strong>
              </div>
            ))}
            <p className="muted">
              Идэвхгүй {result.idle_seconds != null ? durationText(result.idle_seconds) : '—'}.
            </p>
          </section>
        )}
        <section className="stats" aria-label="WorkTrack нээлттэй цаг">
          <LauncherClock user={user} card />
        </section>
        <p className="muted">
          Даалгаврын цаг, компьютер дээр ажилласан цаг, WorkTrack нээлттэй цаг гурав өөр зүйлийг
          хэмждэг тул хооронд нь нэмэхгүй. 30 секунд тутам шинэчлэгдэнэ.
        </p>
      </details>
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
