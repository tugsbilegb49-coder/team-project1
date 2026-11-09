import { DailyColumns, RankedBars, SegmentedBar } from './Charts';
import { minutesText } from './chartFormat';
import { clockTime } from './taskTime';

const CATEGORY_NAMES = {
  WORK: 'Ажлын програм',
  BROWSER: 'Хөтөч',
  COMMUNICATION: 'Харилцаа',
  OTHER: 'Бусад',
};

function initials(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('');
}

function todayInUlaanbaatar() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ulaanbaatar' }).format(new Date());
}

/** Сарын тайлангийн нэг ажилтан: гол тоо, асаалттай цагийн задаргаа, өдөр бүрийн багана, топ жагсаалт. */
export default function MonthlyEmployee({ row, month, schedule }) {
  const launcher = row.launcher_recorded_since ? row.launcher_seconds : null;
  const app = row.application_seconds || 0;
  const idle = row.idle_seconds || 0;
  const hasWork = typeof row.work_seconds === 'number';
  const work = hasWork ? Math.min(row.work_seconds, app) : 0;
  const unrecorded = launcher === null ? 0 : Math.max(0, launcher - app - idle);
  const parts = [
    ...(hasWork
      ? [
          { label: 'Ажлын програм', value: work, color: '--viz-1' },
          { label: 'Бусад програм', value: app - work, color: '--viz-2' },
        ]
      : [{ label: 'Апп ашигласан', value: app, color: '--viz-1' }]),
    { label: 'Идэвхгүй', value: idle, color: '--viz-idle' },
    ...(launcher === null ? [] : [{ label: 'Бүртгээгүй', value: unrecorded, color: '--viz-none' }]),
  ];
  const apps = row.applications
    .filter((item) => item.application.toLowerCase() !== 'idle')
    .slice(0, 6)
    .map((item) => ({
      label: item.application,
      value: item.seconds,
      note: CATEGORY_NAMES[item.category] || '',
    }));
  const tasks = row.tasks.slice(0, 5).map((task) => ({
    label: task.title,
    value: task.seconds,
    note: `оролцоо ${task.contribution_percent}%`,
  }));
  return (
    <article className="monthly-employee">
      <header className="monthly-head">
        <span className="monthly-avatar" aria-hidden="true">
          {initials(row.name)}
        </span>
        <div>
          <h3>
            {row.name}{' '}
            <small>
              @{row.username}
              {!row.is_active && ' · идэвхгүй'}
            </small>
          </h3>
          <p className="muted">
            {row.department || 'Хэлтэсгүй'} ·{' '}
            {row.launcher_last_upload
              ? `Програмын цаг илгээсэн: ${new Date(row.launcher_last_upload).toLocaleString('mn-MN', { timeZone: 'Asia/Ulaanbaatar' })}`
              : 'Програмын цаг хараахан ирээгүй. Ажилтан WorkTrack-аа дахин асааж төхөөрөмжөө холбоно.'}
          </p>
        </div>
      </header>
      <dl className="monthly-stats">
        <div>
          <dt>WorkTrack асаалттай</dt>
          <dd>{launcher === null ? '—' : clockTime(launcher)}</dd>
        </div>
        <div>
          <dt>Апп ашигласан (идэвхгүйг хассан)</dt>
          <dd>{clockTime(app)}</dd>
          {hasWork && app > 0 && <span>ажлын програм {Math.round((work * 100) / app)}%</span>}
        </div>
        <div>
          <dt>Даалгаварт бүртгэсэн</dt>
          <dd>{clockTime(row.task_seconds)}</dd>
          <span>идэвхгүй {clockTime(idle)}</span>
        </div>
        <div>
          <dt>Энэ сард дуусгасан</dt>
          <dd>{row.completed_tasks.length}</dd>
          <span>
            шилжүүлсэн {row.transfers_sent} · хүлээн авсан {row.transfers_received}
          </span>
        </div>
      </dl>
      <SegmentedBar title="WorkTrack асаалттай цаг юунд зарцуулагдсан" parts={parts} />
      <p className="muted">
        «Бүртгээгүй» нь WorkTrack нээлттэй байсан ч «Ажил эхлүүлэх» дараагүй, түр зогсоосон эсвэл
        бүртгэл тасарсан хугацаа. Даалгаврын цаг тусдаа хэмжигддэг тул энд нэмэгдэхгүй. Ажлын
        хуваарийн гадна: {clockTime(row.outside_schedule_seconds || 0)}.
      </p>
      {Array.isArray(row.daily) && (
        <DailyColumns
          title="Өдөр бүрийн ажил"
          month={month}
          days={row.daily}
          schedule={schedule}
          today={todayInUlaanbaatar()}
        />
      )}
      <div className="monthly-charts">
        <RankedBars
          title="Хамгийн их ашигласан програм"
          rows={apps}
          format={minutesText}
          empty="Аппын бүртгэл ирээгүй."
        />
        <RankedBars
          title="Даалгаварт зарцуулсан цаг"
          rows={tasks}
          format={minutesText}
          empty="Даалгаврын цаг бүртгээгүй."
        />
      </div>
      <details>
        <summary>{row.name} — ажлын дэлгэрэнгүй</summary>
        <h4>Энэ сард цаг бүртгэсэн даалгавар</h4>
        {row.tasks.length ? (
          <ul>
            {row.tasks.map((task) => (
              <li key={task.id}>
                {task.title} — {clockTime(task.seconds)}; нийт даалгаварт оруулсан одоогийн хувь:{' '}
                {task.contribution_percent}%
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
            {row.applications.map((item) => (
              <li key={item.application}>
                {item.application} — {clockTime(item.seconds)}
              </li>
            ))}
          </ul>
        ) : (
          <p>Аппын бүртгэл ирээгүй.</p>
        )}
      </details>
    </article>
  );
}
