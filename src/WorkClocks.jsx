import { useEffect, useState } from 'react';
import { clockTime } from './taskTime';
import { api } from './api';

function useTick() {
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  return now;
}

export function LauncherClock({user, card = false}) {
  const [sample, setSample] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [error, setError] = useState('');
  const now = useTick();
  const connected = sample && now-sample.at < 45000;
  useEffect(() => {
    const controller = new AbortController();
    const flight = {busy:false};
    async function read() {
      if (flight.busy) return;
      flight.busy = true;
      try {
        const value = await api('/desktop/status/', {signal:controller.signal, headers:{'X-WorkTrack-Desktop':'1'}});
        if (!controller.signal.aborted) {
          const usage = value.launcher_usage;
          if (usage?.available && Array.isArray(usage.months)) {
            setSample({usage, at:Date.now()}); setError('');
          } else {
            setSample(null);
            setError(usage?.error || 'Сарын тооцоог эхлүүлэхийн тулд WorkTrack-аа дахин асаана уу.');
          }
        }
      } catch { if (!controller.signal.aborted) {setSample(null); setError('Локал launcher-тэй холбогдоогүй.');} }
      finally { flight.busy = false; }
    }
    read(); const timer = setInterval(read, 15000);
    return () => {controller.abort(); clearInterval(timer);};
  }, [user.id]);
  const Container = card ? 'article' : 'div';
  const Value = card ? 'h2' : 'strong';
  const usage = sample?.usage;
  const month = usage?.months.find(row => row.month === selectedMonth) || usage?.months.find(row => row.month === usage.current_month);
  const liveSeconds = usage?.running && month?.month === usage.current_month && connected
    ? Math.min(Math.max(0, now-sample.at)/1000, Math.max(0, usage.month_ends_at-usage.as_of)) : 0;
  return <Container className={card ? 'stat-card launcher-time-card' : 'work-clock'} aria-label="WorkTrack сарын хугацаа">
    <p>WorkTrack асаалттай байсан сарын нийт хугацаа</p>
    <Value>{month ? clockTime(month.seconds + liveSeconds) : '—'}</Value>
    {usage && <label className="usage-month">Сар сонгох
      <select value={month?.month === usage.current_month ? '' : month?.month || ''} onChange={event => setSelectedMonth(event.target.value)}>
        <option value="">Энэ сар ({usage.current_month})</option>
        {usage.months.filter(row => row.month !== usage.current_month).map(row => <option key={row.month} value={row.month}>{row.month}</option>)}
      </select>
    </label>}
    {card && <small>Энэ account-тай холбосон төхөөрөмж дээр хааж, дахин нээсэн хугацаануудыг нийлүүлнэ.
      Компьютер унтсан (Sleep) болон програм хаалттай байсан завсар орохгүй.</small>}
    {usage && !usage.running && <small>Төхөөрөмжөө холбоно уу. Өмнөх хадгалсан хугацаа хэвээр үлдэнэ.</small>}
    {usage?.sync_error && usage.sync_error !== 'unlinked' && <small role="status">Серверт цаг илгээх холболт/зөвшөөрлөө шалгана уу. Хадгалсан хугацаа төхөөрөмж дээр үлдэнэ.</small>}
    {card && usage?.recorded_since && <small>Бүртгэж эхэлсэн: {new Date(usage.recorded_since).toLocaleDateString('mn-MN', {timeZone:'Asia/Ulaanbaatar'})}</small>}
    {(!connected || error) && <small role="status">{error || 'Сарын хугацааны холболтыг шалгаж байна…'}</small>}
  </Container>;
}

export function TaskWorkClock({work, busy, onStop, navigate}) {
  const now = useTick();
  const session = work.sample?.data.session;
  const allowance = session ? Math.max(0, (Date.parse(session.lease_expires_at)-Date.parse(work.sample.data.server_now))/1000) : 0;
  const delta = work.sample ? Math.max(0, now-work.sample.at)/1000 : 0;
  const running = session?.running && delta < allowance;
  return <div className="task-work-clock">
    {session ? <>
      <span>{session.title} · {running ? 'Цаг бүртгэж байна' : 'Цаг зогссон'}</span>
      <strong aria-label="Даалгаврын session хугацаа">{clockTime(session.seconds + (session.running ? Math.min(delta, allowance) : 0))}</strong>
      {running && <button type="button" disabled={busy} onClick={onStop}>Даалгаврын цаг зогсоох</button>}
      <button type="button" onClick={() => navigate('tasks')}>Даалгаварт очих</button>
    </> : <span>Даалгаврын цаг: даалгавраа сонгоод «Ажиллаж эхлэх» дарна.</span>}
    {work.error && <p role="status">Цагийн холболт: {work.error}</p>}
  </div>;
}
