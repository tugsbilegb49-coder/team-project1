import { useState } from "react";
import "./Tasks.css";

function Tasks({ tasks, setTasks, members }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [filterMember, setFilterMember] = useState("Бүгд");
  const [filterStatus, setFilterStatus] = useState("Бүгд");
  function addTask(e) {
    e.preventDefault();

    if (!title.trim()) {
      alert("Даалгаврын нэрээ оруулна уу.");
      return;
    }

    const newTask = {
      id: Date.now(),
      title,
      description,
      deadline,
      assignedTo,
      status: "Хүлээгдэж байна",
    };

    setTasks([...tasks, newTask]);

    setTitle("");
    setDescription("");
    setDeadline("");
    setAssignedTo("");
  }

  function changeStatus(id, newStatus) {
    setTasks(
      tasks.map((task) =>
        task.id === id
          ? { ...task, status: newStatus }
          : task
      )
    );
  }

  function deleteTask(id) {
    setTasks(tasks.filter((task) => task.id !== id));
  }
const filteredTasks = tasks.filter(
  (task) =>
    (filterMember === "Бүгд" ||
      task.assignedTo === filterMember) &&
    (filterStatus === "Бүгд" ||
      task.status === filterStatus)
);
  return (
    <div className="tasks-page">
      <header className="tasks-header">
        <h1>Миний даалгавар</h1>
        <p>Өөрийн ажлуудаа нэг дор удирдаарай.</p>
      </header>

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
            <option key={member.id ?? member.name} value={member.name}>
              {member.name}
            </option>
          ))}
        </select>

        <button type="submit">+ Даалгавар нэмэх</button>
      </form>

      <section className="tasks-list">
  <label>Гишүүнээр шүүх</label>
  <select
    value={filterMember}
    onChange={(e) => setFilterMember(e.target.value)}
  >
    <option value="Бүгд">Бүх гишүүд</option>

    {members.map((member) => (
      <option key={member.id ?? member.name} value={member.name}>
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

                {task.deadline && (
                  <small>Дуусах: {task.deadline}</small>
                )}

                {task.assignedTo && (
                  <p>Хариуцах гишүүн: {task.assignedTo}</p>
                )}

                <label>Төлөв</label>
                <select
                  value={task.status}
                  onChange={(e) =>
                    changeStatus(task.id, e.target.value)
                  }
                >
                  <option value="Хүлээгдэж байна">
                    Хүлээгдэж байна
                  </option>
                  <option value="Хийгдэж байна">
                    Хийгдэж байна
                  </option>
                  <option value="Дууссан">Дууссан</option>
                </select>
              </div>

              <div className="task-actions">
                <button
                  type="button"
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