import { useEffect, useRef, useState } from 'react';
import { api, downloadReport } from './api';

const errorLabels = {
  network: 'Холболтын алдаа',
  authentication: 'Дахин нэвтрэх шаардлагатай',
  permission: 'Зөвшөөрлийг шалгана уу',
  storage: 'Хадгалах алдаа',
  login_changed: 'Нэвтэрсэн хэрэглэгч солигдсон — төхөөрөмжөө дахин холбоно уу',
  invalid_event: 'Буруу бүртгэл',
  legacy_queue: 'Хуучин хадгалагдсан бүртгэл аль хэрэглэгчийнх болохыг шалгах шаардлагатай',
};
const stateLabels = {
  online: 'Ажиллаж байна',
  paused: 'Түр зогссон',
  offline: 'Холболтгүй',
  disabled: 'Идэвхгүй',
};
function when(value) {
  return value
    ? new Intl.DateTimeFormat('mn-MN', {
        timeZone: 'Asia/Ulaanbaatar',
        dateStyle: 'short',
        timeStyle: 'medium',
      }).format(new Date(value))
    : 'Мэдээлэлгүй';
}

function usePolling(path, user) {
  const [result, setResult] = useState(null);
  const [reload, setReload] = useState(0);
  const inFlight = useRef(new Map());
  const key = `${path}:${user.id}:${user.role}:${user.department}:${reload}`;
  useEffect(() => {
    const controller = new AbortController();
    const requests = inFlight.current;
    async function read() {
      if (requests.get(key) === controller) return;
      requests.set(key, controller);
      try {
        const data = await api(path, { signal: controller.signal });
        if (!controller.signal.aborted) setResult({ key, data, error: '' });
      } catch (failure) {
        if (!controller.signal.aborted && failure.name !== 'AbortError')
          setResult((previous) => ({
            key,
            data: previous?.key === key ? previous.data : null,
            error: failure.message,
          }));
      } finally {
        if (requests.get(key) === controller) requests.delete(key);
      }
    }
    read();
    const timer = setInterval(read, 30000);
    return () => {
      clearInterval(timer);
      controller.abort();
      if (requests.get(key) === controller) requests.delete(key);
    };
  }, [path, key]);
  return {
    data: result?.key === key ? result.data : null,
    error: result?.key === key ? result.error : '',
    refresh: () => setReload((value) => value + 1),
  };
}

export function Notifications({ user, navigate }) {
  const { data, error } = usePolling('/api/notifications/', user);
  const names = {
    task_overdue: 'Хугацаа хэтэрсэн',
    task_due_today: 'Өнөөдөр дуусах',
    agent_offline: 'Төхөөрөмж холболтгүй',
    task_transfer: 'Даалгавар шилжүүлэх хүсэлт',
    upload_error: 'Илгээлтийн алдаа',
    queue_pending: 'Илгээгдээгүй бүртгэл байна',
    backup_failed: 'Backup амжилтгүй',
    backup_stale: 'Backup удаан хийгдээгүй. Сүүлийнх',
  };
  // Device problems open the device list for admins; others see their own computer on «Миний өнөөдөр».
  const target = (kind) =>
    kind.startsWith('task_')
      ? 'tasks'
      : kind.startsWith('backup_')
        ? 'settings'
        : user.is_admin
          ? 'agents'
          : 'today';
  return (
    <details className="notification-box">
      <summary>Мэдэгдэл ({data?.count ?? 0})</summary>
      {error && <p role="status">Мэдэгдэл шинэчлэгдсэнгүй: {error}</p>}
      {data?.items?.length === 0 && <p>Шинэ мэдэгдэл алга.</p>}
      {data?.items?.map((item) => (
        <div className="activity-row" key={item.id}>
          <span>
            {names[item.kind]}: {item.message}
            {item.error_code ? ` — ${errorLabels[item.error_code] || 'Алдаа'}` : ''}
          </span>
          <button type="button" onClick={() => navigate(target(item.kind))}>
            Харах
          </button>
        </div>
      ))}
      {data?.truncated && (
        <p>Олон мэдэгдэл байна. Ажилтан/төхөөрөмжийн жагсаалтаас үргэлжлүүлэн шалгана уу.</p>
      )}
    </details>
  );
}

