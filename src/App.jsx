import { useEffect, useState } from "react";
import { api, list, login, clearAuth } from "./api";
import Tasks from "./Tasks";
import "./App.css";
const statuses = {
  TODO: "Хүлээгдэж байна",
  IN_PROGRESS: "Хийгдэж байна",
  DONE: "Дууссан",
};
function App() {
  const [user, setUser] = useState(null),
    [page, setPage] = useState("dashboard");
  const [tasks, setTasks] = useState([]),
    [members, setMembers] = useState([]);
  const [report, setReport] = useState(null),
    [employee, setEmployee] = useState("");
  const [date, setDate] = useState(() =>
    new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ulaanbaatar" }).format(
      new Date(),
    ),
  );
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [ready, setReady] = useState(false);
  const canManage = user && (user.is_admin || user.role === "MANAGER");
  async function load() {
    const [me, users, rows] = await Promise.all([
      api("/api/users/me/"),
      list("/api/users/"),
      list("/api/tasks/"),
    ]);
    setUser(me);
    setMembers(
      users.map((u) => ({
        ...u,
        name:
          [u.first_name, u.last_name].filter(Boolean).join(" ") || u.username,
      })),
    );
    setTasks(
      rows.map((t) => ({
        ...t,
        status: statuses[t.status],
        deadline: t.due_date,
        assignedTo: t.employee_name,
      })),
    );
    setEmployee((current) => current || String(me.id));
  }
  async function run(action) {
    setError("");
    setBusy(true);
    try {
      await action();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    let active = true;
    api("/api/users/me/")
      .then(() => load())
      .catch(() => clearAuth())
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!user || !employee) return;
    let active = true;
    api(`/api/scores/dashboard/?employee_id=${employee}&date=${date}`)
      .then((data) => {
        if (active) setReport(data);
      })
      .catch((e) => {
        if (active) {
          setReport(null);
          setError(e.message);
        }
      });
    return () => {
      active = false;
    };
  }, [user, employee, date]);
  async function signIn(e) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    await run(async () => {
      await login(form.get("username"), form.get("password"));
      await load();
    });
  }
  async function mutate(path, method, data) {
    return run(async () => {
      await api(path, {
        method,
        ...(data ? { body: JSON.stringify(data) } : {}),
      });
      await load();
    });
  }
  if (!ready) return <main className="main">Уншиж байна…</main>;
  if (!user)
    return (
      <main className="main">
        <form className="task-form" onSubmit={signIn}>
          <h1>WorkTrack — Нэвтрэх</h1>
          <label>
            Хэрэглэгчийн нэр
            <input name="username" autoComplete="username" required />
          </label>
          <label>
            Нууц үг
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
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
            <p
              key={key}
              className={page === key ? "active" : ""}
              onClick={() => setPage(key)}
            >
              {label}
            </p>
          ))}
        </nav>
        <p>
          {user.username} · {user.role}
        </p>
        <button
          onClick={() => {
            clearAuth();
            setUser(null);
            setTasks([]);
            setMembers([]);
            setReport(null);
            setEmployee("");
          }}
        >
          Гарах
        </button>
      </aside>
      <main className="main" aria-busy={busy}>
        {error && <p role="alert">{error}</p>}
        {busy && <p>Хадгалж байна…</p>}
        {page === "tasks" ? (
          <Tasks
            tasks={tasks}
            members={members}
            canManage={canManage && !busy}
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
          <section>
            <h1>Багийн гишүүд</h1>
            {user.is_admin && (
              <form
                className="task-form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  const data = Object.fromEntries(new FormData(form));
                  if (await mutate("/api/users/", "POST", data)) form.reset();
                }}
              >
                <h2>Гишүүн нэмэх</h2>
                <input
                  name="username"
                  placeholder="Хэрэглэгчийн нэр"
                  required
                />
                <input name="first_name" placeholder="Нэр" required />
                <input name="email" type="email" placeholder="Имэйл" />
                <input
                  name="password"
                  type="password"
                  placeholder="Анхны нууц үг"
                  minLength={8}
                  required
                />
                <select name="role">
                  <option value="EMPLOYEE">Employee</option>
                  <option value="MANAGER">Manager</option>
                  <option value="ADMIN">Admin</option>
                </select>
                <button disabled={busy}>Нэмэх</button>
              </form>
            )}
            {members.map((m) => (
              <article className="task-item" key={m.id}>
                <div>
                  <h3>{m.name}</h3>
                  <p>
                    {m.email} · {m.role}
                  </p>
                  <small>{m.department_name}</small>
                </div>
                {user.is_admin && m.id !== user.id && m.is_active && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      mutate(`/api/users/${m.id}/`, "PATCH", {
                        is_active: false,
                      })
                    }
                  >
                    Идэвхгүй болгох
                  </button>
                )}
              </article>
            ))}
          </section>
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
              <select
                value={employee}
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
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
              <button
                disabled={busy || !date}
                onClick={() =>
                  run(async () => {
                    await api("/api/scores/calculate/", {
                      method: "POST",
                      body: JSON.stringify({
                        employee_id: Number(employee),
                        date,
                      }),
                    });
                    setReport(
                      await api(
                        `/api/scores/dashboard/?employee_id=${employee}&date=${date}`,
                      ),
                    );
                  })
                }
              >
                Оноо тооцох / шинэчлэх
              </button>
              {report && (
                <>
                  <p>
                    Оноо:{" "}
                    {report.score
                      ? `${report.score.score} (${report.score.category})`
                      : "Тооцоолоогүй"}
                  </p>
                  <h3>Application</h3>
                  {report.applications.length ? (
                    report.applications.map((row) => (
                      <p key={row.application + row.category}>
                        {row.application} · {row.category}:{" "}
                        {(row.seconds / 60).toFixed(1)} мин
                      </p>
                    ))
                  ) : (
                    <p>Activity бүртгэгдээгүй.</p>
                  )}
                  <h3>Camera</h3>
                  {report.camera.length ? (
                    report.camera.map((row) => (
                      <p key={row.state}>
                        {row.state}: {(row.seconds / 60).toFixed(1)} мин
                      </p>
                    ))
                  ) : (
                    <p>Camera мэдээлэл бүртгэгдээгүй.</p>
                  )}
                </>
              )}
            </section>
          </section>
        )}
      </main>
    </div>
  );
}
export default App;
