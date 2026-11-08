import { useEffect, useState } from 'react';
import { api } from './api';
import { Heatmap, RankedBars } from './Charts';
import { minutesText } from './chartFormat';

/** Сарын харьцуулалт: ажилтан, хэлтэс бүрийн дундаж оноо, долоо хоногийн өдөр × цаг. */
export default function MonthCharts({ month, revision }) {
  const [data, setData] = useState(null),
    [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api('/api/reports/charts/?' + new URLSearchParams({ month }), { signal: controller.signal })
      .then((value) => {
        setData(value);
        setError('');
      })
      .catch((failure) => {
        if (failure.name !== 'AbortError') setError(failure.message);
      });
    return () => controller.abort();
  }, [month, revision]);
  if (error) return <p role="alert">Харьцуулалт уншигдсангүй: {error}</p>;
  if (!data) return <p className="muted">Харьцуулалт уншиж байна…</p>;
  const score = (value) => value.toFixed(1);
  return (
    <section className={`chart-grid month-charts`} aria-label="Сарын харьцуулалт">
      <div className="chart-card">
        <RankedBars
          title="Ажилтнуудын сарын дундаж оноо"
          max={100}
          format={score}
          rows={data.employees.map((row) => ({
            label: row.name,
            value: row.average_score,
            note: `${row.scored_days} өдөр · ${row.department}`,
          }))}
          empty="Энэ сард оноо тооцогдоогүй."
        />
      </div>
      <div className="chart-card">
        <RankedBars
          title="Хэлтсүүдийн дундаж оноо"
          max={100}
          format={score}
          rows={data.departments.map((row) => ({
            label: row.department,
            value: row.average_score,
            note: `${row.people} хүн · ажилласан ${minutesText(row.work_seconds)}`,
          }))}
          empty="Энэ сард оноо тооцогдоогүй."
        />
      </div>
      <div className="chart-card wide">
        <Heatmap title="Хэзээ хамгийн их ажилладаг вэ (өдөр × цаг)" grid={data.heatmap} />
      </div>
    </section>
  );
}
