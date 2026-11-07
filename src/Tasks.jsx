import { useEffect, useRef, useState } from "react";
import TaskCollaboration from './TaskCollaboration';
import "./Tasks.css";

function Tasks({
  tasks,
  members,
  onCreate,
  onUpdate,
  onDelete,
  onQuality,
  canManage,
  busy,
  user,
  work,
  onStart,
  onTaskOnlyStart,
  onAction,
  onRefresh,
}) {
  const activeMembers = members.filter((member) => member.is_active);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [filterMember, setFilterMember] = useState("Бүгд");
  const [filterStatus, setFilterStatus] = useState("Бүгд");
  useEffect(() => {
    if (busy) return;
    const timer = setInterval(onRefresh, 15000);
    return () => clearInterval(timer);
  }, [busy, onRefresh]);
  async function addTask(e) {
    e.preventDefault();

    if (!title.trim()) {
      alert("Даалгаврын нэрээ оруулна уу.");
      return;
    }

    if (!activeMembers.some((member) => String(member.id) === assignedTo))
      return alert("Идэвхтэй гишүүн сонгоно уу.");
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
        <button type="button" disabled={busy} onClick={onRefresh}>Даалгавар шинэчлэх</button>
        <p className="muted">Цаг бүртгэхдээ «Ажиллаж эхлэх» дарна. Нэг удаад нэг даалгаварт цаг бүртгэнэ.
          Вебээ нээлттэй байлгана; холболт 90 секунд тасарвал цаг зогсоно. Жагсаалт 15 секунд тутам шинэчлэгдэнэ.</p>
      </header>

      {canManage && (
        <form className="task-form" onSubmit={addTask}>
          <h2>Шинэ даалгавар нэмэх</h2>

          <fieldset disabled={busy}>
            <label htmlFor="task-title">Даалгаврын нэр</label>
            <input
              type="text"
              id="task-title"
              required
              maxLength={200}
              placeholder="Даалгаврын нэрээ бичнэ үү"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />

            <label htmlFor="task-description">Тайлбар</label>
            <textarea
              id="task-description"
              placeholder="Даалгаврын тайлбар"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />

            <label htmlFor="task-deadline">Дуусах хугацаа</label>
            <input
              id="task-deadline"
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
            />

            <label htmlFor="task-employee">Хариуцах гишүүн</label>
            <select
              id="task-employee"
              required
              value={
                activeMembers.some((member) => String(member.id) === assignedTo)
                  ? assignedTo
                  : ""
              }
              onChange={(e) => setAssignedTo(e.target.value)}
            >
              <option value="">Гишүүн сонгох</option>

              {activeMembers.map((member) => (
                <option key={member.id ?? member.name} value={member.id}>
                  {member.name}
                </option>
              ))}
            </select>

            <button type="submit">+ Даалгавар нэмэх</button>
          </fieldset>
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
            <article className="task-item task-card" key={task.id}>
              <div className="task-card-content">
                <h3>{task.title}</h3>

                {task.description && <p>{task.description}</p>}

                {task.deadline && <small>Дуусах: {task.deadline}</small>}

                {task.assignedTo && <p>Хариуцах гишүүн: {task.assignedTo}</p>}

                {(task.can_manage ?? canManage) && (
                  <QualityEditor
                    key={`${task.id}:${task.quality_score ?? ""}`}
                    task={task}
                    onSave={onQuality}
                    disabled={busy}
                  />
                )}
                <label htmlFor={`task-status-${task.id}`}>Төлөв</label>
                <select
                  id={`task-status-${task.id}`}
                  disabled={!(task.can_manage ?? canManage) || busy}
                  value={task.status}
                  onChange={(e) => changeStatus(task.id, e.target.value)}
                >
                  <option value="Хүлээгдэж байна">Хүлээгдэж байна</option>
                  <option value="Хийгдэж байна">Хийгдэж байна</option>
                  <option value="Дууссан">Дууссан</option>
                </select>
                <TaskCollaboration task={task} user={user} busy={busy} onAction={onAction} onStart={onStart} onTaskOnlyStart={onTaskOnlyStart} work={work}/>
              </div>

              <div className="task-actions">
                <button
                  type="button"
                  disabled={!(task.can_manage ?? canManage) || busy}
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

function QualityEditor({ task, onSave, disabled }) {
  const stored = task.quality_score == null ? "" : String(task.quality_score);
  const inputRef = useRef(null);
  const [value, setValue] = useState(stored);
  const [saved, setSaved] = useState(stored);
  const [error, setError] = useState("");
  const changed =
    value === "" || saved === ""
      ? value !== saved
      : Number(value) !== Number(saved);
  function validate() {
    if (inputRef.current?.validity.badInput) {
      setError("Тоон үнэлгээ оруулна уу.");
      return false;
    }
    const number = Number(value);
    if (
      value !== "" &&
      (!Number.isFinite(number) ||
        number < 0 ||
        number > 100 ||
        Math.abs(number * 100 - Math.round(number * 100)) > 1e-7)
    ) {
      setError(
        "0–100 хооронд, хамгийн ихдээ 2 орны нарийвчлалтай үнэлгээ оруулна уу.",
      );
      return false;
    }
    setError("");
    return true;
  }
  return (
    <form
      className="quality-form"
      onSubmit={async (event) => {
        event.preventDefault();
        if (disabled || !changed || !validate()) return;
        const ok = await onSave(task.id, value === "" ? null : Number(value));
        if (ok) {
          setSaved(value);
          setError("");
        } else
          setError("Үнэлгээ хадгалагдсангүй. Алдааг засаж дахин оролдоно уу.");
      }}
      noValidate
    >
      <label htmlFor={`quality-${task.id}`}>Чанарын үнэлгээ (0–100)</label>
      <input
        id={`quality-${task.id}`}
        ref={inputRef}
        type="number"
        min="0"
        max="100"
        step="0.01"
        value={value}
        disabled={disabled}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `quality-error-${task.id}` : undefined}
        onChange={(event) => setValue(event.target.value)}
        onBlur={validate}
      />
      <button type="submit" disabled={disabled || !changed}>
        Үнэлгээ хадгалах
      </button>
      {error && (
        <p id={`quality-error-${task.id}`} role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