function Pager({ data, page, setPage }) {
  return (
    <div className="activity-controls">
      <button
        type="button"
        disabled={page === 1 || !data}
        onClick={() => setPage((value) => value - 1)}
      >
        Өмнөх
      </button>
      <span>
        Хуудас {page} · Нийт {data?.count ?? 0}
      </span>
      <button type="button" disabled={!data?.next} onClick={() => setPage((value) => value + 1)}>
        Дараах
      </button>
    </div>
  );
}

const KIND_NAMES = { computer: 'Компьютер', camera: 'Камер' };

/** Компьютер бүр холбогдсон эсэх; нарийн мэдээлэл «Дэлгэрэнгүй» дотор. */
export function AgentStatus({ user }) {
  const [page, setPage] = useState(1);
  const { data, error, refresh } = usePolling(`/api/agent-status/?page=${page}`, user);
  return (
    <section className="task-section">
      <h1>Төхөөрөмжийн төлөв</h1>
      <p>
        Компьютер бүр WorkTrack-тай холбогдсон эсэхийг харуулна. 30 секунд тутам шинэчлэгдэнэ; 1.5
        минутаас удаан мэдээ ирээгүй бол «Холболтгүй».
      </p>
      <button type="button" onClick={refresh}>
        Төлөв шинэчлэх
      </button>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p>Уншиж байна…</p>}
      {data?.results?.length === 0 && <p>Бүртгэлтэй төхөөрөмж алга.</p>}
      {data?.results?.map((device) => {
        const main = device.agents.find((agent) => agent.kind === 'computer') || device.agents[0];
        const problems = device.agents.filter((agent) => agent.error_code);
        return (
          <article className="activity-detail-card device-card" key={device.id}>
            <div className="device-head">
              <h2>{device.name}</h2>
              <span className={`device-state state-${main?.state || 'none'}`}>
                {main ? stateLabels[main.state] : 'Мэдээ ирээгүй'}
              </span>
            </div>
            <p className="muted">
              {device.employee_name} · {device.platform}
              {!device.enabled ? ' · Идэвхгүй' : ''}
            </p>
            {!device.agents.length && (
              <p>
                Энэ компьютер WorkTrack-аас хараахан мэдээ илгээгээгүй. WorkTrack-аа нээгээд «Ажил
                эхлүүлэх» дарна уу.
              </p>
            )}
            {problems.map((agent) => (
              <p role="status" key={agent.kind}>
                {KIND_NAMES[agent.kind] || agent.kind}:{' '}
                {errorLabels[agent.error_code] || 'Алдаа гарсан'}
              </p>
            ))}
            {device.agents.length > 0 && (
              <details>
                <summary>Дэлгэрэнгүй</summary>
                {device.agents.map((agent) => (
                  <div key={agent.kind} aria-label={`${device.name} ${agent.kind}`}>
                    <h3>
                      {KIND_NAMES[agent.kind] || agent.kind} — {stateLabels[agent.state]}
                    </h3>
                    <div className="activity-row">
                      <span>Сүүлд холбогдсон</span>
                      <strong>{when(agent.seen_at)}</strong>
                    </div>
                    <div className="activity-row">
                      <span>Сүүлд бүртгэл илгээсэн</span>
                      <strong>{when(agent.last_upload_at)}</strong>
                    </div>
                    <div className="activity-row">
                      <span>Илгээгдэхийг хүлээж буй бүртгэл</span>
                      <strong>{agent.queue_count}</strong>
                    </div>
                    <p className="muted">
                      Програмын хувилбар {agent.agent_version || '—'} · Тохиргоо{' '}
                      {agent.settings_version}
                    </p>
                  </div>
                ))}
              </details>
            )}
          </article>
        );
      })}
      <Pager data={data} page={page} setPage={setPage} />
    </section>
  );
}

