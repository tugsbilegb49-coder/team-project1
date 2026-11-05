import { useState } from "react";
import "./Tasks.css";

function Tasks({
  tasks,
  members,
  onCreate,
  onUpdate,
  onDelete,
  onQuality,
  canManage,
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [filterMember, setFilterMember] = useState("Бүгд");
  const [filterStatus, setFilterStatus] = useState("Бүгд");
  async function addTask(e) {
    e.preventDefault();

    if (!title.trim()) {
      alert("Даалгаврын нэрээ оруулна уу.");
      return;
    }

    if (!assignedTo) return alert("Гишүүн сонгоно уу.");
    const ok = await onCreate({
      title,
      description,
      employee: Number(assignedTo),
      due_date: deadline || null,
    });
    if (!ok) return;

    setTitle("");
    setDescription("");
    setDeadline("");
    setAssignedTo("");
  }

  function changeStatus(id, newStatus) {
    onUpdate(id, newStatus);
  }

  function deleteTask(id) {
    onDelete(id);
  }
  const filteredTasks = tasks.filter(
    (task) =>
      (filterMember === "Бүгд" || String(task.employee) === filterMember) &&
      (filterStatus === "Бүгд" || task.status === filterStatus),
  );
  return (
    <div className="tasks-page">
      <header className="tasks-header">
        <h1>Миний даалгавар</h1>
        <p>Өөрийн ажлуудаа нэг дор удирдаарай.</p>
      </header>

      {canManage && (
        <form className="task-form" onSubmit={addTask}>
          <h2>Шинэ даалгавар нэмэх</h2>

          <label>Даалгаврын нэр</label>
          <input
            type="text"
            placeholder="Даалгаврын нэрээ бичнэ үү"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />

          <label>Тайлбар</label>
          <textarea
            placeholder="Даалгаврын тайлбар"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />

          <label>Дуусах хугацаа</label>
          <input
            type="date"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />

          <label>Хариуцах гишүүн</label>
          <select
            value={assignedTo}
            onChange={(e) => setAssignedTo(e.target.value)}
          >
            <option value="">Гишүүн сонгох</option>

            {members.map((member) => (
              <option key={member.id ?? member.name} value={member.id}>
                {member.name}
              </option>
            ))}
          </select>

          <button type="submit">+ Даалгавар нэмэх</button>
        </form>
      )}

      <section className="tasks-list">
        <label>Гишүүнээр шүүх</label>
        <select
          value={filterMember}
          onChange={(e) => setFilterMember(e.target.value)}
        >
          <option value="Бүгд">Бүх гишүүд</option>

          {members.map((member) => (
            <option key={member.id ?? member.name} value={member.id}>
              {member.name}
            </option>
          ))}
        </select>

        <label>Төлөвөөр шүүх</label>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
        >
          <option value="Бүгд">Бүх төлөв</option>
          <option value="Хүлээгдэж байна">Хүлээгдэж байна</option>
          <option value="Хийгдэж байна">Хийгдэж байна</option>
          <option value="Дууссан">Дууссан</option>
        </select>

        <h2>Даалгаврын жагсаалт ({filteredTasks.length})</h2>

        {filteredTasks.length === 0 ? (
          <p className="empty-message">
            Одоогоор даалгавар алга. Шинэ даалгавар нэмээрэй.
          </p>
        ) : (
          filteredTasks.map((task) => (
            <article className="task-item" key={task.id}>
              <div>
                <h3>{task.title}</h3>

                {task.description && <p>{task.description}</p>}

                {task.deadline && <small>Дуусах: {task.deadline}</small>}

                {task.assignedTo && <p>Хариуцах гишүүн: {task.assignedTo}</p>}

                {canManage && (
                  <label>
                    Чанарын үнэлгээ (0–100)
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      defaultValue={task.quality_score ?? ""}
                      key={`${task.id}-${task.quality_score}`}
                      onBlur={(e) => {
                        const value =
                          e.target.value === "" ? null : Number(e.target.value);
                        if (
                          value !==
                            (task.quality_score === null
                              ? null
                              : Number(task.quality_score)) &&
                          (value === null || (value >= 0 && value <= 100))
                        )
                          onQuality(task.id, value);
                      }}
                    />
                  </label>
                )}
                <label>Төлөв</label>
                <select
                  disabled={!canManage}
                  value={task.status}
                  onChange={(e) => changeStatus(task.id, e.target.value)}
                >
                  <option value="Хүлээгдэж байна">Хүлээгдэж байна</option>
                  <option value="Хийгдэж байна">Хийгдэж байна</option>
                  <option value="Дууссан">Дууссан</option>
                </select>
              </div>

              <div className="task-actions">
                <button
                  type="button"
                  disabled={!canManage}
                  className="delete-button"
                  onClick={() => deleteTask(task.id)}
                >
                  Устгах
                </button>
              </div>
            </article>
          ))
        )}
      </section>
    </div>
  );
}

export default Tasks;
