import { useState } from "react";

export default function Members({ user, members, departments, busy, mutate }) {
  const [role, setRole] = useState("EMPLOYEE");
  const [department, setDepartment] = useState("");
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
          {user.is_admin && member.id !== user.id && member.is_active && (
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
        </article>
      ))}
    </section>
  );
}
