import { useEffect, useId, useRef, useState } from 'react';
import { minutesText, SCORE_PARTS } from './chartFormat';

/*
 * Хөнгөн SVG/HTML графикууд. Өнгө нь App.css-ийн --viz-* (баталгаажсан палитр): нэг цуваа бол
 * цэнхэр, хоёр дахь нь улбар шар, «юу ч биш» (идэвхгүй, байхгүй) нь саарал. Тэмдэг бүр hover болон
 * keyboard focus дээр утгаа хэлнэ; бүх утга «Хүснэгтээр харах» дотор ч бий.
 */

/** Нэг tooltip: заагчийн дэргэд, эсвэл focus авсан тэмдгийн дээр. */
function useTip() {
  const box = useRef(null);
  const [tip, setTip] = useState(null);
  function place(event, content) {
    const frame = box.current?.getBoundingClientRect();
    if (!frame) return;
    let x, y;
    if (event.clientX !== undefined && event.type.startsWith('pointer')) {
      x = event.clientX - frame.left;
      y = event.clientY - frame.top;
    } else {
      const mark = event.currentTarget.getBoundingClientRect();
      x = mark.left + mark.width / 2 - frame.left;
      y = mark.top - frame.top;
    }
    setTip({ x: Math.max(8, Math.min(x, frame.width - 8)), y, content, flip: x > frame.width / 2 });
  }
  const bind = (content) => ({
    tabIndex: 0,
    onPointerMove: (event) => place(event, content),
    onPointerLeave: () => setTip(null),
    onFocus: (event) => place(event, content),
    onBlur: () => setTip(null),
  });
  const layer = tip && (
    <div
      className={`viz-tip ${tip.flip ? 'flip' : ''}`}
      style={{ left: tip.x, top: tip.y }}
      role="status"
      aria-live="polite"
    >
      {tip.content}
    </div>
  );
  return { box, bind, layer };
}

function TipBody({ value, label, rows }) {
  return (
    <>
      <strong>{value}</strong>
      <span>{label}</span>
      {rows?.map(([color, name, amount]) => (
        <span className="viz-tip-row" key={name}>
          <i style={{ background: `var(${color})` }} /> {name}: <b>{amount}</b>
        </span>
      ))}
    </>
  );
}

function Legend({ items }) {
  return (
    <ul className="viz-legend">
      {items.map(([color, name]) => (
        <li key={name}>
          <i style={{ background: `var(${color})` }} />
          {name}
        </li>
      ))}
    </ul>
  );
}

