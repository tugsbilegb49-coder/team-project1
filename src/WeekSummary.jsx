import { useState } from 'react';
import { api } from './api';
import { durationText } from './taskTime';
import { usePolling } from './usePolling';

const WEEKDAYS = ['Даваа', 'Мягмар', 'Лхагва', 'Пүрэв', 'Баасан', 'Бямба', 'Ням'];
const SERIES = [
  { field: 'task_seconds', label: 'Даалгаварт', className: 'week-bar-task' },
  { field: 'application_seconds', label: 'Компьютер дээр', className: 'week-bar-computer' },
];

/** YYYY-MM-DD-ийг өдрөөр шилжүүлнэ (цагийн бүсээс хамаарахгүй). */
function shiftDate(value, days) {
  return new Date(Date.parse(`${value}T00:00:00Z`) + days * 86400000).toISOString().slice(0, 10);
}

function shortDate(value) {
  return `${value.slice(5, 7)}/${value.slice(8, 10)}`;
}

/** Ажилтны өөрийн 7 хоног: өдөр бүрийн даалгаврын болон компьютерийн цаг, гол даалгаврууд. */
export default function WeekSummary({ user }) {
  const [start, setStart] = useState(''); // '' = энэ 7 хоног
  const [current, setCurrent] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  usePolling(
    async (signal) => {
      try {
        const query = start ? `?start=${start}` : '';
        const data = await api(`/api/me/week/${query}`, { signal });
        if (signal.aborted) return;
        setResult({ start, data });
        setError('');
        if (!start) setCurrent(data.start);
      } catch (failure) {
        if (!signal.aborted && failure.name !== 'AbortError') setError(failure.message);
      }
    },
    60000,
    `${user.id}:${start}`,
  );
  const data = result?.start === start ? result.data : null;
  const longest = Math.max(
    1,
    ...(data?.days || []).flatMap((day) => SERIES.map(({ field }) => day[field])),
  );
  function goTo(next) {
    setStart(current && next >= current ? '' : next);
  }
  return (
    <section className="activity-detail-card week-summary" aria-label="Миний 7 хоног">
      <div className="week-heading">
        <div>
          <h2>Миний 7 хоног</h2>
          <p className="muted">
            {data ? `${shortDate(data.start)} – ${shortDate(data.end)}` : 'Уншиж байна…'}
          </p>
        </div>
        <div className="week-nav">
          <button type="button" disabled={!data} onClick={() => goTo(shiftDate(data.start, -7))}>
            ‹ Өмнөх
          </button>
          <button
            type="button"
            disabled={!data || !start}
            onClick={() => goTo(shiftDate(data.start, 7))}
          >
            Дараах ›
          </button>
        </div>
      </div>
      {error && <p role="status">7 хоногийн мэдээлэл уншиж чадсангүй: {error}</p>}
      {data && (
        <>
          <p>
            Даалгаварт <strong>{durationText(data.totals.task_seconds)}</strong> · Компьютер дээр{' '}
            <strong>{durationText(data.totals.application_seconds)}</strong> · Дууссан даалгавар{' '}
            <strong>{data.completed_tasks}</strong>
          </p>
          <ul className="week-legend" aria-hidden="true">
            {SERIES.map(({ label, className }) => (
              <li key={className}>
                <span className={`week-swatch ${className}`} />
                {label}
              </li>
            ))}
          </ul>
          <ol className="week-chart">
            {data.days.map((day, index) => {
              const name = `${WEEKDAYS[index]} ${shortDate(day.date)}`;
              return (
                <li
                  key={day.date}
                  aria-label={`${name}: даалгаварт ${durationText(day.task_seconds)}, компьютер дээр ${durationText(day.application_seconds)}`}
                >
                  <span className="week-day">{name}</span>
                  {day.task_seconds || day.application_seconds ? (
                    <span className="week-bars" aria-hidden="true">
                      {SERIES.map(({ field, label, className }) => (
                        <span
                          className="week-bar-row"
                          key={field}
                          title={`${label}: ${durationText(day[field])}`}
                        >
                          {/* Leave room for the value label at the bar's tip. */}
                          <span
                            className={`week-bar ${className}`}
                            style={{ width: `calc((100% - 90px) * ${day[field] / longest})` }}
                          />
                          <span className="week-value">
                            {day[field] ? durationText(day[field]) : '—'}
                          </span>
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className="week-empty">Бүртгэлгүй</span>
                  )}
                </li>
              );
            })}
          </ol>
          {data.tasks.length > 0 && (
            <>
              <h3>Хамгийн их цаг зарцуулсан даалгавар</h3>
              {data.tasks.map((task) => (
                <div className="activity-row" key={task.id}>
                  <span>{task.title}</span>
                  <strong>{durationText(task.seconds)}</strong>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </section>
  );
}
