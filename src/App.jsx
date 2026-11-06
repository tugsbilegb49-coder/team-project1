import { useEffect, useRef, useState } from "react";
import { api, list, login, logout, hasAuth, onAuthCleared } from "./api";
import Tasks from "./Tasks";
import Members from "./Members";
import "./App.css";
const statuses = {
  TODO: "Хүлээгдэж байна",
  IN_PROGRESS: "Хийгдэж байна",
  DONE: "Дууссан",
};
function localToday() {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: "Asia/Ulaanbaatar",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = (key) => parts.find((part) => part.type === key).value;
  return `${value("year")}-${value("month")}-${value("day")}`;
}
function App() {
  const [user, setUser] = useState(null),
    [page, setPage] = useState("dashboard");
  const [tasks, setTasks] = useState([]),
    [members, setMembers] = useState([]),
    [departments, setDepartments] = useState([]);
  const [reportState, setReport] = useState(null),
    [employee, setEmployee] = useState("");
  const [date, setDate] = useState(localToday);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false),
    [ready, setReady] = useState(() => !hasAuth()),
    [revision, setRevision] = useState(0);
  const mounted = useRef(false),
    session = useRef(0),
    running = useRef(false),
    reportRequest = useRef(0);
  const today = localToday();
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(date);
  const reportKey = `${user?.id}:${employee}:${date}`;
  const currentReport =
    reportState?.key === reportKey && reportState.revision === revision
      ? reportState
      : null;
  const report = currentReport?.data || null;
  const reportError = currentReport?.error || "";
  const maxMinutes =
    report?.applications.reduce(
      (max, row) => Math.max(max, row.seconds / 60),
      1,
    ) || 1;
  const canManage = Boolean(
    user && (user.is_admin || (user.role === "MANAGER" && user.department)),
  );
  function resetSession(reason) {
    session.current += 1;
    reportRequest.current += 1;
    running.current = false;
    setBusy(false);
    setUser(null);
    setTasks([]);
    setMembers([]);
    setDepartments([]);
    setReport(null);
    setEmployee("");
    setPage("dashboard");
    setError(
      reason === "expired" ? "Нэвтрэх хугацаа дууссан. Дахин нэвтэрнэ үү." : "",
    );
  }
  async function load(signal) {
    const options = signal ? { signal } : {};
    const expected = session.current;
    const [me, users, rows, divisions] = await Promise.all([
      api("/api/users/me/", options),
      list("/api/users/", options),
      list("/api/tasks/", options),
      list("/api/departments/", options),
    ]);
    if (!mounted.current || expected !== session.current) return false;
    setUser(me);
    setDepartments(divisions);
    setMembers(
      users.map((row) => ({
        ...row,
        name:
          [row.first_name, row.last_name].filter(Boolean).join(" ") ||
          row.username,
      })),
    );
    setTasks(
      rows.map((row) => ({
        ...row,
        status: statuses[row.status],
        deadline: row.due_date,
        assignedTo: row.employee_name,
      })),
    );
    setEmployee((current) =>
      users.some((row) => String(row.id) === current) ? current : String(me.id),
    );
    setRevision((value) => value + 1);
    return true;
  }
  async function run(action) {
    if (running.current) return false;
    const expected = session.current;
    running.current = true;
    setError("");
    setBusy(true);
    try {
      return (await action()) !== false;
    } catch (failure) {
      if (
        mounted.current &&
        expected === session.current &&
        failure.name !== "AbortError"
      )
        setError(failure.message);
      return false;
    } finally {
      if (mounted.current && expected === session.current) {
        running.current = false;
        setBusy(false);
      }
    }
  }
  useEffect(() => {
    mounted.current = true;
    const lifecycle = new AbortController();
    const unsubscribe = onAuthCleared((reason) => {
      if (!lifecycle.signal.aborted) resetSession(reason);
    });
    if (hasAuth())
      load(lifecycle.signal)
        .catch((failure) => {
          if (!lifecycle.signal.aborted && failure.name !== "AbortError")
            setError(failure.message);
        })
        .finally(() => {
          if (!lifecycle.signal.aborted) setReady(true);
        });
    return () => {
      lifecycle.abort();
      mounted.current = false;
      session.current += 1;
      unsubscribe();
    };
  }, []);
  useEffect(() => {
    if (!user?.id || !employee || !validDate) return;
    const controller = new AbortController();
    const request = ++reportRequest.current,
      expected = session.current;
    api(`/api/scores/dashboard/?employee_id=${employee}&date=${date}`, {
      signal: controller.signal,
    })
      .then((data) => {
        if (
          !data ||
          !Array.isArray(data.applications) ||
          !Array.isArray(data.camera)
        )
          throw new Error("Тайлангийн хариу буруу форматтай байна.");
        if (
          !controller.signal.aborted &&
          request === reportRequest.current &&
          expected === session.current
        )
          setReport({ key: reportKey, revision, data });
      })
      .catch((failure) => {
        if (
          !controller.signal.aborted &&
          request === reportRequest.current &&
          expected === session.current &&
          failure.name !== "AbortError"
        )
          setReport({ key: reportKey, revision, error: failure.message });
      });
    return () => controller.abort();
  }, [user?.id, employee, date, validDate, reportKey, revision]);
  async function signIn(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await run(async () => {
      await login(form.get("username"), form.get("password"));
      return load();
    });
  }
  async function mutate(path, method, data) {
    return run(async () => {
      await api(path, {
        method,
        ...(data ? { body: JSON.stringify(data) } : {}),
      });
      try {
        return await load();
      } catch (failure) {
        if (failure.name === "AbortError" || !hasAuth()) throw failure;
        setError(
          `Өөрчлөлт хадгалагдсан. Жагсаалт шинэчлэгдсэнгүй: ${failure.message}`,
        );
        return true;
      }
    });
  }
  if (!ready) return <main className="main">Уншиж байна…</main>;
  if (!user && hasAuth())
    return (
      <main className="main">
        <h1>WorkTrack</h1>
        <p>Хадгалсан нэвтрэлтийг сэргээж чадсангүй.</p>
        {error && <p role="alert">{error}</p>}
        <button disabled={busy} onClick={() => run(load)}>
          Дахин холбогдох
        </button>
      </main>
    );
  if (!user)
    return (
      <main className="main">
        <form className="task-form" onSubmit={signIn}>
          <h1>WorkTrack — Нэвтрэх</h1>
          <label htmlFor="login-username">Хэрэглэгчийн нэр</label>
          <input
            id="login-username"
            name="username"
            autoComplete="username"
            required
            disabled={busy}
          />
          <label htmlFor="login-password">Нууц үг</label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            disabled={busy}
          />
          {error && <p role="alert">{error}</p>}
          <button disabled={busy}>Нэвтрэх</button>
        </form>
      </main>
    );
  const done = tasks.filter((t) => t.status === statuses.DONE).length;
  return (
    <div className="app">
      <aside className="sidebar">
        <h2>WorkTrack</h2>
        <nav>
          {[
            ["dashboard", "Dashboard"],
            ["tasks", "Даалгавар"],
            ["members", "Багийн гишүүд"],
            ["reports", "Тайлан"],
          ].map(([key, label]) => (
            <button
              type="button"
              key={key}
              className={page === key ? "active" : ""}
              onClick={() => setPage(key)}
            >
              {label}
            </button>
          ))}
        </nav>
        <p>
          {user.username} · {user.role}
        </p>
        <button disabled={busy} onClick={() => run(() => logout())}>
          Гарах
        </button>
      </aside>
      <main className="main" aria-busy={busy}>
        {user.role === "MANAGER" && !user.department && !user.is_admin && (
          <p role="alert">
            Manager-ийн хэлтэс тохируулагдаагүй байна. Admin-аар хэлтэс
            сонгуулна уу.
          </p>
        )}
        {error && <p role="alert">{error}</p>}
        {busy && <p>Хадгалж байна…</p>}
        {page === "tasks" ? (
          <Tasks
            tasks={tasks}
            members={members}
            canManage={canManage}
            busy={busy}
            onCreate={(data) => mutate("/api/tasks/", "POST", data)}
            onUpdate={(id, label) =>
              mutate(`/api/tasks/${id}/`, "PATCH", {
                status: Object.keys(statuses).find(
                  (key) => statuses[key] === label,
                ),
              })
            }
            onQuality={(id, quality_score) =>
              mutate(`/api/tasks/${id}/`, "PATCH", { quality_score })
            }
            onDelete={(id) => mutate(`/api/tasks/${id}/`, "DELETE")}
          />
        ) : page === "members" ? (
          <Members
            user={user}
            members={members}
            departments={departments}
            busy={busy}
            mutate={mutate}
          />
        ) : (
          <section>
            <header className="header">
              <h1>{page === "reports" ? "Тайлан" : "Dashboard"}</h1>
              <button disabled={busy} onClick={() => run(load)}>
                Шинэчлэх
              </button>
            </header>
            <section className="stats">
              <div className="stat-card">
                <p>Нийт даалгавар</p>
                <h2>{tasks.length}</h2>
              </div>
              <div className="stat-card">
                <p>Дууссан</p>
                <h2>{done}</h2>
              </div>
              <div className="stat-card">
                <p>Гүйцэтгэл</p>
                <h2>
                  {tasks.length ? Math.round((done / tasks.length) * 100) : 0}%
                </h2>
              </div>
            </section>
            <section className="task-section">
              <h2>Өдрийн activity ба бүтээмж</h2>

              <div className="activity-controls">
                <select
                  value={employee}
                  aria-label="Тайлангийн ажилтан"
                  disabled={busy}
                  onChange={(e) => setEmployee(e.target.value)}
                >
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>

                <input
                  type="date"
                  aria-label="Тайлангийн огноо"
                  disabled={busy}
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  required
                />

                <button
                  disabled={busy || !employee || !validDate || date > today}
                  onClick={() =>
                    run(async () => {
                      await api("/api/scores/calculate/", {
                        method: "POST",
                        body: JSON.stringify({
                          employee_id: Number(employee),
                          date,
                        }),
                      });
                      setRevision((value) => value + 1);
                    })
                  }
                >
                  Оноо тооцох / шинэчлэх
                </button>
              </div>

              {reportError && <p role="alert">{reportError}</p>}
              {validDate && employee && !report && !reportError && (
                <p role="status">Тайлан уншиж байна…</p>
              )}
              {!validDate && <p>Тайлангийн огноо сонгоно уу.</p>}
              {report && (
  <div className="activity-dashboard">
    <div className="activity-score-card">
      <p>Өдрийн бүтээмжийн оноо</p>
      <h3>{report.score ? report.score.score : "—"}</h3>
      <span>
        {report.score ? report.score.category : "Тооцоолоогүй"}
      </span>
    </div>

    <div className="activity-detail-card">
      <h3>Application categories</h3>
      {report.application_categories?.length ? (
        report.application_categories.map((row) => (
          <div className="activity-row" key={row.category}>
            <span>{row.category}</span>
            <strong>{(row.seconds / 60).toFixed(1)} мин</strong>
          </div>
        ))
      ) : (
        <p>Ангиллын мэдээлэл бүртгэгдээгүй.</p>
      )}
    </div>

    <div className="activity-detail-card">
      <h3>Application activity</h3>
      {report.applications?.length ? (
        <div className="activity-chart">
          {report.applications.map((row) => {
            const minutes = row.seconds / 60;
            const maxMinutes = Math.max(
              ...report.applications.map((item) => item.seconds / 60),
              1
            );

            return (
              <div
                className="chart-item"
                key={`${row.application}-${row.category}`}
              >
                <div className="chart-value">
                  {minutes.toFixed(1)} мин
                </div>
                <div className="chart-bar-bg">
                  <div
                    className="chart-bar-fill"
                    style={{
                      width: `${(minutes / maxMinutes) * 100}%`,
                    }}
                  />
                </div>
                <div className="chart-label">
                  {row.application}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p>Activity бүртгэгдээгүй.</p>
      )}
    </div>

    <div className="activity-detail-card">
      <h3>Website activity</h3>
      {report.websites?.length ? (
        <div className="activity-chart">
          {report.websites.map((row) => {
            const minutes = row.seconds / 60;
            const maxMinutes = Math.max(
              ...report.websites.map((item) => item.seconds / 60),
              1
            );

            return (
              <div className="chart-item" key={row.domain}>
                <div className="chart-value">
                  {minutes.toFixed(1)} мин
                </div>
                <div className="chart-bar-bg">
                  <div
                    className="chart-bar-fill"
                    style={{
                      width: `${(minutes / maxMinutes) * 100}%`,
                    }}
                  />
                </div>
                <div className="chart-label">
                  {row.domain}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p>Website мэдээлэл одоогоор бүртгэгдээгүй.</p>
      )}
    </div>

    <div className="activity-detail-card">
      <h3>Camera activity</h3>
      {report.camera?.length ? (
        report.camera.map((row) => (
          <div className="activity-row" key={row.state}>
            <span>{row.state}</span>
            <strong>{(row.seconds / 60).toFixed(1)} мин</strong>
          </div>
        ))
      ) : (
        <p>Camera мэдээлэл бүртгэгдээгүй.</p>
      )}
    </div>
  </div>
)}
            </section>
          </section>
        )}
      </main>
    </div>
  );
}
export default App;
