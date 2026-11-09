import { SegmentedBar } from './Charts';
import { useEffect, useState } from 'react';
import { api } from './api';
import { clockTime } from './taskTime';

const transferLabels = {
  PENDING: 'Хүлээгдэж байна',
  ACCEPTED: 'Зөвшөөрсөн',
  DECLINED: 'Татгалзсан',
  CANCELLED: 'Цуцалсан',
};

export default function TaskCollaboration({
  task,
  user,
  busy,
  onAction,
  onStart,
  onTaskOnlyStart,
  work,
}) {
  const data = task.collaboration || {
    contributions: [],
    progress_percent: 0,
    total_seconds: 0,
    transfers: [],
  };
  const mine = data.contributions.find((row) => row.employee === user.id);
  const owner = task.employee === user.id;
  const canManage = task.can_manage ?? user.is_admin;
  const pending = data.pending_transfer;
  const count = task.transfer_count || 0;
  const active = work.sample?.data.session;
  const running = active?.running && active.task_id === task.id;
  const [requestOpen, setRequestOpen] = useState(false);
  const [message, setMessage] = useState('');
  async function decide(decision) {
    if (await onAction(task.id, 'transfer-respond', { request_id: pending.id, decision }))
      setMessage(decision === 'accept' ? 'Даалгаврыг хүлээн авлаа.' : 'Хүсэлтийг шийдвэрлэлээ.');
  }
  return (
    <section className="task-collaboration" aria-label={`${task.title} — оролцоо`}>
      <h4>Оролцоо · нийт {Number(data.progress_percent)}%</h4>
      <SegmentedBar
        thin
        table={false}
        format={(value) => `${value}%`}
        parts={[
          // Three people by name; anyone after them folds into one part so colours stay distinct.
          ...data.contributions.slice(0, 3).map((row, index) => ({
            label: row.username,
            value: Number(row.percent),
            color: ['--viz-1', '--viz-2', '--viz-3'][index],
          })),
          ...(data.contributions.length > 3
            ? [
                {
                  label: 'Бусад гишүүд',
                  value: data.contributions
                    .slice(3)
                    .reduce((sum, row) => sum + Number(row.percent), 0),
                  color: '--viz-4',
                },
              ]
            : []),
          {
            label: 'Үлдсэн',
            value: Math.max(0, 100 - Number(data.progress_percent)),
            color: '--viz-idle',
          },
        ]}
      />
      <p>
        Даалгаварт бүртгэсэн нийт цаг: <strong>{clockTime(data.total_seconds)}</strong>
      </p>
      <p className="muted">
        Хийсэн хувь нь гишүүний өөрийн оруулсан үнэлгээ. Цагийн эзлэх хувь нь бүртгэсэн хугацаанаас
        тооцогдоно.
      </p>
      {!data.contributions.length && <p>Одоогоор оролцоо бүртгээгүй.</p>}
      <ul className="task-contributions">
        {data.contributions.map((row, index) => (
          <li key={row.employee ?? `former-${index}`}>
            <strong>{row.username}</strong>
            <span>
              {clockTime(row.seconds)} · цагийн {row.time_share_percent}%
            </span>
            <span>
              Хийсэн хувь: {Number(row.percent)}%{row.running ? ' · Цаг ажиллаж байна' : ''}
            </span>
          </li>
        ))}
      </ul>
      {owner && task.status !== 'Дууссан' && (
        <>
          <button type="button" disabled={busy || running} onClick={() => onStart(task.id)}>
            {running ? 'Энэ даалгаврын цаг ажиллаж байна' : 'Энэ ажлыг сонгох'}
          </button>
          {!running && (
            <details>
              <summary>Аппын бүртгэлгүй ажиллах</summary>
              <p>Өөр төхөөрөмжөөс зөвхөн энэ даалгаврын цагаа бүртгэх бол:</p>
              <button type="button" disabled={busy} onClick={() => onTaskOnlyStart(task.id)}>
                Зөвхөн даалгаврын цаг эхлүүлэх
              </button>
            </details>
          )}
        </>
      )}
      {owner && (
        <ProgressEditor
          key={`${task.id}:${mine?.percent ?? 0}`}
          task={task}
          current={mine?.percent ?? 0}
          total={data.progress_percent}
          busy={busy}
          onAction={onAction}
        />
      )}
      <p>Шилжүүлсэн: {count} / 2</p>
      {pending ? (
        <div className="task-transfer-pending">
          <p>
            <strong>
              {pending.from_name} → {pending.to_name}
            </strong>{' '}
            · Хариу хүлээж байна
          </p>
          {pending.note && <p>{pending.note}</p>}
          <div className="desktop-actions">
            {pending.to_employee === user.id && (
              <>
                <button type="button" disabled={busy} onClick={() => decide('accept')}>
                  Хүлээн авах
                </button>
                <button type="button" disabled={busy} onClick={() => decide('decline')}>
                  Татгалзах
                </button>
              </>
            )}
            {(owner || canManage || pending.requested_by === user.id) && (
              <button type="button" disabled={busy} onClick={() => decide('cancel')}>
                Хүсэлт цуцлах
              </button>
            )}
          </div>
        </div>
      ) : count < 2 && task.status !== 'Дууссан' && (owner || canManage) ? (
        <>
          <button
            type="button"
            disabled={busy}
            aria-expanded={requestOpen}
            onClick={() => {
              setMessage('');
              setRequestOpen(!requestOpen);
            }}
          >
            Шилжүүлэх хүсэлт
          </button>
          {requestOpen && (
            <TransferForm
              task={task}
              busy={busy}
              onAction={onAction}
              onClose={() => setRequestOpen(false)}
              onSaved={() => {
                setRequestOpen(false);
                setMessage('Хүсэлт илгээгдлээ. Хүлээн авагч зөвшөөртөл хариуцагч солигдохгүй.');
              }}
            />
          )}
        </>
      ) : (
        count >= 2 && <p>Хоёр удаагийн шилжүүлгийн хязгаарт хүрсэн.</p>
      )}
      {message && <p role="status">{message}</p>}
      {!!data.transfers.length && (
        <details>
          <summary>Шилжүүлгийн түүх</summary>
          <ul>
            {data.transfers.map((row) => (
              <li key={row.id}>
                {row.from_name} → {row.to_name} · {transferLabels[row.status]}
                {' · '}
                {new Date(row.created_at).toLocaleString('mn-MN', { timeZone: 'Asia/Ulaanbaatar' })}
                {row.note && <p>{row.note}</p>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function ProgressEditor({ task, current, total, busy, onAction }) {
  const [value, setValue] = useState(String(current));
  const [saved, setSaved] = useState(false);
  const max = Math.round((100 - Number(total) + Number(current)) * 100) / 100;
  return (
    <form
      className="quality-form"
      onSubmit={async (event) => {
        event.preventDefault();
        if (await onAction(task.id, 'progress', { percent: value, expected_percent: current }))
          setSaved(true);
      }}
    >
      <label htmlFor={`progress-${task.id}`}>Миний хийсэн хувь (нийт ажлын, 0–{max}%)</label>
      <input
        id={`progress-${task.id}`}
        type="number"
        min="0"
        max={max}
        step="0.01"
        required
        value={value}
        disabled={busy}
        onChange={(event) => {
          setValue(event.target.value);
          setSaved(false);
        }}
      />
      <button disabled={busy || Number(value) === Number(current)} type="submit">
        Хувь хадгалах
      </button>
      {saved && <p role="status">Хувь хадгаллаа.</p>}
    </form>
  );
}

function TransferForm({ task, busy, onAction, onSaved, onClose }) {
  const [recipients, setRecipients] = useState(null),
    [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api(`/api/tasks/${task.id}/transfer-recipients/`, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setRecipients(data);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(failure.message);
      });
    return () => controller.abort();
  }, [task.id, reload]);
  return (
    <form
      className="task-form"
      onSubmit={async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.currentTarget));
        if (
          await onAction(task.id, 'transfer-request', {
            ...data,
            recipient: Number(data.recipient),
          })
        )
          onSaved();
      }}
    >
      <p>
        Хүлээн авагч зөвшөөрсний дараа хариуцагч солигдоно. Өөрийн хийсэн хувийг эхлээд хадгална уу.
      </p>
      {error && (
        <>
          <p role="alert">{error}</p>
          <button
            type="button"
            onClick={() => {
              setError('');
              setReload((value) => value + 1);
            }}
          >
            Дахин ачаалах
          </button>
        </>
      )}
      {!recipients && !error && <p>Гишүүдийг уншиж байна…</p>}
      {recipients?.length === 0 && (
        <p>Шилжүүлэх идэвхтэй гишүүн алга. Хэлтсийн тохиргоог админаар шалгуулна уу.</p>
      )}
      <fieldset disabled={busy || !recipients?.length || Boolean(error)}>
        <label htmlFor={`recipient-${task.id}`}>Хүлээн авах гишүүн</label>
        <select id={`recipient-${task.id}`} name="recipient" required defaultValue="">
          <option value="">Гишүүн сонгох</option>
          {recipients?.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name} ({row.username})
            </option>
          ))}
        </select>
        <label htmlFor={`handoff-note-${task.id}`}>Шилжүүлэх тайлбар</label>
        <textarea id={`handoff-note-${task.id}`} name="note" maxLength={1000} />
        <button type="submit">Хүсэлт илгээх</button>
      </fieldset>
      <button type="button" disabled={busy} onClick={onClose}>
        Болих
      </button>
    </form>
  );
}
