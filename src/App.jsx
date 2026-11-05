
import { useEffect, useState } from "react";
import "./App.css";
import Tasks from "./Tasks";

function App() {
  const [page, setPage] = useState("dashboard");

const [tasks, setTasks] = useState(() => {
  const savedTasks = localStorage.getItem("worktrack-tasks");
  return savedTasks ? JSON.parse(savedTasks) : [];
});

const [members, setMembers] = useState(() => {
  const savedMembers = localStorage.getItem("worktrack-members");
  return savedMembers ? JSON.parse(savedMembers) : [];
});
const [memberName, setMemberName] = useState("");
const [memberEmail, setMemberEmail] = useState("");
const [roles, setRoles] = useState(() => {
  const savedRoles = localStorage.getItem("worktrack-roles");

  return savedRoles
    ? JSON.parse(savedRoles)
    : [
        "Frontend Developer",
        "Backend Developer",
        "Database & Data Model Developer",
        "Computer Activity Agent Developer",
        "Camera Developer",
        "AI Developer",
        "QA Engineer",
        "Documentation",
      ];
});

const [memberRole, setMemberRole] = useState("Frontend Developer");
const [newRole, setNewRole] = useState("");
function addMember(e) {
  e.preventDefault();

  if (!memberName.trim() || !memberEmail.trim()) {
    alert("Нэр болон имэйлээ оруулна уу.");
    return;
  }

  const newMember = {
    id: Date.now(),
    name: memberName,
    email: memberEmail,
    role: memberRole,
  };

  setMembers([...members, newMember]);

  setMemberName("");
  setMemberEmail("");
  setMemberRole("Frontend Developer");
}

function deleteMember(id) {
  setMembers(members.filter((member) => member.id !== id));
}

function addRole(e) {
  e.preventDefault();

  const role = newRole.trim();

  if (!role) {
    alert("Үүргийн нэрээ оруулна уу.");
    return;
  }

  if (roles.includes(role)) {
    alert("Энэ үүрэг аль хэдийн байна.");
    return;
  }

  setRoles([...roles, role]);
  setMemberRole(role);
  setNewRole("");
}

function deleteRole(roleToDelete) {
  if (members.some((member) => member.role === roleToDelete)) {
    alert("Энэ үүрэгтэй гишүүн бүртгэлтэй байна.");
    return;
  }

  const updatedRoles = roles.filter((role) => role !== roleToDelete);

  setRoles(updatedRoles);

  if (memberRole === roleToDelete) {
    setMemberRole(updatedRoles[0] || "");
  }
}
useEffect(() => {
  localStorage.setItem("worktrack-members", JSON.stringify(members));
}, [members]);

useEffect(() => {
  localStorage.setItem("worktrack-roles", JSON.stringify(roles));
}, [roles]);

  const totalTasks = tasks.length;
  const completedTasks = tasks.filter(
    (task) => task.status === "Дууссан"
  ).length;
  const progress = totalTasks === 0
  ? 0
  : Math.round((completedTasks / totalTasks) * 100);
  const inProgressTasks = tasks.filter(
    (task) => task.status === "Хийгдэж байна"
  ).length;
  const pendingTasks = tasks.filter(
    (task) => task.status === "Хүлээгдэж байна"
  ).length;
const today = new Date().toISOString().split("T")[0];

const overdueTasks = tasks.filter(
  (task) =>
    task.deadline &&
    task.deadline < today &&
    task.status !== "Дууссан"
).length;
  return (
    <div className="app">
      <aside className="sidebar">
        <h2>WorkTrack</h2>

        <nav>
          <p
            className={page === "dashboard" ? "active" : ""}
            onClick={() => setPage("dashboard")}
          >
            Dashboard
          </p>

          <p
            className={page === "tasks" ? "active" : ""}
            onClick={() => setPage("tasks")}
          >
            Миний даалгавар
          </p>

          <p
  className={page === "members" ? "active" : ""}
  onClick={() => setPage("members")}
>
  Багийн гишүүд
</p>
          <p
  className={page === "reports" ? "active" : ""}
  onClick={() => setPage("reports")}
>
  Тайлан
</p>
        </nav>
      </aside>

      <main className="main">
        {page === "dashboard" ? (
          <>
            <header className="header">
              <div>
                <h1>Dashboard</h1>
                <p>Ажлын бүтээмж хянах систем</p>
              </div>

              <div className="user">👤 Админ</div>
            </header>

            <section className="stats">
              <div className="stat-card">
                <p>Нийт даалгавар</p>
                <h2>{totalTasks}</h2>
              </div>

              <div className="stat-card">
                <p>Дууссан</p>
                <h2>{completedTasks}</h2>
              </div>

              <div className="stat-card">
                <p>Хийгдэж байна</p>
                <h2>{inProgressTasks}</h2>
              </div>
              <div className="stat-card overdue-card">
                <p>Хугацаа хэтэрсэн</p>
                <h2>{overdueTasks}</h2>
              </div>
              <div className="stat-card">
                <p>Хүлээгдэж байна</p>
                <h2>{pendingTasks}</h2>
              </div>
            </section>
            <section className="progress-section">
  <h2>Нийт гүйцэтгэл</h2>
  <p>{progress}% дууссан</p>

  <div className="progress-bar">
    <div
      className="progress-fill"
      style={{ width: `${progress}%` }}
    ></div>
  </div>
</section>
            <section className="task-section">
              <h2>Сүүлийн даалгаврууд</h2>

              {tasks.length === 0 ? (
                <p>Одоогоор даалгавар алга.</p>
              ) : (
                tasks.slice(-3).reverse().map((task) => (
                  <div className="task-row" key={task.id}>
                    <span>{task.title}</span>
                    <span
                      className={`status ${
                        task.status === "Дууссан" ? "done" : ""
                      }`}
                    >
                      {task.status}
                    </span>
                  </div>
                ))
              )}
            </section>
          </>
              ) : page === "tasks" ? (
  <Tasks
    tasks={tasks}
    setTasks={setTasks}
    members={members}
  />
  ) : page === "members" ? (
<section className="members-section">
  <header className="header">
    <div>
      <h1>Багийн гишүүд</h1>
      <p>Төслийн багийн гишүүдийн мэдээлэл</p>
    </div>
  </header>

  <form className="task-form" onSubmit={addMember}>
    <h2>Шинэ гишүүн нэмэх</h2>

    <label>Нэр</label>
    <input
      type="text"
      placeholder="Гишүүний нэр"
      value={memberName}
      onChange={(e) => setMemberName(e.target.value)}
    />

    <label>Имэйл</label>
    <input
      type="email"
      placeholder="example@gmail.com"
      value={memberEmail}
      onChange={(e) => setMemberEmail(e.target.value)}
    />

   <label>Үүрэг</label>
<select
  value={memberRole}
  onChange={(e) => setMemberRole(e.target.value)}
>
  {roles.map((role) => (
    <option key={role} value={role}>
      {role}
    </option>
  ))}
</select>

    <button type="submit">+ Гишүүн нэмэх</button>
  </form>
<section className="tasks-list">
  <h2>Үүргийн жагсаалт ({roles.length})</h2>

  <form onSubmit={addRole}>
    <input
      type="text"
      placeholder="Шинэ үүргийн нэр"
      value={newRole}
      onChange={(e) => setNewRole(e.target.value)}
    />

    <button type="submit">+ Үүрэг нэмэх</button>
  </form>

  {roles.map((role) => (
    <article className="task-item" key={role}>
      <span>{role}</span>

      <button
        type="button"
        className="delete-button"
        onClick={() => deleteRole(role)}
      >
        Хасах
      </button>
    </article>
  ))}
</section>
  <section className="tasks-list">
    <h2>Гишүүдийн жагсаалт ({members.length})</h2>

    {members.length === 0 ? (
      <p>Одоогоор гишүүн нэмээгүй байна.</p>
    ) : (
      members.map((member) => (
        <article className="task-item" key={member.id}>
          <div>
            <h3>{member.name}</h3>
            <p>{member.email}</p>
            <small>{member.role}</small>
          </div>

          <button
            type="button"
            className="delete-button"
            onClick={() => deleteMember(member.id)}
          >
            Устгах
          </button>
        </article>
      ))
    )}
  </section>
</section>
) : (
          
          <section className="report-section">
            <header className="header">
              <div>
                
                <h1>Тайлан</h1>
                <p>Ажлын бүтээмжийн тайлан</p>
              </div>
            </header>

            <section className="stats">
              <div className="stat-card">
                <p>Нийт даалгавар</p>
                <h2>{totalTasks}</h2>
              </div>

              <div className="stat-card">
                <p>Дууссан</p>
                <h2>{completedTasks}</h2>
              </div>

              <div className="stat-card">
                <p>Хийгдэж байна</p>
                <h2>{inProgressTasks}</h2>
              </div>

              <div className="stat-card">
                <p>Хүлээгдэж байна</p>
                <h2>{pendingTasks}</h2>
              </div>
            </section>

            <section className="progress-section">
              <h2>Нийт гүйцэтгэл</h2>
              <p>{progress}% дууссан</p>

              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${progress}%` }}
                ></div>
              </div>
            </section>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;