export function AuditHistory({ user }) {
  const [page, setPage] = useState(1);
  const { data, error } = usePolling(`/api/audit/?page=${page}`, user);
  const actions = {
    create: 'Үүсгэсэн',
    update: 'Зассан',
    delete: 'Устгасан',
    configure: 'Тохируулсан',
    grant: 'Зөвшөөрсөн',
    revoke: 'Цуцалсан',
    export: 'Экспортолсон',
    password_change: 'Нууц үг сольсон',
    password_reset_code: 'Нууц үг сэргээх код үүсгэсэн',
    password_reset: 'Кодоор нууц үгээ шинэчилсэн',
    admin_change: 'Админ зассан',
    transfer_request: 'Шилжүүлэх хүсэлт',
    transfer_accept: 'Шилжүүлгийг зөвшөөрсөн',
    transfer_decline: 'Шилжүүлгээс татгалзсан',
    transfer_cancel: 'Шилжүүлгийг цуцалсан',
    progress: 'Гүйцэтгэлийн хувь',
    work_start: 'Даалгаврын цаг эхлүүлсэн',
    work_stop: 'Даалгаврын цаг зогсоосон',
  };
  const resources = {
    task: 'Даалгавар',
    user: 'Хэрэглэгч',
    consent: 'Consent',
    report: 'Тайлан',
    monitoring_settings: 'Тохиргоо',
  };
  const fields = {
    employee_id: 'Ажилтан',
    title: 'Гарчиг',
    status: 'Төлөв',
    due_date: 'Дуусах хугацаа',
    quality_score: 'Чанарын үнэлгээ',
    completed_at: 'Дууссан цаг',
    role: 'Эрх',
    username: 'Хэрэглэгчийн нэр',
    is_active: 'Идэвхтэй',
    department_id: 'Хэлтэс',
    productive_apps: 'Ажилд тооцох аппууд',
    camera_threshold: 'Камерын итгэлцлийн босго',
    presence_log_retention_days: 'Камерын түр файл хадгалах хоног',
    activity_retention_days: 'Өгөгдлийн санд хадгалах хоног',
    automatic_retention: 'Автомат цэвэрлэгээ',
    client_version: 'Ажилтны аппын хувилбар',
    work_days: 'Ажлын өдрүүд',
    work_start: 'Ажил эхлэх цаг',
    work_end: 'Ажил дуусах цаг',
    client_download_url: 'Аппын татах холбоос',
    records_revoked: 'Цуцалсан зөвшөөрөл',
    policy_version: 'Зөвшөөрлийн хувилбар',
  };
  return (
    <section className="task-section">
      <h1>Өөрчлөлтийн түүх</h1>
      <p>
        Таны эрхийн хүрээнд хэн, юуг, хэзээ өөрчилснийг харуулна. Нууц үг, нэвтрэх түлхүүр
        хадгалахгүй.
      </p>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p>Уншиж байна…</p>}
      {data?.results?.length === 0 && <p>Өөрчлөлт бүртгэгдээгүй.</p>}
      {data?.results?.map((entry) => (
        <article className="activity-detail-card" key={entry.id}>
          <h2>
            {entry.actor_label} · {actions[entry.action] || entry.action}
          </h2>
          <p>
            {resources[entry.resource] || entry.resource} #{entry.object_id} ·{' '}
            {when(entry.created_at)}
          </p>
          <ul>
            {Object.entries(entry.changes).map(([field, change]) => (
              <li key={field}>
                {fields[field] || field}:{' '}
                {change && typeof change === 'object' && 'before' in change
                  ? `${JSON.stringify(change.before)} → ${JSON.stringify(change.after)}`
                  : JSON.stringify(change)}
              </li>
            ))}
          </ul>
        </article>
      ))}
      <Pager data={data} page={page} setPage={setPage} />
    </section>
  );
}

