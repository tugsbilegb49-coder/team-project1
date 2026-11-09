import { useState } from "react";

export default function Members({ user, members, departments, busy, mutate }) {
  const [role, setRole] = useState("EMPLOYEE");
  const [department, setDepartment] = useState("");
  const [editingId, setEditingId] = useState(null);
  return (
    <section>
      <h1>Багийн гишүүд</h1>
      {user.is_admin && (
        <>
          <form
            className="task-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const name = new FormData(form).get("name").trim();
              if (name && (await mutate("/api/departments/", "POST", { name })))
                form.reset();
            }}
          >
            <h2>Хэлтэс нэмэх</h2>
            <fieldset disabled={busy}>
              <label htmlFor="department-name">Хэлтсийн нэр</label>
              <input
                id="department-name"
                name="name"
                required
                maxLength={120}
              />
              <button type="submit">Хэлтэс нэмэх</button>
            </fieldset>
          </form>
          {departments.length > 0 && (
            <section className="department-edit-list" aria-label="Хэлтэс засах">
              <h2>Хэлтсийн нэр өөрчлөх</h2>
              {departments.map((row) => (
                <form
                  className="department-edit-row"
                  key={row.id}
                  onSubmit={async (event) => {
                    event.preventDefault();
                    const form = event.currentTarget;
                    const name = new FormData(form).get("name").trim();
                    if (name)
                      await mutate(`/api/departments/${row.id}/`, "PATCH", {
                        name,
                      });
                  }}
                >
                  <fieldset disabled={busy}>
                    <label htmlFor={`department-edit-${row.id}`}>
                      {row.name}
                    </label>
                    <input
                      id={`department-edit-${row.id}`}
                      name="name"
                      defaultValue={row.name}
                      required
                      maxLength={120}
                    />
                  </fieldset>
                  <button type="submit" disabled={busy}>
                    Нэр хадгалах
                  </button>
                  <button type="button" className="delete-button" disabled={busy}
                    onClick={() => {
                      if (window.confirm(`"${row.name}" хэлтсийг устгах уу? Хэлтсийн ажилтнууд хэлтэсгүй болно.`))
                        mutate(`/api/departments/${row.id}/`, "DELETE");
                    }}>
                    Хэлтэс устгах
                  </button>
                </form>
              ))}
            </section>
          )}
          <form
            className="task-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const data = Object.fromEntries(new FormData(form));
              data.department = department ? Number(department) : null;
              if (await mutate("/api/users/", "POST", data)) {
                form.reset();
                setRole("EMPLOYEE");
                setDepartment("");
              }
            }}
          >
            <h2>Гишүүн нэмэх</h2>
            <fieldset disabled={busy}>
              <label htmlFor="member-username">Хэрэглэгчийн нэр</label>
              <input
                id="member-username"
                name="username"
                required
                autoComplete="off"
              />
              <label htmlFor="member-name">Нэр</label>
              <input id="member-name" name="first_name" required />
              <label htmlFor="member-email">Имэйл</label>
              <input id="member-email" name="email" type="email" />
              <label htmlFor="member-password">Анхны нууц үг</label>
              <input
                id="member-password"
                name="password"
                type="password"
                minLength={8}
                autoComplete="new-password"
                required
              />
              <label htmlFor="member-role">Эрх</label>
              <select
                id="member-role"
                name="role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
              >
                <option value="EMPLOYEE">Employee</option>
                <option value="MANAGER">Manager</option>
                <option value="ADMIN">Admin</option>
              </select>
              <label htmlFor="member-department">
                Хэлтэс{role === "MANAGER" ? " (заавал)" : ""}
              </label>
              <select
                id="member-department"
                value={department}
                onChange={(event) => setDepartment(event.target.value)}
                required={role === "MANAGER"}
              >
                <option value="">Хэлтэс сонгох</option>
                {departments.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </select>
              {role === "MANAGER" && !departments.length && (
                <p>Manager нэмэхийн өмнө хэлтэс үүсгэнэ үү.</p>
              )}
              <button
                type="submit"
                disabled={role === "MANAGER" && !departments.length}
              >
                Гишүүн нэмэх
              </button>
            </fieldset>
          </form>
        </>
      )}
      {members.map((member) => (
        <article className="task-item" key={member.id}>
          <div>
            <h3>{member.name}</h3>
            <p>
              {member.email} · {member.role}
              {!member.is_active ? " · Идэвхгүй" : ""}
            </p>
            {user.is_admin ? (
              <label>
                Хэлтэс — {member.name}
                <select
                  aria-label={`Хэлтэс — ${member.name}`}
                  value={member.department ?? ""}
                  disabled={busy}
                  onChange={(event) =>
                    mutate(`/api/users/${member.id}/`, "PATCH", {
                      department: event.target.value
                        ? Number(event.target.value)
                        : null,
                    })
                  }
                >
                  <option value="" disabled={member.role === "MANAGER"}>
                    Хэлтэсгүй
                  </option>
                  {departments.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <small>{member.department_name || "Хэлтэсгүй"}</small>
            )}
          </div>
          {user.is_admin && member.id !== user.id && (
            <div className="member-actions">
              <button disabled={busy} onClick={() => setEditingId(editingId === member.id ? null : member.id)}>
                {editingId === member.id ? "Засвар хаах" : "Мэдээлэл засах"}
              </button>
              {member.is_active && (
                <button
                  disabled={busy}
                  onClick={() =>
                    mutate(`/api/users/${member.id}/`, "PATCH", {
                      is_active: false,
                    })
                  }
                >
                  Идэвхгүй болгох
                </button>
              )}
              <button
                className="delete-button"
                disabled={busy}
                onClick={() => {
                  const confirmed = window.confirm(
                    `"${member.name}" (${member.email || member.username}, ${member.role}) болон түүнд холбогдсон activity, даалгавар, оноо, төхөөрөмж, зөвшөөрлийн бүртгэл бүрмөсөн устахыг батлах уу?`,
                  );
                  if (confirmed) mutate(`/api/users/${member.id}/`, "DELETE");
                }}
              >
                Бүрмөсөн устгах
              </button>
            </div>
          )}
          {user.is_admin && editingId === member.id && (
            <form className="member-edit-form" onSubmit={async (event) => {
              event.preventDefault();
              const form = Object.fromEntries(new FormData(event.currentTarget));
              form.department = form.department ? Number(form.department) : null;
              form.is_active = form.is_active === "on";
              if (await mutate(`/api/users/${member.id}/`, "PATCH", form)) setEditingId(null);
            }}>
              <label>Нэр<input name="first_name" defaultValue={member.first_name} required /></label>
              <label>Овог<input name="last_name" defaultValue={member.last_name} /></label>
              <label>Имэйл<input name="email" type="email" defaultValue={member.email} /></label>
              <label>Эрх<select name="role" defaultValue={member.role}>
                <option value="EMPLOYEE">Employee</option><option value="MANAGER">Manager</option><option value="ADMIN">Admin</option>
              </select></label>
              <label>Хэлтэс<select name="department" defaultValue={member.department ?? ""}>
                <option value="">Хэлтэсгүй</option>{departments.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </select></label>
              <label className="member-active-toggle"><input type="checkbox" name="is_active" defaultChecked={member.is_active} /> Идэвхтэй</label>
              <button type="submit" disabled={busy}>Өөрчлөлт хадгалах</button>
            </form>
          )}
        </article>
      ))}
    </section>
  );
}