function TableView({ caption, head, rows }) {
  return (
    <details className="viz-table">
      <summary>Хүснэгтээр харах</summary>
      <div className="viz-table-scroll">
        <table>
          <caption>{caption}</caption>
          <thead>
            <tr>
              {head.map((cell) => (
                <th key={cell}>{cell}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row[0]}>
                {row.map((cell, index) => (
                  <td key={index}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/** Нэг бүхлийг хэсгүүдэд хуваасан өндөр бар (≤ 6 хэсэг). thin=true бол текстгүй 8px. */
export function SegmentedBar({ title, parts, format = minutesText, thin = false, table = true }) {
  const { box, bind, layer } = useTip();
  const total = parts.reduce((sum, part) => sum + part.value, 0);
  const share = (value) => (total ? Math.round((value * 100) / total) : 0);
  const shown = parts.filter((part) => part.value > 0);
  return (
    <figure className="viz" ref={box}>
      {title && <figcaption>{title}</figcaption>}
      {total ? (
        <div
          className={`viz-segments ${thin ? 'thin' : ''}`}
          role="img"
          aria-label={`${title || ''}: ${shown.map((part) => `${part.label} ${format(part.value)} (${share(part.value)}%)`).join(', ')}`}
        >
          {shown.map((part) => (
            <div
              key={part.label}
              className="viz-segment"
              style={{ flexGrow: part.value, background: `var(${part.color})` }}
              aria-label={`${part.label}: ${format(part.value)}, ${share(part.value)}%`}
              {...bind(
                <TipBody
                  value={format(part.value)}
                  label={`${part.label} · ${share(part.value)}%`}
                />,
              )}
            >
              {!thin && share(part.value) >= 12 && <span>{share(part.value)}%</span>}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">Одоогоор бүртгэл алга.</p>
      )}
      <Legend items={parts.map((part) => [part.color, part.label])} />
      {layer}
      {table && total > 0 && (
        <TableView
          caption={title}
          head={['Хэсэг', 'Хэмжээ', 'Хувь']}
          rows={parts.map((part) => [part.label, format(part.value), `${share(part.value)}%`])}
        />
      )}
    </figure>
  );
}

const KIND_STYLE = {
  work: ['--viz-1', 'Ажлын програм'],
  other: ['--viz-2', 'Бусад програм'],
  idle: ['--viz-idle', 'Идэвхгүй'],
};

/** Өглөөнөөс орой хүртэл 15 минут тутам: аль төрөл давамгайлсан. */
export function Timeline({ title, slots }) {
  const { box, bind, layer } = useTip();
  if (!slots.length)
    return (
      <figure className="viz">
        <figcaption>{title}</figcaption>
        <p className="muted">Өнөөдөр бүртгэл алга.</p>
      </figure>
    );
  const first = Math.floor(slots[0].slot / 4) * 4;
  const last = Math.ceil((slots[slots.length - 1].slot + 1) / 4) * 4;
  const bySlot = Object.fromEntries(slots.map((slot) => [slot.slot, slot]));
  const cells = [];
  for (let index = first; index < last; index += 1) cells.push(bySlot[index] || { slot: index });
  const label = (index) =>
    `${String(Math.floor(index / 4)).padStart(2, '0')}:${String((index % 4) * 15).padStart(2, '0')}`;
  const hours = [];
  const step = (last - first) / 4 > 10 ? 2 : 1;
  for (let hour = first / 4; hour <= last / 4; hour += step) hours.push(hour);
  return (
    <figure className="viz" ref={box}>
      <figcaption>{title}</figcaption>
      <div
        className="viz-timeline"
        role="img"
        aria-label={`${title}: ${label(first)}–${label(last)}`}
      >
        {cells.map((cell) => {
          const kinds = Object.keys(KIND_STYLE).filter((kind) => cell[kind] > 0);
          if (!kinds.length) return <div key={cell.slot} className="viz-slot empty" />;
          const main = kinds.reduce((best, kind) => (cell[kind] > cell[best] ? kind : best));
          return (
            <div
              key={cell.slot}
              className="viz-slot"
              style={{ background: `var(${KIND_STYLE[main][0]})` }}
              aria-label={`${label(cell.slot)}–${label(cell.slot + 1)}: ${kinds.map((kind) => `${KIND_STYLE[kind][1]} ${minutesText(cell[kind])}`).join(', ')}`}
              {...bind(
                <TipBody
                  value={`${label(cell.slot)}–${label(cell.slot + 1)}`}
                  label={`Ихэнхдээ: ${KIND_STYLE[main][1]}`}
                  rows={kinds.map((kind) => [
                    KIND_STYLE[kind][0],
                    KIND_STYLE[kind][1],
                    minutesText(cell[kind]),
                  ])}
                />,
              )}
            />
          );
        })}
      </div>
      <div className="viz-hours" aria-hidden="true">
        {hours.map((hour) => (
          <span key={hour} style={{ left: `${((hour * 4 - first) / (last - first)) * 100}%` }}>
            {String(hour).padStart(2, '0')}
          </span>
        ))}
      </div>
      <Legend items={Object.values(KIND_STYLE)} />
      {layer}
      <TableView
        caption={title}
        head={['Цаг', 'Ажлын програм', 'Бусад програм', 'Идэвхгүй']}
        rows={slots.map((slot) => [
          label(slot.slot),
          minutesText(slot.work),
          minutesText(slot.other),
          minutesText(slot.idle),
        ])}
      />
    </figure>
  );
}

/** Оноо = 0.4·T + 0.3·Q + 0.2·D + 0.1·W: хэсэг бүр 0–100, сул хэсэг шууд харагдана. */
export function ScoreBreakdown({ score }) {
  const values = SCORE_PARTS.map(([key, letter, name, weight]) => ({
    key,
    letter,
    name,
    weight,
    value: Number(score[key]),
  }));
  const weakest = values.reduce((low, part) => (part.value < low.value ? part : low));
  return (
    <figure className="viz score-breakdown">
      <figcaption>Оноо юунаас бүрдэв</figcaption>
      {values.map((part) => (
        <div className="score-part" key={part.key}>
          <div className="score-part-label">
            <b>{part.letter}</b> {part.name}{' '}
            <span className="muted">· жин {part.weight * 100}%</span>
            {part.key === weakest.key && part.value < 100 && (
              <span className="weak-flag">↓ хамгийн сул</span>
            )}
          </div>
          <div
            className="meter"
            role="meter"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={part.value}
            aria-label={`${part.letter} ${part.name}`}
          >
            <i style={{ width: `${part.value}%` }} />
          </div>
          <div className="score-part-value">
            <strong>{part.value.toFixed(0)}%</strong>
            <span className="muted">→ {(part.value * part.weight).toFixed(1)} оноо</span>
          </div>
        </div>
      ))}
      <p className="score-sum">
        Нийт: {values.map((part) => (part.value * part.weight).toFixed(1)).join(' + ')} ={' '}
        <strong>{Number(score.score).toFixed(1)}</strong>
      </p>
    </figure>
  );
}

const H = 220,
  PAD = { left: 36, right: 46, top: 14, bottom: 28 };

/** The element's width in CSS pixels, so SVG text keeps its real size at any screen width. */
function useWidth(fallback = 640) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(260, Math.round(entry.contentRect.width))),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** Өдөр өдрөөр оноо: 2px шугам, нимгэн дэвсгэр, сүүлийн утга шугамын үзүүрт. */
export function ScoreTrend({ title, points }) {
  const id = useId();
  const [active, setActive] = useState(null);
  const [frame, W] = useWidth();
  if (points.length < 2)
    return (
      <figure className="viz">
        <figcaption>{title}</figcaption>
        <p className="muted">
          Шугам зурахад дор хаяж хоёр өдрийн оноо хэрэгтэй. Оноо өдөр бүр автоматаар тооцогдоно.
        </p>
      </figure>
    );
  const plotW = W - PAD.left - PAD.right,
    plotH = H - PAD.top - PAD.bottom;
  const x = (index) => PAD.left + (index / (points.length - 1)) * plotW;
  const y = (value) => PAD.top + (1 - value / 100) * plotH;
  const line = points
    .map((point, index) => `${index ? 'L' : 'M'}${x(index)},${y(point.score)}`)
    .join(' ');
  const area = `${line} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const short = (date) => date.slice(5).replace('-', '/');
  const end = points[points.length - 1];
  const pick = (event) => {
    const frame = event.currentTarget.getBoundingClientRect();
    const ratio = ((event.clientX - frame.left) / frame.width) * W;
    const index = Math.round(((ratio - PAD.left) / plotW) * (points.length - 1));
    setActive(Math.max(0, Math.min(points.length - 1, index)));
  };
  const point = active === null ? null : points[active];
  return (
    <figure className="viz">
      <figcaption id={id}>{title}</figcaption>
      <div className="viz-line-frame" ref={frame}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="viz-line"
          role="img"
          aria-labelledby={id}
          tabIndex={0}
          onPointerMove={pick}
          onPointerLeave={() => setActive(null)}
          onFocus={() => setActive(points.length - 1)}
          onBlur={() => setActive(null)}
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft') setActive((value) => Math.max(0, (value ?? 0) - 1));
            if (event.key === 'ArrowRight')
              setActive((value) => Math.min(points.length - 1, (value ?? 0) + 1));
          }}
        >
          {[0, 25, 50, 75, 100].map((tick) => (
            <g key={tick}>
              <line
                className="viz-grid"
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
              />
              <text className="viz-axis" x={PAD.left - 6} y={y(tick) + 4} textAnchor="end">
                {tick}
              </text>
            </g>
          ))}
          {[0, Math.floor((points.length - 1) / 2), points.length - 1].map((index) => (
            <text
              key={index}
              className="viz-axis"
              x={x(index)}
              y={H - 8}
              textAnchor={index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'}
            >
              {short(points[index].date)}
            </text>
          ))}
          <path d={area} className="viz-area" />
          <path d={line} className="viz-stroke" />
          {point && (
            <line className="viz-cross" x1={x(active)} x2={x(active)} y1={PAD.top} y2={y(0)} />
          )}
          <circle className="viz-dot" cx={x(points.length - 1)} cy={y(end.score)} r={4} />
          {point && <circle className="viz-dot" cx={x(active)} cy={y(point.score)} r={4} />}
          <text className="viz-end" x={x(points.length - 1) + 8} y={y(end.score) + 4}>
            {end.score.toFixed(0)}
          </text>
        </svg>
        {point && (
          <div
            className={`viz-tip ${active > points.length / 2 ? 'flip' : ''}`}
            style={{ left: `${(x(active) / W) * 100}%`, top: `${(y(point.score) / H) * 100}%` }}
          >
            <strong>{point.score.toFixed(1)} оноо</strong>
            <span>{point.date}</span>
            {SCORE_PARTS.map(([key, letter]) => (
              <span className="viz-tip-row" key={key}>
                {letter}: <b>{point[key].toFixed(0)}%</b>
              </span>
            ))}
          </div>
        )}
      </div>
      <TableView
        caption={title}
        head={['Өдөр', 'Оноо', 'T', 'Q', 'D', 'W']}
        rows={points.map((row) => [
          row.date,
          row.score.toFixed(1),
          ...SCORE_PARTS.map(([key]) => `${row[key].toFixed(0)}%`),
        ])}
      />
    </figure>
  );
}

/** Камер: цаг бүрт хүн байсан, байгаагүй минут (дээж секунд тутам). */
export function PresenceHours({ title, rows }) {
  const { box, bind, layer } = useTip();
  if (!rows.length) return null;
  const max = Math.max(...rows.map((row) => row.present + row.absent), 1);
  return (
    <figure className="viz" ref={box}>
      <figcaption>{title}</figcaption>
      <div className="viz-columns" role="img" aria-label={title}>
        {rows.map((row) => {
          const total = row.present + row.absent;
          return (
            <div
              className="viz-column"
              key={row.hour}
              aria-label={`${row.hour}:00 — хүн байсан ${minutesText(row.present)}, байгаагүй ${minutesText(row.absent)}`}
              {...bind(
                <TipBody
                  value={`${row.hour}:00–${row.hour + 1}:00`}
                  label={`Хүн байсан ${Math.round((row.present * 100) / (total || 1))}%`}
                  rows={[
                    ['--viz-1', 'Хүн байсан', minutesText(row.present)],
                    ['--viz-idle', 'Хүн байгаагүй', minutesText(row.absent)],
                  ]}
                />,
              )}
            >
              <div className="viz-stack" style={{ height: `${(total / max) * 100}%` }}>
                <i style={{ flexGrow: row.absent, background: 'var(--viz-idle)' }} />
                <i style={{ flexGrow: row.present, background: 'var(--viz-1)' }} />
              </div>
              <span className="viz-axis-label">{row.hour}</span>
            </div>
          );
        })}
      </div>
      <Legend
        items={[
          ['--viz-1', 'Хүн байсан'],
          ['--viz-idle', 'Хүн байгаагүй'],
        ]}
      />
      {layer}
      <TableView
        caption={title}
        head={['Цаг', 'Хүн байсан', 'Хүн байгаагүй']}
        rows={rows.map((row) => [
          `${row.hour}:00`,
          minutesText(row.present),
          minutesText(row.absent),
        ])}
      />
    </figure>
  );
}

/** Эрэмбэлсэн хэвтээ бар: нэг өнгө, их нь дээрээ; утга нь барын үзүүрт. */
export function RankedBars({ title, rows, max = null, format = (value) => value, empty }) {
  const { box, bind, layer } = useTip();
  const valued = rows.filter((row) => row.value !== null && row.value !== undefined);
  const top = max ?? Math.max(...valued.map((row) => row.value), 1);
  const sorted = [...valued].sort((a, b) => b.value - a.value);
  const missing = rows.filter((row) => row.value === null || row.value === undefined);
  return (
    <figure className="viz" ref={box}>
      <figcaption>{title}</figcaption>
      {!sorted.length && <p className="muted">{empty || 'Мэдээлэл алга.'}</p>}
      <div className="viz-ranked">
        {sorted.map((row) => (
          <div className="viz-ranked-row" key={row.label}>
            <span className="viz-ranked-name">{row.label}</span>
            <div className="viz-ranked-track">
              <div
                className="viz-ranked-bar"
                style={{ width: `${Math.max(1, (row.value / top) * 100)}%` }}
                aria-label={`${row.label}: ${format(row.value)}`}
                {...bind(
                  <TipBody
                    value={format(row.value)}
                    label={row.note ? `${row.label} · ${row.note}` : row.label}
                  />,
                )}
              />
              <span className="viz-ranked-value">{format(row.value)}</span>
            </div>
          </div>
        ))}
      </div>
      {missing.length > 0 && (
        <p className="muted">Оноогүй: {missing.map((row) => row.label).join(', ')}</p>
      )}
      {layer}
      <TableView
        caption={title}
        head={['Нэр', 'Утга', 'Тайлбар']}
        rows={[...sorted, ...missing].map((row) => [
          row.label,
          row.value === null || row.value === undefined ? '—' : format(row.value),
          row.note || '',
        ])}
      />
    </figure>
  );
}

const WEEKDAYS = ['Да', 'Мя', 'Лх', 'Пү', 'Ба', 'Бя', 'Ня'];
const RAMP = ['--seq-1', '--seq-2', '--seq-3', '--seq-4', '--seq-5'];

/** Долоо хоногийн өдөр × цаг: хэзээ хамгийн их ажилладаг (нэг өнгө, их нь бараан). */
export function Heatmap({ title, grid }) {
  const { box, bind, layer } = useTip();
  const max = Math.max(...grid.flat(), 0);
  if (!max)
    return (
      <figure className="viz">
        <figcaption>{title}</figcaption>
        <p className="muted">Энэ сард компьютерийн бүртгэл алга.</p>
      </figure>
    );
  const step = (value) => Math.min(RAMP.length - 1, Math.floor((value / max) * RAMP.length));
  return (
    <figure className="viz" ref={box}>
      <figcaption>{title}</figcaption>
      <div className="viz-heat-scroll">
        <div className="viz-heat" role="img" aria-label={title}>
          <span />
          {Array.from({ length: 24 }, (_, hour) => (
            <span key={hour} className="viz-axis-label">
              {hour % 3 === 0 ? hour : ''}
            </span>
          ))}
          {grid.map((hours, day) => [
            <span key={`d${day}`} className="viz-axis-label">
              {WEEKDAYS[day]}
            </span>,
            ...hours.map((value, hour) =>
              value ? (
                <i
                  key={`${day}-${hour}`}
                  style={{ background: `var(${RAMP[step(value)]})` }}
                  aria-label={`${WEEKDAYS[day]} ${hour}:00 — ${minutesText(value)}`}
                  {...bind(
                    <TipBody
                      value={minutesText(value)}
                      label={`${WEEKDAYS[day]} ${hour}:00–${hour + 1}:00`}
                    />,
                  )}
                />
              ) : (
                <i key={`${day}-${hour}`} className="empty" />
              ),
            ),
          ])}
        </div>
      </div>
      <div className="viz-scale" aria-hidden="true">
        Бага
        {RAMP.map((token) => (
          <i key={token} style={{ background: `var(${token})` }} />
        ))}
        Их (хамгийн ихдээ {minutesText(max)})
      </div>
      {layer}
      <TableView
        caption={title}
        head={['Өдөр', ...Array.from({ length: 24 }, (_, hour) => `${hour}`)]}
        rows={grid.map((hours, day) => [
          WEEKDAYS[day],
          ...hours.map((value) => (value ? Math.round(value / 60) : '')),
        ])}
      />
    </figure>
  );
}
