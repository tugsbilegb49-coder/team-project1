import { useState } from 'react';
import { clockTime, sessionTiming, useTick } from './taskTime';
import { api } from './api';
import { usePolling } from './usePolling';

export function LauncherClock({ user, card = false }) {
  const [sample, setSample] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [error, setError] = useState('');
  const now = useTick();
  const connected = sample && now - sample.at < 45000;
  usePolling(
    async (signal) => {
      try {
        const value = await api('/desktop/status/', {
          signal,
          headers: { 'X-WorkTrack-Desktop': '1' },
        });
        if (signal.aborted) return;
        const usage = value.launcher_usage;
        if (usage?.available && Array.isArray(usage.months)) {
          setSample({ usage, at: Date.now() });
          setError('');
        } else {
          setSample(null);
          setError(usage?.error || 'Сарын тооцоог эхлүүлэхийн тулд WorkTrack-аа дахин асаана уу.');
        }
      } catch {
        if (!signal.aborted) {
          setSample(null);
          setError(
            'Энэ компьютер дээрх WorkTrack програмтай холбогдсонгүй. WorkTrack-аа асаана уу.',
          );
        }
      }
    },
    15000,
    user.id,
  );
  const Container = card ? 'article' : 'div';
  const Value = card ? 'h2' : 'strong';
  const usage = sample?.usage;
  const month =
    usage?.months.find((row) => row.month === selectedMonth) ||
    usage?.months.find((row) => row.month === usage.current_month);
  const liveSeconds =
    usage?.running && month?.month === usage.current_month && connected
      ? Math.min(
          Math.max(0, now - sample.at) / 1000,
          Math.max(0, usage.month_ends_at - usage.as_of),
        )
      : 0;
  return (
    <Container
      className={card ? 'stat-card launcher-time-card' : 'work-clock'}
      aria-label="WorkTrack сарын хугацаа"
    >
      {card && (
        <p className="eyebrow">
          {month?.month === usage?.current_month ? 'Энэ сар' : month?.month || 'Сарын нийлбэр'}
        </p>
      )}
      <p>WorkTrack нээлттэй байсан</p>
      <Value>{month ? clockTime(month.seconds + liveSeconds) : '—'}</Value>
      {usage && (
        <label className="usage-month">
          Сар сонгох
          <select
            value={month?.month === usage.current_month ? '' : month?.month || ''}
            onChange={(event) => setSelectedMonth(event.target.value)}
          >
            <option value="">Энэ сар ({usage.current_month})</option>
            {usage.months
              .filter((row) => row.month !== usage.current_month)
              .map((row) => (
                <option key={row.month} value={row.month}>
                  {row.month}
                </option>
              ))}
          </select>
        </label>
      )}
      {card && <small>Компьютер унтсан болон WorkTrack хаалттай байсан хугацааг тооцохгүй.</small>}
      {usage && !usage.running && (
        <small>Төхөөрөмжөө холбоно уу. Өмнөх хадгалсан хугацаа хэвээр үлдэнэ.</small>
      )}
      {usage?.sync_error && usage.sync_error !== 'unlinked' && (
        <small role="status">
          Серверт цаг илгээх холболт/зөвшөөрлөө шалгана уу. Хадгалсан хугацаа төхөөрөмж дээр үлдэнэ.
        </small>
      )}
      {card && usage?.recorded_since && (
        <small>
          Бүртгэж эхэлсэн:{' '}
          {new Date(usage.recorded_since).toLocaleDateString('mn-MN', {
            timeZone: 'Asia/Ulaanbaatar',
          })}
        </small>
      )}
      {(!connected || error) && (
        <small role="status">{error || 'Сарын хугацааны холболтыг шалгаж байна…'}</small>
      )}
    </Container>
  );
}

export function TaskWorkClock({ work, busy, onStop, navigate, card = false }) {
  const { session, running, seconds } = sessionTiming(work.sample, useTick());
  if (card)
    return (
      <article className="stat-card" aria-label="Одоогийн даалгаврын цаг">
        <p className="eyebrow">Одоогийн даалгавар</p>
        <p>Даалгаврын цаг</p>
        <h2>{clockTime(seconds)}</h2>
        <small>
          {session
            ? `${session.title} · ${running ? 'Бүртгэж байна' : 'Зогссон'}`
            : 'Даалгавар сонгоод «Ажил эхлүүлэх» дарахад тоолж эхэлнэ.'}
        </small>
        <small>Өмнөх цагууд даалгавар болон сарын тайланд хадгалагдана.</small>
        {work.error && <small role="alert">Цагийн холболт: {work.error}</small>}
      </article>
    );
  return (
    <div className="task-work-clock">
      {session ? (
        <>
          <span>
            {session.title} · {running ? 'Цаг бүртгэж байна' : 'Цаг зогссон'}
          </span>
          <strong aria-label="Даалгаврын цаг">{clockTime(seconds)}</strong>
          {running && (
            <button type="button" disabled={busy} onClick={onStop}>
              Түр зогсоох
            </button>
          )}
          <button type="button" onClick={() => navigate('today')}>
            Ажлын удирдлагад очих
          </button>
        </>
      ) : (
        <span>Даалгаврын цагийг «Миний өнөөдөр» хэсгээс эхлүүлнэ.</span>
      )}
      {work.error && <p role="status">Цагийн холболт: {work.error}</p>}
    </div>
  );
}
