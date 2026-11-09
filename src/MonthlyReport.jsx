import { useEffect, useState } from 'react';
import MonthCharts from './MonthCharts';
import MonthlyEmployee from './MonthlyEmployee';
import { api } from './api';
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
              <MonthlyEmployee
                key={row.employee}
                row={row}
                month={report.month || month}
                schedule={report.schedule}
              />
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
