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
    queue_pending: 'Илгээх бүртгэл хүлээгдэж байна',
  };
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
          <button
            type="button"
            onClick={() => navigate(item.kind.startsWith('task_') ? 'tasks' : 'agents')}
          >
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

export function AgentStatus({ user }) {
  const [page, setPage] = useState(1);
  const { data, error, refresh } = usePolling(`/api/agent-status/?page=${page}`, user);
  return (
    <section className="task-section">
      <h1>Төхөөрөмжийн төлөв</h1>
      <p>
        30 секунд тутам шинэчлэгдэнэ. Сүүлийн heartbeat 90 секундээс хуучирвал холболтгүй гэж
        харуулна.
      </p>
      <button type="button" onClick={refresh}>
        Төлөв шинэчлэх
      </button>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p>Уншиж байна…</p>}
      {data?.results?.length === 0 && <p>Бүртгэлтэй төхөөрөмж алга.</p>}
      {data?.results?.map((device) => (
        <article className="activity-detail-card" key={device.id}>
          <h2>{device.name}</h2>
          <p>
            {device.employee_name} · {device.platform}
            {!device.enabled ? ' · Идэвхгүй' : ''}
          </p>
          {!device.agents.length && (
            <p>
              Төхөөрөмж төлөвөө илгээгээгүй.{' '}
              {device.platform === 'Windows' ? 'Start WorkTrack.bat' : 'Start WorkTrack.command'}
              -аар асаана уу.
            </p>
          )}
          {device.agents.map((agent) => (
            <div key={agent.kind} aria-label={`${device.name} ${agent.kind}`}>
              <h3>
                {agent.kind === 'camera' ? 'Camera' : 'Computer agent'} — {stateLabels[agent.state]}
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
                <span>Queue-д хүлээгдэж буй</span>
                <strong>{agent.queue_count}</strong>
              </div>
              {agent.error_code && (
                <p role="status">{errorLabels[agent.error_code] || 'Алдаа гарсан'}</p>
              )}
              <p>
                Програм {agent.agent_version || '—'} · Тохиргоо v{agent.settings_version}
              </p>
            </div>
          ))}
        </article>
      ))}
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
    admin_change: 'Admin-аар зассан',
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
    presence_log_retention_days: 'CSV хадгалах хоног',
    activity_retention_days: 'Өгөгдлийн санд хадгалах хоног',
    automatic_retention: 'Автомат цэвэрлэгээ',
    client_version: 'Ажилтны аппын хувилбар',
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
      <h1>Monitoring тохиргоо</h1>
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
              CSV файлын дээд хэмжээ (byte)
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
              CSV backup тоо
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
              Local CSV хадгалах хоног
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
              Database activity хадгалах хоног
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
              Backup амжилттай болсны дараа хугацаа хэтэрсэн activity-г автоматаар цэвэрлэх
            </label>
            <p>
              Автомат цэвэрлэгээ эхэндээ унтраалттай. Хэрэглэгч, даалгавар, зөвшөөрөл, оноог
              устгахгүй.
            </p>
            <h2>Ажилтны аппын шинэ хувилбар</h2>
            <p>
              Шинэ хувилбар гаргасан бол энд бичнэ. Хуучин хувилбартай компьютерууд мэдэгдэл авч,
              татах холбоосыг харна. Компьютер бүрийн хувилбарыг «Agent төлөв»-өөс харна.
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