/** Админд: backup-ийн төлөв, хоёр дахь хуулбарын хавтас, оффисын серверийн холбох хаяг. */
export function ServerStatus({ user }) {
  const { data, error, refresh } = usePolling('/api/server-status/', user);
  const [folder, setFolder] = useState(null);
  const [saving, setSaving] = useState(false),
    [feedback, setFeedback] = useState(null);
  const backup = data?.backup,
    status = backup?.status,
    share = data?.share;
  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setFeedback(null);
    try {
      await api('/api/server-status/', {
        method: 'PATCH',
        body: JSON.stringify({ backup_copy_dir: (folder ?? backup.copy_dir).trim() }),
      });
      setFolder(null);
      setFeedback({
        ok: true,
        text: 'Хадгаллаа. Дараагийн backup (нэг цагийн дотор) энд хуулагдана.',
      });
      refresh();
    } catch (failure) {
      const detail = failure.details?.backup_copy_dir;
      setFeedback({ ok: false, text: Array.isArray(detail) ? detail.join(' ') : failure.message });
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="task-section" aria-label="Сервер ба backup">
      <h1>Сервер ба backup</h1>
      {error && <p role="alert">{error}</p>}
      {share && (
        <div className="server-share">
          <h2>Ажилтны компьютерийг холбох</h2>
          <p>Ажилтны WorkTrack-ийн «Сервертэй холбох» хуудсанд эдгээрийг оруулна:</p>
          <p>
            Хаяг: <code>{share.addresses[0]}</code>
            {share.addresses.length > 1 && (
              <span className="muted"> (эсвэл {share.addresses.slice(1).join(', ')})</span>
            )}
          </p>
          <p>
            Серверийн код: <code>{share.code}</code>
          </p>
          <p className="muted">
            Код нь холболтыг шифрлэж, өөр компьютер энэ сервер мэт дүр эсгэхээс хамгаална.
          </p>
        </div>
      )}
      {backup && (
        <>
          <h2>Backup</h2>
          {!status ? (
            <p>
              Backup хараахан хийгдээгүй. WorkTrack асаалттай үед өдөрт нэг удаа автоматаар хийнэ.
            </p>
          ) : (
            <p>
              Сүүлийн амжилттай backup: <strong>{when(status.last_success_at)}</strong>
              {status.last_copy_at && <> · Хоёр дахь хуулбар: {when(status.last_copy_at)}</>}
            </p>
          )}
          {status?.error && <p role="alert">Сүүлийн оролдлого амжилтгүй: {status.error}</p>}
          {backup.copy_dir_source === 'environment' ? (
            <p>
              Хоёр дахь хуулбар: <code>{backup.copy_dir}</code> (серверийн BACKUP_COPY_DIR
              тохиргоогоор).
            </p>
          ) : (
            <form className="task-form" onSubmit={save}>
              <fieldset disabled={saving || !user.is_admin}>
                <label>
                  Хоёр дахь хуулбарын хавтас (серверийн компьютер дээр)
                  <input
                    value={folder ?? backup.copy_dir}
                    maxLength={500}
                    placeholder="D:\WorkTrack-backup эсвэл /Volumes/USB/WorkTrack"
                    onChange={(e) => setFolder(e.target.value)}
                  />
                </label>
                <p className="muted">
                  Сервер эвдэрвэл backup хамт алга болохгүйн тулд USB диск, сүлжээний хавтас эсвэл
                  Google Drive / OneDrive-ийн синк хийдэг хавтсыг сонгоно. Сүүлийн 30 хуулбар
                  хадгалагдана. Хоосон бол хоёр дахь хуулбар хийхгүй.
                </p>
                {feedback && <p role={feedback.ok ? 'status' : 'alert'}>{feedback.text}</p>}
                <button type="submit">Хавтас хадгалах</button>
              </fieldset>
            </form>
          )}
          {!backup.copy_dir && (
            <p role="status" className="work-reminder">
              Одоогоор backup зөвхөн серверийн компьютер дээр байна. Хоёр дахь хавтас тохируулахыг
              зөвлөж байна.
            </p>
          )}
        </>
      )}
    </section>
  );
}

const WEEKDAY_NAMES = ['Даваа', 'Мягмар', 'Лхагва', 'Пүрэв', 'Баасан', 'Бямба', 'Ням'];

