import { useEffect, useState } from 'react';
import MonthCharts from './MonthCharts';
import { api } from './api';
import { clockTime } from './taskTime';
import { usePolling } from './usePolling';

function currentMonth() {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: 'Asia/Ulaanbaatar',
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(new Date());
  return `${parts.find((part) => part.type === 'year').value}-${parts.find((part) => part.type === 'month').value}`;
}

export default function MonthlyReport({ user }) {
  const [selected, setSelected] = useState('');
  const [current, setCurrent] = useState(currentMonth);
  const [sample, setSample] = useState(null);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const month = selected || current;
  const key = `${user.id}:${user.role}:${user.department}:${month}`;
  const report = sample?.key === key ? sample.data : null;
  useEffect(() => {
    const timer = setInterval(() => setCurrent(currentMonth()), 30000);
    return () => clearInterval(timer);
  }, []);
  usePolling(
    async (signal) => {
      try {
        const data = await api('/api/reports/monthly/?' + new URLSearchParams({ month }), {
          signal,
        });
        if (!signal.aborted) {
          setSample({ key, data });
          setError('');
        }
      } catch (failure) {
        if (!signal.aborted) {
          setSample(null);
          setError(failure.message);
        }
      }
    },
    30000,
    `${key}:${revision}`,
  );
  return (
    <section className="monthly-report" aria-label="Сарын ажилтны тайлан">
      <div className="monthly-report-heading">
        <div>
          <h2>
            {user.is_admin || user.role === 'MANAGER'
              ? 'Ажилтнуудын сарын тайлан'
              : 'Миний сарын тайлан'}
          </h2>
          <p>30 секунд тутам автоматаар шинэчлэгдэнэ · Улаанбаатарын цагаар</p>
        </div>
        <label>
          Тайлангийн сар
          <input
            type="month"
            min="2000-01"
            max="2100-12"
            value={month}
            onChange={(event) => setSelected(event.target.value)}
          />
        </label>
        <button
          type="button"
          onClick={() => {
            setSelected('');
            setRevision((value) => value + 1);
          }}
        >
          Энэ сар
        </button>
        <button type="button" onClick={() => setRevision((value) => value + 1)}>
          Сарын тайлан шинэчлэх
        </button>
      </div>
      <p className="muted">
        Програм асаалттай цаг, аппын болон идэвхгүй хугацаа, даалгаврын цаг нь тусдаа хэмжилт тул
        хооронд нь нэмэхгүй. Аппын цаг нь ажил гүйцэтгэсэн эсвэл бүтээмжтэй байсны баталгаа биш.
      </p>
      {(user.is_admin || user.role === 'MANAGER') && (
        <MonthCharts key={key} month={month} revision={revision} />
      )}
      {error && <p role="alert">Сарын тайлан: {error}</p>}
      {!report && !error && <p role="status">Сарын тайлан уншиж байна…</p>}
      {report && (
        <>
          <p className="muted">
            Шинэчилсэн:{' '}
            {new Date(report.generated_at).toLocaleString('mn-MN', {
              timeZone: 'Asia/Ulaanbaatar',
            })}
          </p>
          {!report.employees.length && <p>Харах боломжтой ажилтан алга.</p>}
          <div className="monthly-employees">
            {report.employees.map((row) => (
              <article className="monthly-employee" key={row.employee}>
                <h3>
                  {row.name}{' '}
                  <small>
                    @{row.username}
                    {!row.is_active && ' · идэвхгүй'}
                  </small>
                </h3>
                {row.department && <p>{row.department}</p>}
                <dl className="monthly-metrics">
                  <div>
                    <dt>WorkTrack асаалттай</dt>
                    <dd>{row.launcher_recorded_since ? clockTime(row.launcher_seconds) : '—'}</dd>
                  </div>
                  <div>
                    <dt>Апп ашигласан (идэвхгүйг хассан)</dt>
                    <dd>{clockTime(row.application_seconds)}</dd>
                  </div>
                  <div>
                    <dt>Үүнээс ажлын хуваарийн гадна</dt>
                    <dd>{clockTime(row.outside_schedule_seconds || 0)}</dd>
                  </div>
                  <div>
                    <dt>Идэвхгүй</dt>
                    <dd>{clockTime(row.idle_seconds)}</dd>
                  </div>
                  <div>
                    <dt>Даалгаварт бүртгэсэн</dt>
                    <dd>{clockTime(row.task_seconds)}</dd>
                  </div>
                  <div>
                    <dt>Энэ сард дуусгасан</dt>
                    <dd>{row.completed_tasks.length}</dd>
                  </div>
                  <div>
                    <dt>Шилжүүлсэн / хүлээн авсан</dt>
                    <dd>
                      {row.transfers_sent} / {row.transfers_received}
                    </dd>
                  </div>
                </dl>
                <p className="muted">
                  {row.launcher_last_upload
                    ? `Програмын цаг илгээсэн: ${new Date(row.launcher_last_upload).toLocaleString('mn-MN', { timeZone: 'Asia/Ulaanbaatar' })}`
                    : 'Програмын цаг хараахан ирээгүй. Ажилтан WorkTrack-аа дахин асааж төхөөрөмжөө холбоно.'}
                </p>
                <details>
                  <summary>{row.name} — ажлын дэлгэрэнгүй</summary>
                  <h4>Энэ сард цаг бүртгэсэн даалгавар</h4>
                  {row.tasks.length ? (
                    <ul>
                      {row.tasks.map((task) => (
                        <li key={task.id}>
                          {task.title} — {clockTime(task.seconds)}; нийт даалгаварт оруулсан
                          одоогийн хувь: {task.contribution_percent}%
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>Даалгаврын цаг бүртгээгүй.</p>
                  )}
                  <h4>Энэ сард дуусгасан даалгавар</h4>
                  {row.completed_tasks.length ? (
                    <ul>
                      {row.completed_tasks.map((task) => (
                        <li key={task.id}>{task.title}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>Дуусгасан даалгавар алга.</p>
                  )}
                  <h4>Аппын бүртгэл</h4>
                  {row.applications.length ? (
                    <ul>
                      {row.applications.map((app) => (
                        <li key={app.application}>
                          {app.application} — {clockTime(app.seconds)}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>Аппын бүртгэл ирээгүй.</p>
                  )}
                </details>
              </article>
            ))}
          </div>
          <p className="muted">
            Хадгалагдсан бүртгэлд тулгуурлана. Өмнө нь хэмжээгүй эсвэл устсан мэдээллийг нөхөж
            тооцохгүй. WorkTrack-ийн давхардсан төхөөрөмжийн хугацааг нэг удаа тоолно; аппын цаг нь
            илгээсэн бүртгэлүүдийн нийлбэр.
          </p>
        </>
      )}
    </section>
  );
}