export function MonitoringSettings({ user }) {
  const [value, setValue] = useState(null),
    [form, setForm] = useState(null);
  const [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(true);
  const controller = useRef(null);
  async function fetchSettings(signal) {
    try {
      const settings = await api('/api/monitoring-settings/', { signal });
      if (!signal.aborted) {
        setValue(settings);
        setForm({ ...settings, productive_apps: settings.productive_apps.join('\n') });
      }
    } catch (failure) {
      if (!signal.aborted && failure.name !== 'AbortError') setError(failure.message);
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }
  async function load() {
    controller.current?.abort();
    controller.current = new AbortController();
    setBusy(true);
    setError('');
    setMessage('');
    await fetchSettings(controller.current.signal);
  }
  useEffect(() => {
    const next = new AbortController();
    controller.current = next;
    Promise.resolve().then(() => fetchSettings(next.signal));
    return () => next.abort();
  }, [user.id]);
  async function save(event) {
    event.preventDefault();
    if (busy || !value) return;
    setBusy(true);
    setError('');
    setMessage('');
    const signal = controller.current.signal;
    const payload = {
      expected_version: value.version,
      productive_apps: form.productive_apps
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
      camera_threshold: Number(form.camera_threshold),
      presence_log_max_bytes: Number(form.presence_log_max_bytes),
      presence_log_backups: Number(form.presence_log_backups),
      presence_log_retention_days: Number(form.presence_log_retention_days),
      activity_retention_days: Number(form.activity_retention_days),
      automatic_retention: form.automatic_retention,
      client_version: form.client_version.trim(),
      client_download_url: form.client_download_url.trim(),
      work_days: form.work_days || [0, 1, 2, 3, 4],
      work_start: (form.work_start || '09:00').slice(0, 5),
      work_end: (form.work_end || '18:00').slice(0, 5),
    };
    try {
      const result = await api('/api/monitoring-settings/', {
        method: 'PATCH',
        body: JSON.stringify(payload),
        signal,
      });
      if (!signal.aborted) {
        setValue(result);
        setMessage(
          'Хадгаллаа. Төхөөрөмжүүд дараагийн холболтоор шинэ тохиргоог авна (ердийн үед 30 секунд орчим).',
        );
      }
    } catch (failure) {
      if (!signal.aborted && failure.name !== 'AbortError') setError(failure.message);
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }
  const update = (name, next) => setForm((previous) => ({ ...previous, [name]: next }));
  return (
    <section className="task-section">
      <h1>Бүртгэлийн тохиргоо</h1>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <button type="button" disabled={busy} onClick={load}>
        Дахин унших
      </button>
      {form && (
        <form className="task-form" onSubmit={save}>
          <fieldset disabled={busy || !user.is_admin}>
            <label>
              Ажилд тооцох аппууд (мөр бүрд нэг)
              <textarea
                rows={6}
                value={form.productive_apps}
                onChange={(e) => update('productive_apps', e.target.value)}
              />
            </label>
            <label>
              Камерын итгэлцлийн босго
              <input
                required
                type="number"
                min="0.05"
                max="1"
                step="0.01"
                value={form.camera_threshold}
                onChange={(e) => update('camera_threshold', e.target.value)}
              />
            </label>
            <label>
              Камерын түр файлын дээд хэмжээ (байт)
              <input
                required
                type="number"
                min="256"
                max="104857600"
                value={form.presence_log_max_bytes}
                onChange={(e) => update('presence_log_max_bytes', e.target.value)}
              />
            </label>
            <label>
              Камерын түр файлын хуулбарын тоо
              <input
                required
                type="number"
                min="0"
                max="20"
                value={form.presence_log_backups}
                onChange={(e) => update('presence_log_backups', e.target.value)}
              />
            </label>
            <label>
              Камерын түр файлыг компьютер дээр хадгалах хоног
              <input
                required
                type="number"
                min="1"
                max="365"
                value={form.presence_log_retention_days}
                onChange={(e) => update('presence_log_retention_days', e.target.value)}
              />
            </label>
            <label>
              Програмын бүртгэлийг серверт хадгалах хоног
              <input
                required
                type="number"
                min="1"
                max="3650"
                value={form.activity_retention_days}
                onChange={(e) => update('activity_retention_days', e.target.value)}
              />
            </label>
            <label className="toggle-field">
              <input
                type="checkbox"
                checked={form.automatic_retention}
                onChange={(e) => update('automatic_retention', e.target.checked)}
              />
              Backup амжилттай болсны дараа хугацаа хэтэрсэн бүртгэлийг автоматаар цэвэрлэх
            </label>
            <p>
              Автомат цэвэрлэгээ эхэндээ унтраалттай. Хэрэглэгч, даалгавар, зөвшөөрөл, оноог
              устгахгүй.
            </p>
            <h2>Ажлын хуваарь</h2>
            <p>
              Сануулга зөвхөн энэ хуваарьт гарна; онооны «ажлын програмын хувь» (W) энэ цагаас
              тооцогдоно; хуваарийн гаднах цагийг (жишээ нь оюутны хичээл) тайланд тусад нь
              харуулна.
            </p>
            <fieldset className="work-days">
              <legend>Ажлын өдрүүд</legend>
              {WEEKDAY_NAMES.map((name, day) => (
                <label className="toggle-field" key={name}>
                  <input
                    type="checkbox"
                    checked={(form.work_days || []).includes(day)}
                    onChange={(e) =>
                      update(
                        'work_days',
                        e.target.checked
                          ? [...(form.work_days || []), day].sort()
                          : (form.work_days || []).filter((value) => value !== day),
                      )
                    }
                  />
                  {name}
                </label>
              ))}
            </fieldset>
            <div className="work-hours">
              <label>
                Эхлэх цаг
                <input
                  type="time"
                  required
                  value={(form.work_start || '').slice(0, 5)}
                  onChange={(e) => update('work_start', e.target.value)}
                />
              </label>
              <label>
                Дуусах цаг
                <input
                  type="time"
                  required
                  value={(form.work_end || '').slice(0, 5)}
                  onChange={(e) => update('work_end', e.target.value)}
                />
              </label>
            </div>
            <h2>Ажилтны аппын шинэ хувилбар</h2>
            <p>
              Шинэ хувилбар гаргасан бол энд бичнэ. Хуучин хувилбартай компьютерууд мэдэгдэл авч,
              татах холбоосыг харна. Компьютер бүрийн хувилбарыг «Төхөөрөмжийн төлөв»-өөс харна.
            </p>
            <label>
              Хувилбар (жишээ нь 1.1.0)
              <input
                inputMode="decimal"
                pattern="\d{1,4}(\.\d{1,4}){0,3}"
                maxLength={20}
                value={form.client_version}
                onChange={(e) => update('client_version', e.target.value)}
              />
            </label>
            <label>
              Татах холбоос
              <input
                type="url"
                maxLength={500}
                placeholder="https://github.com/…/releases/latest"
                required={Boolean(form.client_version.trim())}
                value={form.client_download_url}
                onChange={(e) => update('client_download_url', e.target.value)}
              />
            </label>
            <button type="submit">Тохиргоо хадгалах</button>
          </fieldset>
        </form>
      )}
    </section>
  );
}

export function ReportExport({ user, members, date }) {
  const [first, setFirst] = useState(date),
    [last, setLast] = useState(date),
    [employee, setEmployee] = useState(String(user.id));
  const [kind, setKind] = useState('csv'),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const controller = useRef(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function download(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    controller.current = new AbortController();
    const signal = controller.current.signal;
    try {
      const query = new URLSearchParams({
        start: first,
        end: last,
        employee_id: employee,
        file_type: kind,
      });
      const blob = await downloadReport('/api/reports/export/?' + query, { signal });
      if (signal.aborted) return;
      const url = URL.createObjectURL(blob),
        link = document.createElement('a');
      link.href = url;
      link.download = `worktrack-${first}-${last}.${kind}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      if (!signal.aborted && failure.name !== 'AbortError') setError(failure.message);
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }
  return (
    <form className="task-form" onSubmit={download}>
      <h2>Тайлан татах</h2>
      <fieldset disabled={busy}>
        <label>
          Эхлэх өдөр
          <input required type="date" value={first} onChange={(e) => setFirst(e.target.value)} />
        </label>
        <label>
          Дуусах өдөр
          <input
            required
            type="date"
            min={first}
            value={last}
            onChange={(e) => setLast(e.target.value)}
          />
        </label>
        <label>
          Экспортлох ажилтан
          <select value={employee} onChange={(e) => setEmployee(e.target.value)}>
            {(user.is_admin || user.role === 'MANAGER') && (
              <option value="all">Эрхийн хүрээний бүх ажилтан</option>
            )}
            {members.map((member) => (
              <option key={member.id} value={member.id}>
                {member.name || member.username}
              </option>
            ))}
          </select>
        </label>
        <label>
          Файлын төрөл
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="csv">CSV</option>
            <option value="xlsx">Excel (.xlsx)</option>
          </select>
        </label>
        <button type="submit">{busy ? 'Бэлтгэж байна…' : 'Тайлан татах'}</button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
